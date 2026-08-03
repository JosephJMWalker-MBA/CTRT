"""Gate adjudicator-credential execution on an append-only status ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
    load_adjudicator_credential_evidence,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundAdjudicatorCredentialCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationEvidence,
    load_adjudicator_credential_revocation_evidence,
    validate_adjudicator_credential_revocation_ledger,
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
from ctrt.credentialed_adjudicated_witness_runner import (
    CredentialedAdjudicatedWitnessExperimentRunner,
    CredentialedAdjudicatorExperimentError,
    VerifiedCredentialedAdjudicatorReceipt,
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


class AdjudicatorRevocationGatedRunnerStage(StrEnum):
    """Boundary at which adjudicator revocation-gated execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIALED_EXECUTION = "credentialed-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatorRevocationGatedRunnerStatus(StrEnum):
    """A receipt exists only after final evidence is reverified."""

    VERIFIED = "verified"


class AdjudicatorRevocationGatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatorRevocationGatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS = (
    "exact-adjudicator-revocation-policy-bound",
    "exact-adjudicator-revocation-ledger-bound",
    "issuer-authority-and-linear-supersession-reverified",
    "adjudicator-credential-status-evaluated-as-of-declared-time",
    "revocation-decision-persisted-before-adjudication",
    "credential-and-adjudication-records-left-immutable",
    "adjudicator-revocation-outcome-finalized",
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
class AdjudicatorRevocationGatedFinalManifest:
    """Final marker for ledger abstention or delegated credential outcome."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatorRevocationGatedRunnerStatus
    adjudicator_revocation_outcome: CredentialDecisionOutcome
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    revocation_decision_ref: StoredArtifactRef
    credentialed_adjudicator_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        for value in (
            self.final_id,
            self.experiment_run_id,
            self.experiment_id,
            self.experiment_version,
        ):
            if not value.strip():
                raise ValueError("adjudicator revocation identity fields must not be empty")
        if self.status is not AdjudicatorRevocationGatedRunnerStatus.VERIFIED:
            raise ValueError("adjudicator revocation status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError("adjudicator revocation requires unique multiple contents")
        if self.adjudicator_revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(
                value is not None
                for value in (
                    self.adjudicator_credential_outcome,
                    self.witness_outcome,
                    self.adjudication_outcome,
                    self.reviewer_revocation_outcome,
                    self.credentialed_adjudicator_final_ref,
                )
            ):
                raise ValueError("revocation abstention may not claim downstream outcomes")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("revocation abstention must be terminal abstention")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-credential-revocation-abstention"
            )
        else:
            if (
                self.adjudicator_credential_outcome is None
                or self.credentialed_adjudicator_final_ref is None
            ):
                raise ValueError("revocation execution requires credentialed outcome")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-credential-revocation-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-credential-revocation-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from revocation terminal outcome")
        if self.verified_checks != ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS:
            raise ValueError("final manifest lost adjudicator revocation checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatorRevocationGatedReceipt:
    """Proof of ledger eligibility and optional credentialed adjudication."""

    experiment_run_id: str
    status: AdjudicatorRevocationGatedRunnerStatus
    adjudicator_revocation_outcome: CredentialDecisionOutcome
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    revocation_decision_ref: StoredArtifactRef
    credentialed_adjudicator_receipt: VerifiedCredentialedAdjudicatorReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not AdjudicatorRevocationGatedRunnerStatus.VERIFIED:
            raise ValueError("verified adjudicator revocation status required")
        if self.adjudicator_revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.credentialed_adjudicator_receipt is not None:
                raise ValueError("revocation abstention may not contain downstream receipt")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-credential-revocation-abstention"
            )
        else:
            delegated = self.credentialed_adjudicator_receipt
            if delegated is None:
                raise ValueError("revocation execution requires downstream receipt")
            if (
                delegated.credential_outcome is not self.adjudicator_credential_outcome
                or delegated.witness_outcome is not self.witness_outcome
                or delegated.adjudication_outcome is not self.adjudication_outcome
                or delegated.revocation_outcome is not self.reviewer_revocation_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("delegated receipt differs from revocation receipt")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-credential-revocation-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-credential-revocation-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong revocation outcome")
        if self.verified_checks != ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS:
            raise ValueError("verified receipt lost adjudicator revocation checks")
        _parse_timestamp(self.completed_at, "completed_at")


class RevocationGatedAdjudicatedWitnessExperimentRunner:
    """Evaluate immutable adjudicator status history before credential execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CredentialedAdjudicatedWitnessExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_revocation_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            adjudicator_revocation_evaluated_at,
            "adjudicator_revocation_evaluated_at",
        )
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("revocation-gated adjudication requires a frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match revocation-bound corpus exactly")
        if corpus.revocation_policy_ref != revocation_policy.reference():
            raise ValueError("revocation policy reference must match corpus")
        if corpus.revocation_ledger_ref != ledger.reference():
            raise ValueError("revocation ledger reference must match corpus")
        if tuple(item.content_id for item in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:adjudicator-credential-revocation-decision",
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored adjudicator revocation decision differs")
        self._store.append(
            serialize_artifact(
                decision.artifact_id,
                {
                    "experiment_id": decision.experiment_id,
                    "experiment_version": decision.experiment_version,
                    "revocation_corpus_ref": decision.revocation_corpus_ref,
                    "revocation_policy_ref": decision.revocation_policy_ref,
                    "revocation_ledger_ref": decision.revocation_ledger_ref,
                    "adjudication_ref": decision.adjudication_ref,
                },
            )
        )
        return reference

    def _verify_final(
        self,
        *,
        final: AdjudicatorRevocationGatedFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot,
        policy: AdjudicatorCredentialRevocationPolicySnapshot,
        ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationEvidence,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored revocation final differs from expected")
        if self._store.get(
            final.revocation_corpus_ref.artifact_id,
            expected_hash=final.revocation_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("revocation corpus differs during verification")
        if self._store.get(
            final.revocation_policy_ref.artifact_id,
            expected_hash=final.revocation_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("revocation policy differs during verification")
        if self._store.get(
            final.revocation_ledger_ref.artifact_id,
            expected_hash=final.revocation_ledger_ref.artifact_hash,
        ).payload != ledger.canonical_payload:
            raise ArtifactIntegrityError("revocation ledger differs during verification")
        for reference in evidence.event_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_decision = serialize_artifact(
            f"{final.experiment_run_id}:adjudicator-credential-revocation-decision",
            decision,
        )
        if self._store.get(
            final.revocation_decision_ref.artifact_id,
            expected_hash=final.revocation_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError("revocation decision differs during verification")
        if final.credentialed_adjudicator_final_ref is not None:
            self._store.get(
                final.credentialed_adjudicator_final_ref.artifact_id,
                expected_hash=final.credentialed_adjudicator_final_ref.artifact_hash,
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
        adjudicator_credentials: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
        adjudicator_revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        adjudicator_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_revocation_evaluated_at: str,
        adjudicator_credential_evaluated_at: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedAdjudicatorRevocationGatedReceipt:
        """Return verified revocation abstention or delegated credential outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_policy=adjudicator_revocation_policy,
                ledger=adjudicator_revocation_ledger,
                windows=windows,
                experiment_run_id=experiment_run_id,
                adjudicator_revocation_evaluated_at=(
                    adjudicator_revocation_evaluated_at
                ),
            )
        except ValueError as exc:
            raise AdjudicatorRevocationGatedExperimentError(
                AdjudicatorRevocationGatedRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            revocation_evidence = load_adjudicator_credential_revocation_evidence(
                self._store,
                corpus=corpus,
                policy=adjudicator_revocation_policy,
                ledger=adjudicator_revocation_ledger,
            )
            credential_evidence = load_adjudicator_credential_evidence(
                self._store,
                corpus=corpus.corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=adjudicator_issuer_registry,
                credential_policy=adjudicator_credential_policy,
                adjudication=adjudication,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorRevocationGatedExperimentError(
                AdjudicatorRevocationGatedRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_adjudicator_credential_revocation_ledger(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=adjudicator_issuer_registry,
                credential_policy=adjudicator_credential_policy,
                revocation_policy=adjudicator_revocation_policy,
                ledger=adjudicator_revocation_ledger,
                attestations=credential_evidence.attestations,
                adjudication=adjudication,
                events=revocation_evidence.events,
                evaluated_at=adjudicator_revocation_evaluated_at,
            )
        except (AdjudicatorCredentialRevocationError, ValueError) as exc:
            raise AdjudicatorRevocationGatedExperimentError(
                AdjudicatorRevocationGatedRunnerStage.REVOCATION_VALIDATION,
                str(exc),
            ) from exc

        try:
            decision_ref = self._persist_decision(
                experiment_run_id=experiment_run_id,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorRevocationGatedExperimentError(
                AdjudicatorRevocationGatedRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCredentialedAdjudicatorReceipt | None = None
        credential_outcome: CredentialDecisionOutcome | None = None
        witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        reviewer_revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = adjudicator_revocation_evaluated_at
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
                    adjudicator_issuer_registry=adjudicator_issuer_registry,
                    adjudicator_credential_policy=adjudicator_credential_policy,
                    adjudicator_credentials=adjudicator_credentials,
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    adjudicator_credential_evaluated_at=(
                        adjudicator_credential_evaluated_at
                    ),
                    checkpoint_verified_at=checkpoint_verified_at,
                    witness_evaluated_at=witness_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except CredentialedAdjudicatorExperimentError as exc:
                raise AdjudicatorRevocationGatedExperimentError(
                    AdjudicatorRevocationGatedRunnerStage.CREDENTIALED_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            credential_outcome = delegated.credential_outcome
            witness_outcome = delegated.witness_outcome
            adjudication_outcome = delegated.adjudication_outcome
            reviewer_revocation_outcome = delegated.revocation_outcome
            terminal_outcome = delegated.terminal_outcome
            completed_at = delegated.completed_at
            delegated_final_ref = delegated.final_manifest_ref

        final_id = (
            f"{experiment_run_id}:adjudicator-credential-revocation-abstention"
            if decision.outcome is CredentialDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:adjudicator-credential-revocation-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "adjudicator-credential-revocation-terminal-abstention"
                )
            )
        )
        final = AdjudicatorRevocationGatedFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatorRevocationGatedRunnerStatus.VERIFIED,
            adjudicator_revocation_outcome=decision.outcome,
            adjudicator_credential_outcome=credential_outcome,
            witness_outcome=witness_outcome,
            adjudication_outcome=adjudication_outcome,
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=revocation_evidence.corpus_ref,
            revocation_policy_ref=revocation_evidence.revocation_policy_ref,
            revocation_ledger_ref=revocation_evidence.revocation_ledger_ref,
            revocation_event_refs=revocation_evidence.event_refs,
            adjudication_ref=adjudication.reference(),
            revocation_decision_ref=decision_ref,
            credentialed_adjudicator_final_ref=delegated_final_ref,
            verified_checks=ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS,
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
            raise AdjudicatorRevocationGatedExperimentError(
                AdjudicatorRevocationGatedRunnerStage.FINAL_PERSISTENCE,
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
                policy=adjudicator_revocation_policy,
                ledger=adjudicator_revocation_ledger,
                evidence=revocation_evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorRevocationGatedExperimentError(
                AdjudicatorRevocationGatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatorRevocationGatedReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatorRevocationGatedRunnerStatus.VERIFIED,
            adjudicator_revocation_outcome=decision.outcome,
            adjudicator_credential_outcome=credential_outcome,
            witness_outcome=witness_outcome,
            adjudication_outcome=adjudication_outcome,
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=revocation_evidence.corpus_ref,
            revocation_policy_ref=revocation_evidence.revocation_policy_ref,
            revocation_ledger_ref=revocation_evidence.revocation_ledger_ref,
            revocation_event_refs=revocation_evidence.event_refs,
            adjudication_ref=adjudication.reference(),
            revocation_decision_ref=decision_ref,
            credentialed_adjudicator_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
