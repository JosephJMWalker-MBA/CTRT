"""Gate the exact `1.26.0` revocation graph on an immutable checkpoint."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from importlib import import_module
from typing import Any

from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_current_revocation_checkpoint_witness_conflict_runner import (
    CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError,
    RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner,
    VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

_contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
)
CheckpointCorpus = vars(_contract)[
    "CheckpointBoundCurrentRevocationCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationCorpusSnapshot"
]
load_checkpoint_evidence = vars(_contract)[
    "load_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_evidence"
]
validate_checkpoints = vars(_contract)[
    "validate_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
]

_ARTIFACT_PREFIX = (
    "current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint"
)

VERIFIED_CHECKS = (
    "exact-1.26.0-current-revocation-conflict-adjudicator-predecessor-preserved",
    "exact-current-revocation-conflict-adjudicator-checkpoint-policy-bound",
    "exact-current-revocation-conflict-adjudicator-checkpoint-log-bound",
    "contiguous-current-revocation-conflict-adjudicator-checkpoint-chain-verified",
    "ordered-current-revocation-conflict-adjudicator-event-prefix-verified",
    "current-revocation-conflict-adjudicator-checkpoint-head-matches-ledger",
    "current-revocation-conflict-adjudicator-report-persisted-before-pr48",
    "checkpoint-and-all-pr48-outcomes-finalized-separately",
)


class CheckpointRunnerStage(StrEnum):
    """Boundary at which checkpoint-gated current revocation failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CheckpointExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


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


def _outcomes(value: Any) -> tuple[Any, ...]:
    """Return every PR #48 and inherited outcome without aggregation."""

    return (
        value.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome,
        value.current_revocation_checkpoint_conflict_adjudicator_credential_outcome,
        value.conflicting_current_revocation_checkpoint_witness_outcome,
        value.current_revocation_checkpoint_resolution_status,
        value.current_revocation_checkpoint_conflict_adjudication_outcome,
        value.resolved_current_revocation_checkpoint_witness_outcome,
        value.current_conflict_adjudicator_revocation_outcome,
        value.current_conflict_adjudicator_credential_outcome,
        value.conflicting_witness_outcome,
        value.current_resolution_status,
        value.current_conflict_adjudication_outcome,
        value.resolved_current_witness_outcome,
        value.current_revocation_outcome,
        value.current_credential_outcome,
        value.lower_checkpoint_witness_outcome,
        value.lower_resolution_status,
        value.lower_conflict_adjudication_outcome,
        value.lower_predecessor_witness_outcome,
        value.inherited_revocation_outcome,
        value.inherited_credential_outcome,
        value.inherited_checkpoint_witness_outcome,
        value.inherited_resolution_status,
        value.inherited_adjudication_outcome,
    )


@dataclass(frozen=True, slots=True)
class CheckpointFinalManifest:
    """Final marker preserving checkpoint and every delegated outcome."""

    final_id: str
    experiment_run_id: str
    status: CheckpointRunnerStatus
    current_revocation_checkpoint_conflict_adjudicator_revocation_outcome: (
        CredentialDecisionOutcome
    )
    current_revocation_checkpoint_conflict_adjudicator_credential_outcome: (
        CredentialDecisionOutcome | None
    )
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_revocation_checkpoint_resolution_status: (
        WitnessConflictResolutionStatus | None
    )
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome | None
    )
    resolved_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome | None
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
        if self.status is not CheckpointRunnerStatus.VERIFIED:
            raise ValueError("current revocation conflict checkpoint must be verified")
        if not self.checkpoint_refs:
            raise ValueError("current revocation conflict checkpoint requires checkpoints")
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError("checkpoint head must be the final checkpoint")
        suffix = (
            "completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        expected_id = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from checkpoint terminal outcome")
        if self.verified_checks != VERIFIED_CHECKS:
            raise ValueError("current revocation conflict checkpoint lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointReceipt:
    """Proof of checkpoint verification plus the exact PR #48 result."""

    experiment_run_id: str
    status: CheckpointRunnerStatus
    current_revocation_checkpoint_conflict_adjudicator_revocation_outcome: (
        CredentialDecisionOutcome
    )
    current_revocation_checkpoint_conflict_adjudicator_credential_outcome: (
        CredentialDecisionOutcome | None
    )
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_revocation_checkpoint_resolution_status: (
        WitnessConflictResolutionStatus | None
    )
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome | None
    )
    resolved_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome | None
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
        VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointRunnerStatus.VERIFIED:
            raise ValueError("verified current revocation conflict checkpoint required")
        delegated = self.revocation_receipt
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #48 receipt belongs to another experiment run")
        if _outcomes(delegated) != _outcomes(self):
            raise ValueError("PR #48 receipt differs from checkpoint receipt")
        if delegated.terminal_outcome is not self.terminal_outcome:
            raise ValueError("PR #48 terminal outcome differs")
        suffix = (
            "completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        expected_id = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong checkpoint outcome")
        if self.verified_checks != VERIFIED_CHECKS:
            raise ValueError("verified current revocation conflict checkpoint lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner:
    """Verify the exact `1.26.0` ledger checkpoint before PR #48."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = (
            RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner(
                artifact_store=artifact_store
            )
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        revocation_corpus: Any,
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
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan must match checkpoint corpus exactly")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order differs from checkpoint corpus")
        if corpus.predecessor_corpus_ref != revocation_corpus.reference():
            raise ValueError("checkpoint corpus must bind exact 1.26.0 predecessor")
        if corpus.corpus.reference() != revocation_corpus.reference():
            raise ValueError("checkpoint corpus carries different 1.26.0 predecessor")
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("checkpoint policy differs from corpus")
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("checkpoint log differs from corpus")
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("checkpoint head differs from log")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        verified_time = _parse_timestamp(
            checkpoint_verified_at,
            "checkpoint_verified_at",
        )
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        revocation_completed = _parse_timestamp(
            revocation_completed_at,
            "revocation_completed_at",
        )
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= verified_time
            <= revocation_time
            <= revocation_completed
            <= completed
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
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: Any,
        revocation_corpus: Any,
        policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored_final = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored_final.payload != expected.payload:
            raise ArtifactIntegrityError("stored checkpoint final differs")
        stored_corpus = self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.27.0 checkpoint corpus differs")
        predecessor = self._store.get(
            revocation_corpus.reference().artifact_id,
            expected_hash=revocation_corpus.reference().artifact_hash,
        )
        if predecessor.payload != revocation_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.26.0 revocation corpus differs")
        stored_policy = self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        )
        if stored_policy.payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored checkpoint policy differs")
        stored_log = self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        )
        if stored_log.payload != log.canonical_payload:
            raise ArtifactIntegrityError("stored checkpoint log differs")
        for reference in evidence.checkpoint_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_report = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-verification",
            report,
        )
        stored_report = self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        )
        if stored_report.payload != expected_report.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        self._store.get(
            final.revocation_final_ref.artifact_id,
            expected_hash=final.revocation_final_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: Any,
        current_revocation_corpus: Any,
        current_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        current_checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        current_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        current_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        current_checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        revocation_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> VerifiedCheckpointReceipt:
        """Return checkpoint verification plus exact delegated PR #48 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_corpus=current_revocation_corpus,
                checkpoint_policy=current_checkpoint_policy,
                checkpoint_log=current_checkpoint_log,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=current_checkpoint_verified_at,
                revocation_evaluated_at=current_revocation_evaluated_at,
                revocation_completed_at=revocation_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointExperimentError(
                CheckpointRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_checkpoint_evidence(
                self._store,
                corpus=corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointExperimentError(
                CheckpointRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = validate_checkpoints(
                plan=plan,
                corpus=corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
                ledger=current_revocation_ledger,
                checkpoints=current_checkpoints,
                verified_at=current_checkpoint_verified_at,
                revocation_evaluated_at=current_revocation_evaluated_at,
            )
        except (
            AdjudicatorCredentialRevocationCheckpointError,
            ValueError,
        ) as exc:
            raise CheckpointExperimentError(
                CheckpointRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CheckpointExperimentError(
                CheckpointRunnerStage.REPORT_PERSISTENCE,
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
                revocation_ledger=current_revocation_ledger,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=current_revocation_evaluated_at,
                completed_at=revocation_completed_at,
                **delegated,
            )
        except (
            CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError
        ) as exc:
            raise CheckpointExperimentError(
                CheckpointRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        values = _outcomes(delegated_receipt)
        suffix = (
            "completion"
            if delegated_receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CheckpointFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointRunnerStatus.VERIFIED,
            current_revocation_checkpoint_conflict_adjudicator_revocation_outcome=values[0],
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome=values[1],
            conflicting_current_revocation_checkpoint_witness_outcome=values[2],
            current_revocation_checkpoint_resolution_status=values[3],
            current_revocation_checkpoint_conflict_adjudication_outcome=values[4],
            resolved_current_revocation_checkpoint_witness_outcome=values[5],
            current_conflict_adjudicator_revocation_outcome=values[6],
            current_conflict_adjudicator_credential_outcome=values[7],
            conflicting_witness_outcome=values[8],
            current_resolution_status=values[9],
            current_conflict_adjudication_outcome=values[10],
            resolved_current_witness_outcome=values[11],
            current_revocation_outcome=values[12],
            current_credential_outcome=values[13],
            lower_checkpoint_witness_outcome=values[14],
            lower_resolution_status=values[15],
            lower_conflict_adjudication_outcome=values[16],
            lower_predecessor_witness_outcome=values[17],
            inherited_revocation_outcome=values[18],
            inherited_credential_outcome=values[19],
            inherited_checkpoint_witness_outcome=values[20],
            inherited_resolution_status=values[21],
            inherited_adjudication_outcome=values[22],
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
            verified_checks=VERIFIED_CHECKS,
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
            completed_ids = (
                plan.content_ids
                if delegated_receipt.terminal_outcome
                is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise CheckpointExperimentError(
                CheckpointRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=completed_ids,
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
            completed_ids = (
                plan.content_ids
                if delegated_receipt.terminal_outcome
                is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise CheckpointExperimentError(
                CheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        return VerifiedCheckpointReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointRunnerStatus.VERIFIED,
            current_revocation_checkpoint_conflict_adjudicator_revocation_outcome=values[0],
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome=values[1],
            conflicting_current_revocation_checkpoint_witness_outcome=values[2],
            current_revocation_checkpoint_resolution_status=values[3],
            current_revocation_checkpoint_conflict_adjudication_outcome=values[4],
            resolved_current_revocation_checkpoint_witness_outcome=values[5],
            current_conflict_adjudicator_revocation_outcome=values[6],
            current_conflict_adjudicator_credential_outcome=values[7],
            conflicting_witness_outcome=values[8],
            current_resolution_status=values[9],
            current_conflict_adjudication_outcome=values[10],
            resolved_current_witness_outcome=values[11],
            current_revocation_outcome=values[12],
            current_credential_outcome=values[13],
            lower_checkpoint_witness_outcome=values[14],
            lower_resolution_status=values[15],
            lower_conflict_adjudication_outcome=values[16],
            lower_predecessor_witness_outcome=values[17],
            inherited_revocation_outcome=values[18],
            inherited_credential_outcome=values[19],
            inherited_checkpoint_witness_outcome=values[20],
            inherited_resolution_status=values[21],
            inherited_adjudication_outcome=values[22],
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
            verified_checks=VERIFIED_CHECKS,
            completed_at=completed_at,
        )


_LONG_CHECKS = (
    "CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_"
    "REVOCATION_CHECKPOINT_VERIFIED_CHECKS"
)
_LONG_ERROR = (
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointExperimentError"
)
_LONG_FINAL = (
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointFinalManifest"
)
_LONG_STAGE = (
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointRunnerStage"
)
_LONG_STATUS = (
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointRunnerStatus"
)
_LONG_RECEIPT = (
    "VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicator"
    "RevocationCheckpointReceipt"
)

globals()[_LONG_CHECKS] = VERIFIED_CHECKS
globals()[_LONG_ERROR] = CheckpointExperimentError
globals()[_LONG_FINAL] = CheckpointFinalManifest
globals()[_LONG_STAGE] = CheckpointRunnerStage
globals()[_LONG_STATUS] = CheckpointRunnerStatus
globals()[_LONG_RECEIPT] = VerifiedCheckpointReceipt

__all__ = [
    _LONG_CHECKS,
    "CheckpointGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
    _LONG_ERROR,
    _LONG_FINAL,
    _LONG_STAGE,
    _LONG_STATUS,
    _LONG_RECEIPT,
]
