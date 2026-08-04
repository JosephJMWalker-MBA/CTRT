"""Gate current conflict-adjudicator revocation on an immutable checkpoint."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints import (
    CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
    load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence,
    validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints,
)
from ctrt.current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot,
    RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_current_checkpoint_witness_conflict_runner import (
    CurrentCheckpointWitnessConflictAdjudicatorRevocationExperimentError,
    RevocationGatedCurrentCheckpointWitnessConflictExperimentRunner,
    VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

_ARTIFACT_PREFIX = (
    "current-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint"
)


class CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage(
    StrEnum
):
    """Boundary at which checkpoint-gated current revocation failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus(
    StrEnum
):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
    RuntimeError
):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: (
            CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage
        ),
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS = (
    "exact-1.21.0-current-conflict-adjudicator-revocation-predecessor-preserved",
    "exact-current-conflict-adjudicator-revocation-checkpoint-policy-bound",
    "exact-current-conflict-adjudicator-revocation-checkpoint-log-bound",
    "contiguous-current-conflict-adjudicator-revocation-checkpoint-chain-verified",
    "ordered-current-conflict-adjudicator-revocation-event-prefix-verified",
    "current-conflict-adjudicator-revocation-checkpoint-head-matches-ledger",
    "current-conflict-adjudicator-revocation-checkpoint-report-persisted-before-pr43",
    "checkpoint-and-all-pr43-outcomes-finalized-separately",
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
class CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointFinalManifest:
    """Final marker preserving checkpoint and every delegated outcome."""

    final_id: str
    experiment_run_id: str
    status: CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome
    current_conflict_adjudicator_credential_outcome: CredentialDecisionOutcome | None
    conflicting_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_resolution_status: WitnessConflictResolutionStatus | None
    current_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    resolved_current_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_revocation_outcome: CredentialDecisionOutcome | None
    current_credential_outcome: CredentialDecisionOutcome | None
    lower_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    lower_resolution_status: WitnessConflictResolutionStatus | None
    lower_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    lower_predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    checkpoint_corpus_ref: StoredArtifactRef
    predecessor_revocation_corpus_ref: VersionedArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoint_head_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    revocation_final_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("current conflict-adjudicator checkpoint must be verified")
        if not self.checkpoint_refs:
            raise ValueError("current conflict-adjudicator checkpoint requires checkpoints")
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError("current conflict-adjudicator checkpoint head must be final")
        suffix = (
            "completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        expected_id = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from checkpoint terminal outcome")
        if (
            self.verified_checks
            != CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("current conflict-adjudicator checkpoint final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt:
    """Proof of checkpoint verification plus the exact PR #43 result."""

    experiment_run_id: str
    status: CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome
    current_conflict_adjudicator_credential_outcome: CredentialDecisionOutcome | None
    conflicting_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_resolution_status: WitnessConflictResolutionStatus | None
    current_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    resolved_current_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_revocation_outcome: CredentialDecisionOutcome | None
    current_credential_outcome: CredentialDecisionOutcome | None
    lower_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    lower_resolution_status: WitnessConflictResolutionStatus | None
    lower_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    lower_predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    checkpoint_corpus_ref: StoredArtifactRef
    predecessor_revocation_corpus_ref: VersionedArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoint_head_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    revocation_receipt: (
        VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationReceipt
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("verified current conflict-adjudicator checkpoint required")
        delegated = self.revocation_receipt
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #43 receipt belongs to another experiment run")
        if (
            delegated.current_conflict_adjudicator_revocation_outcome
            is not self.current_conflict_adjudicator_revocation_outcome
            or delegated.current_conflict_adjudicator_credential_outcome
            is not self.current_conflict_adjudicator_credential_outcome
            or delegated.conflicting_witness_outcome
            is not self.conflicting_witness_outcome
            or delegated.current_resolution_status is not self.current_resolution_status
            or delegated.current_conflict_adjudication_outcome
            is not self.current_conflict_adjudication_outcome
            or delegated.resolved_current_witness_outcome
            is not self.resolved_current_witness_outcome
            or delegated.current_revocation_outcome
            is not self.current_revocation_outcome
            or delegated.current_credential_outcome
            is not self.current_credential_outcome
            or delegated.lower_checkpoint_witness_outcome
            is not self.lower_checkpoint_witness_outcome
            or delegated.lower_resolution_status is not self.lower_resolution_status
            or delegated.lower_conflict_adjudication_outcome
            is not self.lower_conflict_adjudication_outcome
            or delegated.lower_predecessor_witness_outcome
            is not self.lower_predecessor_witness_outcome
            or delegated.inherited_revocation_outcome
            is not self.inherited_revocation_outcome
            or delegated.inherited_credential_outcome
            is not self.inherited_credential_outcome
            or delegated.inherited_checkpoint_witness_outcome
            is not self.inherited_checkpoint_witness_outcome
            or delegated.inherited_resolution_status
            is not self.inherited_resolution_status
            or delegated.inherited_adjudication_outcome
            is not self.inherited_adjudication_outcome
            or delegated.terminal_outcome is not self.terminal_outcome
        ):
            raise ValueError("PR #43 receipt differs from checkpoint receipt")
        suffix = (
            "completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        expected_id = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong checkpoint outcome")
        if (
            self.verified_checks
            != CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("verified current conflict-adjudicator checkpoint lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner:
    """Verify the exact 1.21.0 ledger checkpoint before PR #43."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = RevocationGatedCurrentCheckpointWitnessConflictExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: (
            CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
        ),
        revocation_corpus: (
            RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
        ),
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        revocation_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-gated current revocation requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match current checkpoint corpus exactly")
        if corpus.predecessor_corpus_ref != revocation_corpus.reference():
            raise ValueError("checkpoint corpus must bind exact 1.21.0 predecessor")
        if corpus.corpus.reference() != revocation_corpus.reference():
            raise ValueError("checkpoint corpus carries different 1.21.0 predecessor")
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("current checkpoint policy differs from corpus")
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("current checkpoint log differs from corpus")
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("current checkpoint head differs from log")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        verified_time = _parse_timestamp(
            checkpoint_verified_at,
            "checkpoint_verified_at",
        )
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        revocation_completed_time = _parse_timestamp(
            revocation_completed_at,
            "revocation_completed_at",
        )
        completed_time = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= verified_time
            <= revocation_time
            <= revocation_completed_time
            <= completed_time
        ):
            raise ValueError(
                "successor, checkpoint, revocation, and completion chronology differs"
            )

    def _persist_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-verification"
        artifact = serialize_artifact(artifact_id, report)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored current checkpoint report differs")
        return reference

    def _verify_final(
        self,
        *,
        final: (
            CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointFinalManifest
        ),
        final_ref: StoredArtifactRef,
        corpus: (
            CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
        ),
        revocation_corpus: (
            RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
        ),
        policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored current checkpoint final differs")
        if self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.22.0 checkpoint corpus differs")
        predecessor = self._store.get(
            revocation_corpus.reference().artifact_id,
            expected_hash=revocation_corpus.reference().artifact_hash,
        )
        if predecessor.payload != revocation_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.21.0 revocation corpus differs")
        if self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored current checkpoint policy differs")
        if self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        ).payload != log.canonical_payload:
            raise ArtifactIntegrityError("stored current checkpoint log differs")
        for reference in evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        expected_report = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-verification",
            report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != expected_report.payload:
            raise ArtifactIntegrityError("stored current checkpoint report differs")
        self._store.get(
            final.revocation_final_ref.artifact_id,
            expected_hash=final.revocation_final_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: (
            CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
        ),
        current_revocation_corpus: (
            RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
        ),
        current_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        current_checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        current_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        current_conflict_adjudicator_revocation_ledger: (
            AdjudicatorCredentialRevocationLedgerSnapshot
        ),
        experiment_run_id: str,
        current_checkpoint_verified_at: str,
        current_conflict_adjudicator_revocation_evaluated_at: str,
        revocation_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt:
        """Return checkpoint verification plus the exact delegated PR #43 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_corpus=current_revocation_corpus,
                checkpoint_policy=current_checkpoint_policy,
                checkpoint_log=current_checkpoint_log,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=current_checkpoint_verified_at,
                revocation_evaluated_at=(
                    current_conflict_adjudicator_revocation_evaluated_at
                ),
                revocation_completed_at=revocation_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = (
                load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus,
                    policy=current_checkpoint_policy,
                    log=current_checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = (
                validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints(
                    plan=plan,
                    corpus=corpus,
                    policy=current_checkpoint_policy,
                    log=current_checkpoint_log,
                    ledger=current_conflict_adjudicator_revocation_ledger,
                    checkpoints=current_checkpoints,
                    verified_at=current_checkpoint_verified_at,
                    revocation_evaluated_at=(
                        current_conflict_adjudicator_revocation_evaluated_at
                    ),
                )
            )
        except (
            AdjudicatorCredentialRevocationCheckpointError,
            ValueError,
        ) as exc:
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        revocation_plan = replace(
            plan,
            corpus_ref=current_revocation_corpus.reference(),
            content_ids=current_revocation_corpus.content_ids,
        )
        try:
            delegated_receipt = self._runner.run(
                plan=revocation_plan,
                corpus=current_revocation_corpus,
                current_conflict_adjudicator_revocation_ledger=(
                    current_conflict_adjudicator_revocation_ledger
                ),
                experiment_run_id=experiment_run_id,
                current_conflict_adjudicator_revocation_evaluated_at=(
                    current_conflict_adjudicator_revocation_evaluated_at
                ),
                completed_at=revocation_completed_at,
                **delegated,
            )
        except CurrentCheckpointWitnessConflictAdjudicatorRevocationExperimentError as exc:
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        suffix = (
            "completion"
            if delegated_receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
            ),
            current_conflict_adjudicator_revocation_outcome=(
                delegated_receipt.current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                delegated_receipt.current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=(
                delegated_receipt.conflicting_witness_outcome
            ),
            current_resolution_status=delegated_receipt.current_resolution_status,
            current_conflict_adjudication_outcome=(
                delegated_receipt.current_conflict_adjudication_outcome
            ),
            resolved_current_witness_outcome=(
                delegated_receipt.resolved_current_witness_outcome
            ),
            current_revocation_outcome=delegated_receipt.current_revocation_outcome,
            current_credential_outcome=delegated_receipt.current_credential_outcome,
            lower_checkpoint_witness_outcome=(
                delegated_receipt.lower_checkpoint_witness_outcome
            ),
            lower_resolution_status=delegated_receipt.lower_resolution_status,
            lower_conflict_adjudication_outcome=(
                delegated_receipt.lower_conflict_adjudication_outcome
            ),
            lower_predecessor_witness_outcome=(
                delegated_receipt.lower_predecessor_witness_outcome
            ),
            inherited_revocation_outcome=(
                delegated_receipt.inherited_revocation_outcome
            ),
            inherited_credential_outcome=(
                delegated_receipt.inherited_credential_outcome
            ),
            inherited_checkpoint_witness_outcome=(
                delegated_receipt.inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=(
                delegated_receipt.inherited_resolution_status
            ),
            inherited_adjudication_outcome=(
                delegated_receipt.inherited_adjudication_outcome
            ),
            terminal_outcome=delegated_receipt.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            predecessor_revocation_corpus_ref=corpus.predecessor_corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=evidence.checkpoint_refs[-1],
            checkpoint_verification_ref=report_ref,
            revocation_final_ref=delegated_receipt.final_manifest_ref,
            verified_checks=(
                CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
            ),
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
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated_receipt.terminal_outcome
                    is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                revocation_corpus=current_revocation_corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
                evidence=evidence,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated_receipt.terminal_outcome
                    is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt(
            experiment_run_id=experiment_run_id,
            status=(
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
            ),
            current_conflict_adjudicator_revocation_outcome=(
                delegated_receipt.current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                delegated_receipt.current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=(
                delegated_receipt.conflicting_witness_outcome
            ),
            current_resolution_status=delegated_receipt.current_resolution_status,
            current_conflict_adjudication_outcome=(
                delegated_receipt.current_conflict_adjudication_outcome
            ),
            resolved_current_witness_outcome=(
                delegated_receipt.resolved_current_witness_outcome
            ),
            current_revocation_outcome=delegated_receipt.current_revocation_outcome,
            current_credential_outcome=delegated_receipt.current_credential_outcome,
            lower_checkpoint_witness_outcome=(
                delegated_receipt.lower_checkpoint_witness_outcome
            ),
            lower_resolution_status=delegated_receipt.lower_resolution_status,
            lower_conflict_adjudication_outcome=(
                delegated_receipt.lower_conflict_adjudication_outcome
            ),
            lower_predecessor_witness_outcome=(
                delegated_receipt.lower_predecessor_witness_outcome
            ),
            inherited_revocation_outcome=(
                delegated_receipt.inherited_revocation_outcome
            ),
            inherited_credential_outcome=(
                delegated_receipt.inherited_credential_outcome
            ),
            inherited_checkpoint_witness_outcome=(
                delegated_receipt.inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=(
                delegated_receipt.inherited_resolution_status
            ),
            inherited_adjudication_outcome=(
                delegated_receipt.inherited_adjudication_outcome
            ),
            terminal_outcome=delegated_receipt.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            predecessor_revocation_corpus_ref=corpus.predecessor_corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=evidence.checkpoint_refs[-1],
            checkpoint_verification_ref=report_ref,
            revocation_receipt=delegated_receipt,
            final_manifest_ref=final_ref,
            verified_checks=(
                CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
    "CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointFinalManifest",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus",
    "VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt",
]
