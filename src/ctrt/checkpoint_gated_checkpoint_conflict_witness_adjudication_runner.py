"""Gate witness-conflict adjudicator revocation on an immutable checkpoint."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CheckpointExecutor,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential import (
    CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
    load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_evidence,
    validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.revocation_gated_checkpoint_conflict_witness_adjudication_runner import (
    CheckpointConflictWitnessRevocationExperimentError,
    RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner,
    VerifiedCheckpointConflictWitnessRevocationReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)

CheckpointCorpus = (
    CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
)
RevocationCorpus = (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
)


class CheckpointConflictWitnessRevocationCheckpointRunnerStage(StrEnum):
    """Boundary at which checkpoint-gated revocation execution failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictWitnessRevocationCheckpointRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CheckpointConflictWitnessRevocationCheckpointExperimentError(RuntimeError):
    """Fail-closed error preserving the exact failed stage."""

    def __init__(
        self,
        stage: CheckpointConflictWitnessRevocationCheckpointRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS = (
    "exact-witness-conflict-adjudicator-revocation-checkpoint-policy-bound",
    "exact-witness-conflict-adjudicator-revocation-checkpoint-log-bound",
    "contiguous-witness-conflict-adjudicator-revocation-checkpoint-chain-verified",
    "ordered-witness-conflict-adjudicator-revocation-event-prefix-verified",
    "witness-conflict-adjudicator-revocation-checkpoint-head-matches-ledger",
    "witness-conflict-adjudicator-revocation-checkpoint-report-persisted",
    "checkpoint-and-revocation-outcomes-finalized-separately",
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
class CheckpointConflictWitnessRevocationCheckpointFinalManifest:
    """Final marker for checkpoint verification plus delegated revocation."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictWitnessRevocationCheckpointRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
            CheckpointConflictWitnessRevocationCheckpointRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("witness-conflict revocation checkpoint must be verified")
        if not self.checkpoint_refs:
            raise ValueError("checkpoint final requires at least one checkpoint")
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError("checkpoint final head must be its final checkpoint")
        suffix = (
            "completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        expected_id = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            f"{suffix}"
        )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from checkpoint terminal outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint final lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt:
    """Proof of checkpoint verification plus the exact PR #33 result."""

    experiment_run_id: str
    status: CheckpointConflictWitnessRevocationCheckpointRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
    revocation_receipt: VerifiedCheckpointConflictWitnessRevocationReceipt
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CheckpointConflictWitnessRevocationCheckpointRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("verified checkpoint receipt status required")
        delegated = self.revocation_receipt
        if (
            delegated.revocation_outcome is not self.revocation_outcome
            or delegated.credential_outcome is not self.credential_outcome
            or delegated.checkpoint_witness_outcome
            is not self.checkpoint_witness_outcome
            or delegated.resolution_status is not self.resolution_status
            or delegated.adjudication_outcome is not self.adjudication_outcome
            or delegated.terminal_outcome is not self.terminal_outcome
        ):
            raise ValueError("revocation receipt differs from checkpoint receipt")
        suffix = (
            "completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        expected_id = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            f"{suffix}"
        )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong checkpoint outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint receipt lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner:
    """Verify the exact 1.11.0 ledger checkpoint before PR #33."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CheckpointCorpus,
        revocation_corpus: RevocationCorpus,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-gated revocation requires a frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match checkpoint-bound corpus exactly")
        if corpus.predecessor_corpus_ref != revocation_corpus.reference():
            raise ValueError("checkpoint corpus must bind exact 1.11.0 predecessor")
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("checkpoint policy reference differs from corpus")
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("checkpoint log reference differs from corpus")
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("checkpoint head reference differs from log")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        verified_time = _parse_timestamp(
            checkpoint_verified_at,
            "checkpoint_verified_at",
        )
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        completed_time = _parse_timestamp(completed_at, "completed_at")
        if not successor_time <= verified_time <= revocation_time <= completed_time:
            raise ValueError(
                "successor, checkpoint, revocation, and completion chronology differs"
            )

    def _persist_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-verification"
        )
        artifact = serialize_artifact(artifact_id, report)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictWitnessRevocationCheckpointFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CheckpointCorpus,
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
            raise ArtifactIntegrityError("stored checkpoint final differs")
        if self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored checkpoint corpus differs")
        if self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored checkpoint policy differs")
        if self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        ).payload != log.canonical_payload:
            raise ArtifactIntegrityError("stored checkpoint log differs")
        for reference in evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        report_id = (
            f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-verification"
        )
        expected_report = serialize_artifact(report_id, report)
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != expected_report.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        self._store.get(
            final.revocation_final_ref.artifact_id,
            expected_hash=final.revocation_final_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: CheckpointCorpus,
        revocation_corpus: RevocationCorpus,
        credential_corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        checkpoints: tuple[AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        adjudication_evaluated_at: str,
        adjudication_completed_at: str,
        credential_completed_at: str,
        revocation_completed_at: str,
        completed_at: str,
    ) -> VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt:
        """Return checkpoint verification plus the exact delegated PR #33 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_corpus=revocation_corpus,
                checkpoint_policy=checkpoint_policy,
                checkpoint_log=checkpoint_log,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=checkpoint_verified_at,
                revocation_evaluated_at=revocation_evaluated_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = (
                load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus,
                    policy=checkpoint_policy,
                    log=checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = (
                validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints(
                    plan=plan,
                    corpus=corpus,
                    policy=checkpoint_policy,
                    log=checkpoint_log,
                    ledger=revocation_ledger,
                    checkpoints=evidence.checkpoints,
                    verified_at=checkpoint_verified_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                )
            )
        except (AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        delegated_plan = replace(
            plan,
            corpus_ref=revocation_corpus.reference(),
            content_ids=revocation_corpus.content_ids,
        )
        try:
            delegated = self._runner.run(
                plan=delegated_plan,
                corpus=revocation_corpus,
                credential_corpus=credential_corpus,
                adjudication_corpus=adjudication_corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                witness_attestations=witness_attestations,
                head_checkpoint=head_checkpoint,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                adjudication=adjudication,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                revocation_events=revocation_events,
                witness_receipt=witness_receipt,
                checkpoint_executor=checkpoint_executor,
                experiment_run_id=experiment_run_id,
                witness_evaluated_at=witness_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                adjudication_evaluated_at=adjudication_evaluated_at,
                adjudication_completed_at=adjudication_completed_at,
                credential_completed_at=credential_completed_at,
                completed_at=revocation_completed_at,
            )
        except CheckpointConflictWitnessRevocationExperimentError as exc:
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        suffix = (
            "completion"
            if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            f"{suffix}"
        )
        final = CheckpointConflictWitnessRevocationCheckpointFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessRevocationCheckpointRunnerStatus.VERIFIED,
            revocation_outcome=delegated.revocation_outcome,
            credential_outcome=delegated.credential_outcome,
            checkpoint_witness_outcome=delegated.checkpoint_witness_outcome,
            resolution_status=delegated.resolution_status,
            adjudication_outcome=delegated.adjudication_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            predecessor_revocation_corpus_ref=corpus.predecessor_corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_final_ref=delegated.final_manifest_ref,
            verified_checks=(
                CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
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
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.FINAL_PERSISTENCE,
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
                policy=checkpoint_policy,
                log=checkpoint_log,
                evidence=evidence,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictWitnessRevocationCheckpointExperimentError(
                CheckpointConflictWitnessRevocationCheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessRevocationCheckpointRunnerStatus.VERIFIED,
            revocation_outcome=delegated.revocation_outcome,
            credential_outcome=delegated.credential_outcome,
            checkpoint_witness_outcome=delegated.checkpoint_witness_outcome,
            resolution_status=delegated.resolution_status,
            adjudication_outcome=delegated.adjudication_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            predecessor_revocation_corpus_ref=corpus.predecessor_corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=(
                CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
    "CheckpointConflictWitnessRevocationCheckpointExperimentError",
    "CheckpointConflictWitnessRevocationCheckpointFinalManifest",
    "CheckpointConflictWitnessRevocationCheckpointRunnerStage",
    "CheckpointConflictWitnessRevocationCheckpointRunnerStatus",
    "CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner",
    "VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt",
]
