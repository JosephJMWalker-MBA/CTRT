"""Gate witness-conflict adjudication on issuer-bound adjudicator credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicated_witness_checkpoint_runner import (
    AdjudicatedWitnessCheckpointExperimentRunner,
    AdjudicatedWitnessExperimentError,
    VerifiedAdjudicatedWitnessReceipt,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialDecisionReport,
    AdjudicatorCredentialError,
    AdjudicatorCredentialPolicySnapshot,
    CredentialBoundAdjudicationCorpusSnapshot,
    StoredAdjudicatorCredentialEvidence,
    load_adjudicator_credential_evidence,
    validate_adjudicator_credential_attestations,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.credential_revocation_checkpoints import (
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.credential_revocation_ledger import (
    CredentialRevocationLedgerSnapshot,
    CredentialRevocationPolicySnapshot,
)
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import ExtractionQualityPolicySnapshot
from ctrt.extraction_review_adjudication import (
    ReviewAdjudicationPolicySnapshot,
    ReviewDecisionOutcome,
    ReviewerRegistrySnapshot,
)
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
    ReviewerCredentialPolicySnapshot,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class CredentialedAdjudicatorRunnerStage(StrEnum):
    """Boundary at which adjudicator-credential execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    CREDENTIAL_DECISION_PERSISTENCE = "credential-decision-persistence"
    ADJUDICATED_WITNESS_EXECUTION = "adjudicated-witness-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CredentialedAdjudicatorRunnerStatus(StrEnum):
    """A receipt exists only after final evidence is reverified."""

    VERIFIED = "verified"


class CredentialedAdjudicatorExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CredentialedAdjudicatorRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS = (
    "exact-adjudicator-identity-revision-bound",
    "exact-adjudicator-role-attested",
    "issuer-and-policy-reverified",
    "credential-validity-evaluated-at-declared-time",
    "credential-abstention-precedes-adjudication-authorization",
    "preserved-adjudication-record-left-immutable",
    "adjudicator-credential-outcome-finalized",
)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


@dataclass(frozen=True, slots=True)
class CredentialedAdjudicatorFinalManifest:
    """Final marker for credential abstention or delegated adjudication outcome."""

    final_id: str
    experiment_run_id: str
    status: CredentialedAdjudicatorRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudicated_witness_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CredentialedAdjudicatorRunnerStatus.VERIFIED:
            raise ValueError("credentialed adjudicator status must be verified")
        if not self.credential_attestation_refs:
            raise ValueError("final manifest requires credential attestations")
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(
                item is not None
                for item in (
                    self.witness_outcome,
                    self.adjudication_outcome,
                    self.revocation_outcome,
                    self.adjudicated_witness_final_ref,
                )
            ):
                raise ValueError(
                    "credential abstention may not claim downstream outcomes"
                )
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("credential abstention must be terminal abstention")
            expected_id = f"{self.experiment_run_id}:adjudicator-credential-abstention"
        else:
            if (
                self.witness_outcome is None
                or self.adjudication_outcome is None
                or self.adjudicated_witness_final_ref is None
            ):
                raise ValueError(
                    "credential execution requires delegated adjudication evidence"
                )
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-credential-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-credential-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from credential terminal outcome")
        if self.verified_checks != CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS:
            raise ValueError("final manifest lost adjudicator credential checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCredentialedAdjudicatorReceipt:
    """Proof of credential eligibility and optional adjudicated execution."""

    experiment_run_id: str
    status: CredentialedAdjudicatorRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudicated_witness_receipt: VerifiedAdjudicatedWitnessReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CredentialedAdjudicatorRunnerStatus.VERIFIED:
            raise ValueError("verified credentialed adjudicator status required")
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.adjudicated_witness_receipt is not None:
                raise ValueError("credential abstention may not contain downstream receipt")
            expected_id = f"{self.experiment_run_id}:adjudicator-credential-abstention"
        else:
            if self.adjudicated_witness_receipt is None:
                raise ValueError("credential execution requires downstream receipt")
            if (
                self.adjudicated_witness_receipt.witness_outcome
                is not self.witness_outcome
                or self.adjudicated_witness_receipt.adjudication_outcome
                is not self.adjudication_outcome
                or self.adjudicated_witness_receipt.revocation_outcome
                is not self.revocation_outcome
                or self.adjudicated_witness_receipt.terminal_outcome
                is not self.terminal_outcome
            ):
                raise ValueError("delegated receipt differs from credentialed receipt")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-credential-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-credential-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong credential outcome")
        if self.verified_checks != CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS:
            raise ValueError("verified receipt lost adjudicator credential checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CredentialedAdjudicatedWitnessExperimentRunner:
    """Require eligible adjudicator credentials before adjudication can proceed."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = AdjudicatedWitnessCheckpointExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundAdjudicationCorpusSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        credential_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(credential_evaluated_at, "credential_evaluated_at")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("credentialed adjudication requires a frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match credential-bound corpus exactly")
        if corpus.corpus.adjudicator_registry_ref != adjudicator_registry.reference():
            raise ValueError("adjudicator registry reference must match corpus")
        if corpus.issuer_registry_ref != issuer_registry.reference():
            raise ValueError("issuer registry reference must match corpus")
        if corpus.credential_policy_ref != credential_policy.reference():
            raise ValueError("credential policy reference must match corpus")
        if corpus.corpus.adjudication_ref != adjudication.reference():
            raise ValueError("adjudication reference must match corpus")
        if tuple(item.content_id for item in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_report(
        self,
        artifact_id: str,
        report: object,
        message: str,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(artifact_id, report)
        reference = self._store.append(artifact)
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError(message)
        return reference

    def _verify_final(
        self,
        *,
        final: CredentialedAdjudicatorFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CredentialBoundAdjudicationCorpusSnapshot,
        evidence: StoredAdjudicatorCredentialEvidence,
        decision: AdjudicatorCredentialDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored credentialed adjudicator final differs from expected"
            )
        if self._store.get(
            final.credential_corpus_ref.artifact_id,
            expected_hash=final.credential_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "credential-bound corpus differs during verification"
            )
        for reference in (
            evidence.adjudicator_registry_ref,
            evidence.issuer_registry_ref,
            evidence.credential_policy_ref,
            evidence.adjudication_ref,
            *evidence.attestation_refs,
        ):
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_decision = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "adjudicator-credential-decision"
            ),
            decision,
        )
        if self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError(
                "stored adjudicator credential decision differs"
            )
        if final.adjudicated_witness_final_ref is not None:
            self._store.get(
                final.adjudicated_witness_final_ref.artifact_id,
                expected_hash=final.adjudicated_witness_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        method_registry: ExtractionMethodRegistrySnapshot,
        quality_policy: ExtractionQualityPolicySnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        review_policy: ReviewAdjudicationPolicySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: ReviewerCredentialPolicySnapshot,
        revocation_policy: CredentialRevocationPolicySnapshot,
        ledger: CredentialRevocationLedgerSnapshot,
        checkpoint_policy: CredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: CredentialRevocationCheckpointLogSnapshot,
        checkpoints: tuple[CredentialRevocationLedgerCheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        adjudicator_issuer_registry: CredentialIssuerRegistrySnapshot,
        adjudicator_credential_policy: AdjudicatorCredentialPolicySnapshot,
        adjudicator_credentials: tuple[
            AdjudicatorCredentialAttestationSnapshot, ...
        ],
        corpus: CredentialBoundAdjudicationCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_credential_evaluated_at: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedCredentialedAdjudicatorReceipt:
        """Return verified credential abstention or delegated adjudication outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=adjudicator_issuer_registry,
                credential_policy=adjudicator_credential_policy,
                adjudication=adjudication,
                windows=windows,
                experiment_run_id=experiment_run_id,
                credential_evaluated_at=adjudicator_credential_evaluated_at,
            )
        except ValueError as exc:
            raise CredentialedAdjudicatorExperimentError(
                CredentialedAdjudicatorRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_adjudicator_credential_evidence(
                self._store,
                corpus=corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=adjudicator_issuer_registry,
                credential_policy=adjudicator_credential_policy,
                adjudication=adjudication,
            )
        except (ArtifactStoreError, AdjudicatorCredentialError, OSError, ValueError) as exc:
            raise CredentialedAdjudicatorExperimentError(
                CredentialedAdjudicatorRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_adjudicator_credential_attestations(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=adjudicator_issuer_registry,
                credential_policy=adjudicator_credential_policy,
                attestations=evidence.attestations,
                adjudication=adjudication,
                evaluated_at=adjudicator_credential_evaluated_at,
            )
        except (AdjudicatorCredentialError, ValueError) as exc:
            raise CredentialedAdjudicatorExperimentError(
                CredentialedAdjudicatorRunnerStage.CREDENTIAL_VALIDATION,
                str(exc),
            ) from exc
        try:
            decision_ref = self._persist_report(
                f"{experiment_run_id}:adjudicator-credential-decision",
                decision,
                "stored adjudicator credential decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatorExperimentError(
                CredentialedAdjudicatorRunnerStage.CREDENTIAL_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedAdjudicatedWitnessReceipt | None = None
        witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = adjudicator_credential_evaluated_at
        delegated_final_ref: StoredArtifactRef | None = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            try:
                delegated = self._runner.run(
                    plan=plan,
                    candidate_registry=candidate_registry,
                    method_registry=method_registry,
                    quality_policy=quality_policy,
                    reviewer_registry=reviewer_registry,
                    review_policy=review_policy,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    revocation_policy=revocation_policy,
                    ledger=ledger,
                    checkpoint_policy=checkpoint_policy,
                    checkpoint_log=checkpoint_log,
                    checkpoints=checkpoints,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    witness_attestations=witness_attestations,
                    adjudicator_registry=adjudicator_registry,
                    adjudication_policy=adjudication_policy,
                    adjudication=adjudication,
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    checkpoint_verified_at=checkpoint_verified_at,
                    witness_evaluated_at=witness_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except AdjudicatedWitnessExperimentError as exc:
                raise CredentialedAdjudicatorExperimentError(
                    CredentialedAdjudicatorRunnerStage.ADJUDICATED_WITNESS_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            witness_outcome = delegated.witness_outcome
            adjudication_outcome = delegated.adjudication_outcome
            revocation_outcome = delegated.revocation_outcome
            terminal_outcome = delegated.terminal_outcome
            completed_at = delegated.completed_at
            delegated_final_ref = delegated.final_manifest_ref

        final_id = (
            f"{experiment_run_id}:adjudicator-credential-abstention"
            if decision.outcome is CredentialDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:adjudicator-credential-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "adjudicator-credential-terminal-abstention"
                )
            )
        )
        final = CredentialedAdjudicatorFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CredentialedAdjudicatorRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            witness_outcome=witness_outcome,
            adjudication_outcome=adjudication_outcome,
            revocation_outcome=revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=decision_ref,
            adjudicated_witness_final_ref=delegated_final_ref,
            verified_checks=CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(serialize_artifact(final.final_id, final))
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatorExperimentError(
                CredentialedAdjudicatorRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc
        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                evidence=evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatorExperimentError(
                CredentialedAdjudicatorRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc
        return VerifiedCredentialedAdjudicatorReceipt(
            experiment_run_id=experiment_run_id,
            status=CredentialedAdjudicatorRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            witness_outcome=witness_outcome,
            adjudication_outcome=adjudication_outcome,
            revocation_outcome=revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=decision_ref,
            adjudicated_witness_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
