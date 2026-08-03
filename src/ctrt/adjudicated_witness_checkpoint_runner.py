"""Gate checkpoint execution on authorized witness-conflict adjudication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.checkpoint_gated_revocation_runner import (
    CheckpointGatedExperimentError,
    CheckpointGatedRevocationExperimentRunner,
    VerifiedCheckpointGatedReceipt,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessDecisionReport,
    CheckpointWitnessError,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
    validate_checkpoint_witness_attestations,
)
from ctrt.credential_revocation_checkpoints import (
    CredentialRevocationCheckpointError,
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationCheckpointVerificationReport,
    CredentialRevocationLedgerCheckpointSnapshot,
    load_credential_revocation_checkpoint_evidence,
    validate_credential_revocation_checkpoints,
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
    AdjudicationBoundWitnessCorpusSnapshot,
    StoredWitnessConflictAdjudicationEvidence,
    WitnessConflictAdjudicationDecisionReport,
    WitnessConflictAdjudicationError,
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    load_witness_conflict_adjudication_evidence,
    validate_witness_conflict_adjudication,
)
from ctrt.workbench import AnalyzerRegistry


class AdjudicatedWitnessRunnerStage(StrEnum):
    """Boundary at which adjudicated witness execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    ADJUDICATION_VALIDATION = "adjudication-validation"
    ADJUDICATION_DECISION_PERSISTENCE = "adjudication-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatedWitnessRunnerStatus(StrEnum):
    """A receipt exists only after all final evidence is reverified."""

    VERIFIED = "verified"


class AdjudicatedWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatedWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATED_WITNESS_VERIFIED_CHECKS = (
    "checkpoint-chain-reverified-before-adjudication",
    "witness-observations-reverified-without-voting",
    "exact-adjudicator-registry-and-policy-bound",
    "conflicting-fork-evidence-preserved",
    "authorized-resolution-or-fail-closed-abstention",
    "preserved-dissent-reverified",
    "adjudication-outcome-finalized",
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
class AdjudicatedWitnessFinalManifest:
    """Final marker for adjudication abstention or downstream outcome."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatedWitnessRunnerStatus
    witness_outcome: CheckpointWitnessDecisionOutcome
    adjudication_outcome: WitnessConflictAdjudicationOutcome
    revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    adjudication_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    checkpoint_final_ref: StoredArtifactRef | None
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
                raise ValueError(
                    "adjudicated witness identity fields must not be empty"
                )
        if self.status is not AdjudicatedWitnessRunnerStatus.VERIFIED:
            raise ValueError("adjudicated witness status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError(
                "adjudicated witness execution requires unique multiple contents"
            )
        if not self.witness_attestation_refs:
            raise ValueError(
                "adjudicated witness final requires witness attestations"
            )
        if self.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN:
            if self.revocation_outcome is not None or self.checkpoint_final_ref is not None:
                raise ValueError(
                    "adjudication abstention may not claim checkpoint execution"
                )
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError(
                    "adjudication abstention must be terminal abstention"
                )
            expected_id = (
                f"{self.experiment_run_id}:"
                "witness-conflict-adjudication-abstention"
            )
        else:
            if self.revocation_outcome is None or self.checkpoint_final_ref is None:
                raise ValueError(
                    "adjudication-permitted final requires checkpoint execution"
                )
            expected_id = (
                f"{self.experiment_run_id}:"
                "witness-conflict-adjudication-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "witness-conflict-adjudication-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError(
                "final_id must derive from adjudicated witness terminal outcome"
            )
        if self.verified_checks != ADJUDICATED_WITNESS_VERIFIED_CHECKS:
            raise ValueError(
                "adjudicated witness final must preserve every verified check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatedWitnessReceipt:
    """Proof of witness adjudication and optional checkpoint execution."""

    experiment_run_id: str
    status: AdjudicatedWitnessRunnerStatus
    witness_outcome: CheckpointWitnessDecisionOutcome
    adjudication_outcome: WitnessConflictAdjudicationOutcome
    revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    adjudication_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    checkpoint_receipt: VerifiedCheckpointGatedReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not AdjudicatedWitnessRunnerStatus.VERIFIED:
            raise ValueError(
                "verified adjudicated witness status must be verified"
            )
        if self.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None or self.revocation_outcome is not None:
                raise ValueError(
                    "adjudication abstention may not contain checkpoint outcome"
                )
            expected_id = (
                f"{self.experiment_run_id}:"
                "witness-conflict-adjudication-abstention"
            )
        else:
            if self.checkpoint_receipt is None or self.revocation_outcome is None:
                raise ValueError(
                    "adjudication-permitted receipt requires checkpoint outcome"
                )
            if self.checkpoint_receipt.revocation_outcome is not self.revocation_outcome:
                raise ValueError(
                    "checkpoint receipt differs from revocation outcome"
                )
            if self.checkpoint_receipt.terminal_outcome is not self.terminal_outcome:
                raise ValueError(
                    "checkpoint receipt differs from terminal outcome"
                )
            expected_id = (
                f"{self.experiment_run_id}:"
                "witness-conflict-adjudication-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "witness-conflict-adjudication-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError(
                "final manifest must identify adjudication terminal outcome"
            )
        if self.verified_checks != ADJUDICATED_WITNESS_VERIFIED_CHECKS:
            raise ValueError(
                "verified adjudicated witness receipt lost checks"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatedWitnessCheckpointExperimentRunner:
    """Resolve or preserve witness conflicts before checkpoint execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CheckpointGatedRevocationExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: AdjudicationBoundWitnessCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        for value, field_name in (
            (checkpoint_verified_at, "checkpoint_verified_at"),
            (witness_evaluated_at, "witness_evaluated_at"),
            (adjudication_evaluated_at, "adjudication_evaluated_at"),
            (revocation_evaluated_at, "revocation_evaluated_at"),
            (credential_evaluated_at, "credential_evaluated_at"),
            (quality_evaluated_at, "quality_evaluated_at"),
            (review_evaluated_at, "review_evaluated_at"),
        ):
            _parse_timestamp(value, field_name)
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError(
                "adjudicated witness execution requires a frozen plan"
            )
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError(
                "plan must match adjudication-bound corpus exactly"
            )
        if corpus.corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry reference must match corpus")
        if corpus.corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy reference must match corpus")
        if corpus.adjudicator_registry_ref != adjudicator_registry.reference():
            raise ValueError("adjudicator registry reference must match corpus")
        if corpus.adjudication_policy_ref != adjudication_policy.reference():
            raise ValueError("adjudication policy reference must match corpus")
        if corpus.adjudication_ref != adjudication.reference():
            raise ValueError("adjudication record reference must match corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError(
                "execution windows must match frozen content order"
            )

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
        final: AdjudicatedWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: AdjudicationBoundWitnessCorpusSnapshot,
        evidence: StoredWitnessConflictAdjudicationEvidence,
        checkpoint_report: CredentialRevocationCheckpointVerificationReport,
        witness_decision: CheckpointWitnessDecisionReport,
        adjudication_decision: WitnessConflictAdjudicationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored adjudicated witness final differs from expected"
            )
        if self._store.get(
            final.adjudication_corpus_ref.artifact_id,
            expected_hash=final.adjudication_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "adjudication corpus differs during verification"
            )
        for reference in (
            *evidence.witness_evidence.attestation_refs,
            evidence.adjudication_ref,
            evidence.adjudicator_registry_ref,
            evidence.adjudication_policy_ref,
        ):
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_reports = (
            (
                final.checkpoint_verification_ref,
                serialize_artifact(
                    (
                        f"{final.experiment_run_id}:"
                        "credential-revocation-checkpoint-verification"
                    ),
                    checkpoint_report,
                ),
            ),
            (
                final.witness_decision_ref,
                serialize_artifact(
                    f"{final.experiment_run_id}:checkpoint-witness-decision",
                    witness_decision,
                ),
            ),
            (
                final.adjudication_decision_ref,
                serialize_artifact(
                    (
                        f"{final.experiment_run_id}:"
                        "witness-conflict-adjudication-decision"
                    ),
                    adjudication_decision,
                ),
            ),
        )
        for reference, artifact in expected_reports:
            if self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            ).payload != artifact.payload:
                raise ArtifactIntegrityError(
                    "stored adjudication report differs during verification"
                )
        if final.checkpoint_final_ref is not None:
            self._store.get(
                final.checkpoint_final_ref.artifact_id,
                expected_hash=final.checkpoint_final_ref.artifact_hash,
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
        corpus: AdjudicationBoundWitnessCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedAdjudicatedWitnessReceipt:
        """Return verified adjudication abstention or downstream outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                adjudication=adjudication,
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
        except ValueError as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_witness_conflict_adjudication_evidence(
                self._store,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                adjudication=adjudication,
            )
            checkpoint_evidence = load_credential_revocation_checkpoint_evidence(
                self._store,
                corpus=corpus.corpus.corpus,
                policy=checkpoint_policy,
                log=checkpoint_log,
            )
        except (
            ArtifactStoreError,
            CheckpointWitnessError,
            CredentialRevocationCheckpointError,
            WitnessConflictAdjudicationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = validate_credential_revocation_checkpoints(
                plan=plan,
                corpus=corpus.corpus.corpus,
                policy=checkpoint_policy,
                log=checkpoint_log,
                ledger=ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=checkpoint_verified_at,
            )
        except (CredentialRevocationCheckpointError, ValueError) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc
        try:
            checkpoint_report_ref = self._persist_report(
                (
                    f"{experiment_run_id}:"
                    "credential-revocation-checkpoint-verification"
                ),
                checkpoint_report,
                "stored checkpoint report differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_checkpoint_witness_attestations(
                plan=plan,
                corpus=corpus.corpus,
                registry=witness_registry,
                policy=witness_policy,
                head_checkpoint=checkpoint_evidence.checkpoints[-1],
                attestations=evidence.witness_evidence.attestations,
                evaluated_at=witness_evaluated_at,
            )
        except (CheckpointWitnessError, ValueError) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.WITNESS_VALIDATION,
                str(exc),
            ) from exc
        try:
            witness_decision_ref = self._persist_report(
                f"{experiment_run_id}:checkpoint-witness-decision",
                witness_decision,
                "stored witness decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            adjudication_decision = validate_witness_conflict_adjudication(
                plan=plan,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                witness_decision=witness_decision,
                adjudication=adjudication,
                evaluated_at=adjudication_evaluated_at,
            )
        except (WitnessConflictAdjudicationError, ValueError) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.ADJUDICATION_VALIDATION,
                str(exc),
            ) from exc
        try:
            adjudication_decision_ref = self._persist_report(
                (
                    f"{experiment_run_id}:"
                    "witness-conflict-adjudication-decision"
                ),
                adjudication_decision,
                "stored adjudication decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.ADJUDICATION_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        checkpoint_receipt: VerifiedCheckpointGatedReceipt | None = None
        checkpoint_final_ref: StoredArtifactRef | None = None
        revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = adjudication_evaluated_at
        if (
            adjudication_decision.outcome
            is WitnessConflictAdjudicationOutcome.EXECUTE
        ):
            try:
                checkpoint_receipt = self._runner.run(
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
                    corpus=corpus.corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    checkpoint_verified_at=checkpoint_verified_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except CheckpointGatedExperimentError as exc:
                raise AdjudicatedWitnessExperimentError(
                    AdjudicatedWitnessRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            checkpoint_final_ref = checkpoint_receipt.final_manifest_ref
            revocation_outcome = checkpoint_receipt.revocation_outcome
            terminal_outcome = checkpoint_receipt.terminal_outcome
            completed_at = checkpoint_receipt.completed_at

        final_id = (
            f"{experiment_run_id}:witness-conflict-adjudication-abstention"
            if adjudication_decision.outcome
            is WitnessConflictAdjudicationOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:witness-conflict-adjudication-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "witness-conflict-adjudication-terminal-abstention"
                )
            )
        )
        final = AdjudicatedWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatedWitnessRunnerStatus.VERIFIED,
            witness_outcome=witness_decision.outcome,
            adjudication_outcome=adjudication_decision.outcome,
            revocation_outcome=revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            witness_registry_ref=evidence.witness_evidence.witness_registry_ref,
            witness_policy_ref=evidence.witness_evidence.witness_policy_ref,
            witness_attestation_refs=evidence.witness_evidence.attestation_refs,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            adjudication_policy_ref=evidence.adjudication_policy_ref,
            adjudication_ref=evidence.adjudication_ref,
            checkpoint_verification_ref=checkpoint_report_ref,
            witness_decision_ref=witness_decision_ref,
            adjudication_decision_ref=adjudication_decision_ref,
            checkpoint_final_ref=checkpoint_final_ref,
            verified_checks=ADJUDICATED_WITNESS_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(
                serialize_artifact(final.final_id, final)
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.FINAL_PERSISTENCE,
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
                checkpoint_report=checkpoint_report,
                witness_decision=witness_decision,
                adjudication_decision=adjudication_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedWitnessExperimentError(
                AdjudicatedWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc
        return VerifiedAdjudicatedWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatedWitnessRunnerStatus.VERIFIED,
            witness_outcome=witness_decision.outcome,
            adjudication_outcome=adjudication_decision.outcome,
            revocation_outcome=revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            witness_registry_ref=evidence.witness_evidence.witness_registry_ref,
            witness_policy_ref=evidence.witness_evidence.witness_policy_ref,
            witness_attestation_refs=evidence.witness_evidence.attestation_refs,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            adjudication_policy_ref=evidence.adjudication_policy_ref,
            adjudication_ref=evidence.adjudication_ref,
            checkpoint_verification_ref=checkpoint_report_ref,
            witness_decision_ref=witness_decision_ref,
            adjudication_decision_ref=adjudication_decision_ref,
            checkpoint_receipt=checkpoint_receipt,
            final_manifest_ref=final_ref,
            verified_checks=ADJUDICATED_WITNESS_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
