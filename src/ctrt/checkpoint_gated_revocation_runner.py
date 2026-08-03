"""Gate revocation execution on immutable sequential ledger checkpoints."""

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
from ctrt.credential_revocation_checkpoints import (
    CheckpointBoundRevocationCorpusSnapshot,
    CredentialRevocationCheckpointError,
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationLedgerCheckpointSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationCheckpointVerificationReport,
    StoredCredentialRevocationCheckpointEvidence,
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
from ctrt.revocation_gated_credentialed_runner import (
    RevocationGatedCredentialedExtractionExperimentRunner,
    RevocationGatedExperimentError,
    VerifiedRevocationGatedReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class CheckpointGatedRunnerStage(StrEnum):
    """Boundary at which checkpoint-gated execution failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointGatedRunnerStatus(StrEnum):
    """A receipt exists only after checkpoint and final reverification."""

    VERIFIED = "verified"


class CheckpointGatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointGatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_GATED_VERIFIED_CHECKS = (
    "exact-checkpoint-policy-bound",
    "exact-checkpoint-log-bound",
    "contiguous-predecessor-chain-verified",
    "ordered-event-prefix-extension-verified",
    "checkpoint-head-matches-current-ledger",
    "checkpoint-verification-report-persisted",
    "checkpoint-outcome-finalized",
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
class CheckpointGatedFinalManifest:
    """Final marker for checkpoint-verified revocation execution."""

    final_id: str
    experiment_run_id: str
    status: CheckpointGatedRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
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
        if any(
            not value.strip()
            for value in (
                self.final_id,
                self.experiment_run_id,
                self.experiment_id,
                self.experiment_version,
            )
        ):
            raise ValueError(
                "checkpoint-gated identity fields must not be empty"
            )
        if self.status is not CheckpointGatedRunnerStatus.VERIFIED:
            raise ValueError("checkpoint-gated status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError(
                "checkpoint-gated execution requires unique multiple content items"
            )
        if not self.checkpoint_refs:
            raise ValueError(
                "checkpoint-gated final requires checkpoint references"
            )
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError(
                "checkpoint-gated final head must be final checkpoint"
            )
        expected_id = (
            f"{self.experiment_run_id}:revocation-checkpoint-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{self.experiment_run_id}:"
                "revocation-checkpoint-terminal-abstention"
            )
        )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from terminal outcome")
        if self.verified_checks != CHECKPOINT_GATED_VERIFIED_CHECKS:
            raise ValueError(
                "checkpoint-gated final must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointGatedReceipt:
    """Proof of checkpoint verification and downstream revocation outcome."""

    experiment_run_id: str
    status: CheckpointGatedRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
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
    revocation_receipt: VerifiedRevocationGatedReceipt
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointGatedRunnerStatus.VERIFIED:
            raise ValueError(
                "verified checkpoint-gated status must be verified"
            )
        if self.revocation_receipt.revocation_outcome is not (
            self.revocation_outcome
        ):
            raise ValueError(
                "revocation receipt differs from revocation outcome"
            )
        if self.revocation_receipt.terminal_outcome is not (
            self.terminal_outcome
        ):
            raise ValueError(
                "revocation receipt differs from terminal outcome"
            )
        expected_id = (
            f"{self.experiment_run_id}:revocation-checkpoint-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{self.experiment_run_id}:"
                "revocation-checkpoint-terminal-abstention"
            )
        )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError(
                "final manifest must identify checkpoint terminal outcome"
            )
        if self.verified_checks != CHECKPOINT_GATED_VERIFIED_CHECKS:
            raise ValueError(
                "verified checkpoint receipt must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedRevocationExperimentRunner:
    """Verify checkpoint history before revocation-gated execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = RevocationGatedCredentialedExtractionExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CheckpointBoundRevocationCorpusSnapshot,
        checkpoint_policy: CredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: CredentialRevocationCheckpointLogSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        for value, field_name in (
            (checkpoint_verified_at, "checkpoint_verified_at"),
            (revocation_evaluated_at, "revocation_evaluated_at"),
            (credential_evaluated_at, "credential_evaluated_at"),
            (quality_evaluated_at, "quality_evaluated_at"),
            (review_evaluated_at, "review_evaluated_at"),
        ):
            _parse_timestamp(value, field_name)
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError(
                "checkpoint-gated execution requires a frozen plan"
            )
        if plan.corpus_ref != corpus.reference() or plan.content_ids != (
            corpus.content_ids
        ):
            raise ValueError(
                "plan must match checkpoint-bound corpus exactly"
            )
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError(
                "checkpoint policy reference must match corpus"
            )
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError(
                "checkpoint log reference must match corpus"
            )
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError(
                "checkpoint head reference must match corpus"
            )
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError(
                "execution windows must match frozen content order"
            )

    def _persist_report(
        self,
        *,
        experiment_run_id: str,
        report: CredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:credential-revocation-checkpoint-verification",
            report,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint verification differs from report"
            )
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
        final: CheckpointGatedFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CheckpointBoundRevocationCorpusSnapshot,
        checkpoint_policy: CredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: CredentialRevocationCheckpointLogSnapshot,
        evidence: StoredCredentialRevocationCheckpointEvidence,
        report: CredentialRevocationCheckpointVerificationReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint-gated final differs from expected"
            )
        if self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "checkpoint corpus differs during verification"
            )
        if self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        ).payload != checkpoint_policy.canonical_payload:
            raise ArtifactIntegrityError(
                "checkpoint policy differs during verification"
            )
        if self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        ).payload != checkpoint_log.canonical_payload:
            raise ArtifactIntegrityError(
                "checkpoint log differs during verification"
            )
        for reference in evidence.checkpoint_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        report_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "credential-revocation-checkpoint-verification"
            ),
            report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != report_artifact.payload:
            raise ArtifactIntegrityError(
                "checkpoint verification differs during final verification"
            )
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
        checkpoints: tuple[
            CredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        corpus: CheckpointBoundRevocationCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedCheckpointGatedReceipt:
        """Return checkpoint verification plus downstream revocation outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                checkpoint_policy=checkpoint_policy,
                checkpoint_log=checkpoint_log,
                windows=windows,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=checkpoint_verified_at,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except ValueError as exc:
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            checkpoint_evidence = (
                load_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus,
                    policy=checkpoint_policy,
                    log=checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            CredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = validate_credential_revocation_checkpoints(
                plan=plan,
                corpus=corpus,
                policy=checkpoint_policy,
                log=checkpoint_log,
                ledger=ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=checkpoint_verified_at,
            )
        except (CredentialRevocationCheckpointError, ValueError) as exc:
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            revocation_receipt = self._runner.run(
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
                corpus=corpus.corpus,
                environment=environment,
                windows=windows,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except RevocationGatedExperimentError as exc:
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        final = CheckpointGatedFinalManifest(
            final_id=(
                f"{experiment_run_id}:revocation-checkpoint-completion"
                if revocation_receipt.terminal_outcome
                is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "revocation-checkpoint-terminal-abstention"
                )
            ),
            experiment_run_id=experiment_run_id,
            status=CheckpointGatedRunnerStatus.VERIFIED,
            revocation_outcome=revocation_receipt.revocation_outcome,
            terminal_outcome=revocation_receipt.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=checkpoint_evidence.corpus_ref,
            checkpoint_policy_ref=checkpoint_evidence.checkpoint_policy_ref,
            checkpoint_log_ref=checkpoint_evidence.checkpoint_log_ref,
            checkpoint_refs=checkpoint_evidence.checkpoint_refs,
            checkpoint_head_ref=checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_final_ref=revocation_receipt.final_manifest_ref,
            verified_checks=CHECKPOINT_GATED_VERIFIED_CHECKS,
            completed_at=revocation_receipt.completed_at,
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
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if revocation_receipt.terminal_outcome
                    is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                checkpoint_policy=checkpoint_policy,
                checkpoint_log=checkpoint_log,
                evidence=checkpoint_evidence,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointGatedExperimentError(
                CheckpointGatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if revocation_receipt.terminal_outcome
                    is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointGatedReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointGatedRunnerStatus.VERIFIED,
            revocation_outcome=revocation_receipt.revocation_outcome,
            terminal_outcome=revocation_receipt.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=checkpoint_evidence.corpus_ref,
            checkpoint_policy_ref=checkpoint_evidence.checkpoint_policy_ref,
            checkpoint_log_ref=checkpoint_evidence.checkpoint_log_ref,
            checkpoint_refs=checkpoint_evidence.checkpoint_refs,
            checkpoint_head_ref=checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_receipt=revocation_receipt,
            final_manifest_ref=final_ref,
            verified_checks=CHECKPOINT_GATED_VERIFIED_CHECKS,
            completed_at=revocation_receipt.completed_at,
        )
