"""Gate adjudicator revocation execution on immutable ledger checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
    load_adjudicator_credential_revocation_checkpoint_evidence,
    validate_adjudicator_credential_revocation_checkpoints,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
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
from ctrt.revocation_gated_adjudicated_witness_runner import (
    AdjudicatorRevocationGatedExperimentError,
    RevocationGatedAdjudicatedWitnessExperimentRunner,
    VerifiedAdjudicatorRevocationGatedReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class AdjudicatorCheckpointGatedRunnerStage(StrEnum):
    """Boundary at which adjudicator checkpoint-gated execution failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatorCheckpointGatedRunnerStatus(StrEnum):
    """A receipt exists only after checkpoint and final reverification."""

    VERIFIED = "verified"


class AdjudicatorCheckpointGatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatorCheckpointGatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS = (
    "exact-adjudicator-checkpoint-policy-bound",
    "exact-adjudicator-checkpoint-log-bound",
    "contiguous-adjudicator-checkpoint-chain-verified",
    "ordered-adjudicator-event-prefix-extension-verified",
    "adjudicator-checkpoint-head-matches-current-ledger",
    "adjudicator-checkpoint-verification-report-persisted",
    "adjudicator-checkpoint-outcome-finalized",
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
class AdjudicatorCheckpointGatedFinalManifest:
    """Final marker for checkpoint-verified adjudicator revocation execution."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatorCheckpointGatedRunnerStatus
    adjudicator_revocation_outcome: CredentialDecisionOutcome
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    checkpoint_corpus_ref: StoredArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoint_head_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    revocation_final_ref: StoredArtifactRef
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
                raise ValueError("adjudicator checkpoint identity fields must not be empty")
        if self.status is not AdjudicatorCheckpointGatedRunnerStatus.VERIFIED:
            raise ValueError("adjudicator checkpoint status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("adjudicator checkpoint requires unique multiple contents")
        if not self.checkpoint_refs:
            raise ValueError("adjudicator checkpoint final requires checkpoints")
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError("adjudicator checkpoint head must be final checkpoint")
        expected_id = (
            f"{self.experiment_run_id}:adjudicator-revocation-checkpoint-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{self.experiment_run_id}:"
                "adjudicator-revocation-checkpoint-terminal-abstention"
            )
        )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from checkpoint terminal outcome")
        if self.verified_checks != ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS:
            raise ValueError("final manifest lost adjudicator checkpoint checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatorCheckpointGatedReceipt:
    """Proof of checkpoint verification and downstream revocation outcome."""

    experiment_run_id: str
    status: AdjudicatorCheckpointGatedRunnerStatus
    adjudicator_revocation_outcome: CredentialDecisionOutcome
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    checkpoint_corpus_ref: StoredArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoint_head_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    revocation_receipt: VerifiedAdjudicatorRevocationGatedReceipt
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not AdjudicatorCheckpointGatedRunnerStatus.VERIFIED:
            raise ValueError("verified adjudicator checkpoint status required")
        delegated = self.revocation_receipt
        if (
            delegated.adjudicator_revocation_outcome
            is not self.adjudicator_revocation_outcome
            or delegated.adjudicator_credential_outcome
            is not self.adjudicator_credential_outcome
            or delegated.witness_outcome is not self.witness_outcome
            or delegated.adjudication_outcome is not self.adjudication_outcome
            or delegated.reviewer_revocation_outcome
            is not self.reviewer_revocation_outcome
            or delegated.terminal_outcome is not self.terminal_outcome
        ):
            raise ValueError("revocation receipt differs from checkpoint receipt")
        expected_id = (
            f"{self.experiment_run_id}:adjudicator-revocation-checkpoint-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{self.experiment_run_id}:"
                "adjudicator-revocation-checkpoint-terminal-abstention"
            )
        )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong checkpoint outcome")
        if self.verified_checks != ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS:
            raise ValueError("verified receipt lost adjudicator checkpoint checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedAdjudicatorRevocationExperimentRunner:
    """Verify adjudicator checkpoint history before revocation evaluation."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = RevocationGatedAdjudicatedWitnessExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_checkpoint_verified_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            adjudicator_checkpoint_verified_at,
            "adjudicator_checkpoint_verified_at",
        )
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-gated adjudication requires a frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match checkpoint-bound corpus exactly")
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("checkpoint policy reference must match corpus")
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("checkpoint log reference must match corpus")
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("checkpoint head reference must match corpus")
        if tuple(item.content_id for item in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            report,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored adjudicator checkpoint report differs")
        self._store.append(
            serialize_artifact(
                report.artifact_id,
                {
                    "experiment_id": report.experiment_id,
                    "experiment_version": report.experiment_version,
                    "checkpoint_corpus_ref": report.checkpoint_corpus_ref,
                    "checkpoint_policy_ref": report.checkpoint_policy_ref,
                    "checkpoint_log_ref": report.checkpoint_log_ref,
                    "head_checkpoint_ref": report.head_checkpoint_ref,
                },
            )
        )
        return reference

    def _verify_final(
        self,
        *,
        final: AdjudicatorCheckpointGatedFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored adjudicator checkpoint final differs")
        if self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("checkpoint corpus differs during verification")
        if self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        ).payload != checkpoint_policy.canonical_payload:
            raise ArtifactIntegrityError("checkpoint policy differs during verification")
        if self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        ).payload != checkpoint_log.canonical_payload:
            raise ArtifactIntegrityError("checkpoint log differs during verification")
        for reference in evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        report_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != report_artifact.payload:
            raise ArtifactIntegrityError("checkpoint report differs during verification")
        self._store.get(
            final.revocation_final_ref.artifact_id,
            expected_hash=final.revocation_final_ref.artifact_hash,
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
        adjudicator_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        adjudicator_checkpoint_log: (
            AdjudicatorCredentialRevocationCheckpointLogSnapshot
        ),
        adjudicator_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        corpus: CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_checkpoint_verified_at: str,
        adjudicator_revocation_evaluated_at: str,
        adjudicator_credential_evaluated_at: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedAdjudicatorCheckpointGatedReceipt:
        """Return checkpoint verification plus downstream revocation outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                checkpoint_policy=adjudicator_checkpoint_policy,
                checkpoint_log=adjudicator_checkpoint_log,
                windows=windows,
                experiment_run_id=experiment_run_id,
                adjudicator_checkpoint_verified_at=(
                    adjudicator_checkpoint_verified_at
                ),
            )
        except ValueError as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_adjudicator_credential_revocation_checkpoint_evidence(
                self._store,
                corpus=corpus,
                policy=adjudicator_checkpoint_policy,
                log=adjudicator_checkpoint_log,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = validate_adjudicator_credential_revocation_checkpoints(
                plan=plan,
                corpus=corpus,
                policy=adjudicator_checkpoint_policy,
                log=adjudicator_checkpoint_log,
                ledger=adjudicator_revocation_ledger,
                checkpoints=evidence.checkpoints,
                verified_at=adjudicator_checkpoint_verified_at,
            )
        except (AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc

        try:
            report_ref = self._persist_report(
                experiment_run_id=experiment_run_id,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

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
                adjudicator_revocation_policy=adjudicator_revocation_policy,
                adjudicator_revocation_ledger=adjudicator_revocation_ledger,
                corpus=corpus.corpus,
                environment=environment,
                windows=windows,
                experiment_run_id=experiment_run_id,
                adjudicator_revocation_evaluated_at=(
                    adjudicator_revocation_evaluated_at
                ),
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
        except AdjudicatorRevocationGatedExperimentError as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        final_id = (
            f"{experiment_run_id}:adjudicator-revocation-checkpoint-completion"
            if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{experiment_run_id}:"
                "adjudicator-revocation-checkpoint-terminal-abstention"
            )
        )
        final = AdjudicatorCheckpointGatedFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatorCheckpointGatedRunnerStatus.VERIFIED,
            adjudicator_revocation_outcome=(
                delegated.adjudicator_revocation_outcome
            ),
            adjudicator_credential_outcome=(
                delegated.adjudicator_credential_outcome
            ),
            witness_outcome=delegated.witness_outcome,
            adjudication_outcome=delegated.adjudication_outcome,
            reviewer_revocation_outcome=delegated.reviewer_revocation_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=adjudicator_checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_final_ref=delegated.final_manifest_ref,
            verified_checks=ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS,
            completed_at=delegated.completed_at,
        )
        try:
            final_ref = self._store.append(serialize_artifact(final.final_id, final))
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                checkpoint_policy=adjudicator_checkpoint_policy,
                checkpoint_log=adjudicator_checkpoint_log,
                evidence=evidence,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointGatedExperimentError(
                AdjudicatorCheckpointGatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatorCheckpointGatedReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatorCheckpointGatedRunnerStatus.VERIFIED,
            adjudicator_revocation_outcome=delegated.adjudicator_revocation_outcome,
            adjudicator_credential_outcome=delegated.adjudicator_credential_outcome,
            witness_outcome=delegated.witness_outcome,
            adjudication_outcome=delegated.adjudication_outcome,
            reviewer_revocation_outcome=delegated.reviewer_revocation_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=adjudicator_checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS,
            completed_at=delegated.completed_at,
        )
