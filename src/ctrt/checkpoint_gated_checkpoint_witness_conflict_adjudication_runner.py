"""Gate current adjudicator revocation on an immutable ledger checkpoint."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

import ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints as cp
from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CheckpointExecutor,
)
from ctrt.adjudicator_credential_attestation import AdjudicatorCredentialPolicySnapshot
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
from ctrt.checkpoint_witness_conflict_adjudicator_credential import (
    CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
    CredentialPolicySnapshot,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
    validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints import (
    load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence as load_current_checkpoint_evidence,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_ledger import (
    RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.revocation_gated_checkpoint_witness_conflict_adjudication_runner import (
    CheckpointWitnessConflictRevocationExperimentError,
    RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner,
    VerifiedCheckpointWitnessConflictRevocationReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness import (
    WitnessBoundCheckpointCorpusSnapshot,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCheckpointWitnessCorpusSnapshot,
)
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)

CurrentCheckpointCorpus = (
    CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
)
CurrentRevocationCorpus = (
    RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
)
InheritedCheckpointCorpus = (
    cp.CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
)
InheritedCheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
InheritedCheckpointPolicy = cp.AdjudicatorCredentialRevocationCheckpointPolicySnapshot
InheritedCheckpointLog = cp.AdjudicatorCredentialRevocationCheckpointLogSnapshot
InheritedRevocationCorpus = (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
)

_ARTIFACT_PREFIX = (
    "checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint"
)


class CheckpointWitnessConflictRevocationCheckpointRunnerStage(StrEnum):
    """Boundary at which checkpoint-gated current revocation failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointWitnessConflictRevocationCheckpointRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CheckpointWitnessConflictRevocationCheckpointExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointWitnessConflictRevocationCheckpointRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS = (
    "exact-1.16.0-current-revocation-predecessor-preserved",
    "exact-current-revocation-checkpoint-policy-bound",
    "exact-current-revocation-checkpoint-log-bound",
    "contiguous-current-revocation-checkpoint-chain-verified",
    "ordered-current-revocation-event-prefix-verified",
    "current-revocation-checkpoint-head-matches-ledger",
    "current-revocation-checkpoint-report-persisted-before-pr38",
    "checkpoint-and-all-delegated-outcomes-finalized-separately",
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
class CheckpointWitnessConflictRevocationCheckpointFinalManifest:
    """Final marker preserving checkpoint and every delegated outcome."""

    final_id: str
    experiment_run_id: str
    status: CheckpointWitnessConflictRevocationCheckpointRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
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
            CheckpointWitnessConflictRevocationCheckpointRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("current revocation checkpoint must be verified")
        if not self.checkpoint_refs:
            raise ValueError("current revocation checkpoint requires checkpoints")
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError("current revocation checkpoint head must be final")
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
            != CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("current revocation checkpoint final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt:
    """Proof of current checkpoint verification plus exact PR #38 result."""

    experiment_run_id: str
    status: CheckpointWitnessConflictRevocationCheckpointRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
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
    revocation_receipt: VerifiedCheckpointWitnessConflictRevocationReceipt
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CheckpointWitnessConflictRevocationCheckpointRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("verified current revocation checkpoint required")
        delegated = self.revocation_receipt
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #38 receipt belongs to another experiment run")
        if (
            delegated.revocation_outcome is not self.revocation_outcome
            or delegated.credential_outcome is not self.credential_outcome
            or delegated.checkpoint_witness_outcome
            is not self.checkpoint_witness_outcome
            or delegated.resolution_status is not self.resolution_status
            or delegated.conflict_adjudication_outcome
            is not self.conflict_adjudication_outcome
            or delegated.predecessor_witness_outcome
            is not self.predecessor_witness_outcome
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
            raise ValueError("PR #38 receipt differs from checkpoint receipt")
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
            != CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("verified current revocation checkpoint lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner:
    """Verify the exact 1.16.0 ledger checkpoint before PR #38."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = (
            RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner(
                artifact_store=artifact_store
            )
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CurrentCheckpointCorpus,
        revocation_corpus: CurrentRevocationCorpus,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-gated current revocation requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match current checkpoint corpus exactly")
        if corpus.predecessor_corpus_ref != revocation_corpus.reference():
            raise ValueError("checkpoint corpus must bind exact 1.16.0 predecessor")
        if corpus.corpus.reference() != revocation_corpus.reference():
            raise ValueError("checkpoint corpus carries different 1.16.0 predecessor")
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
            current_revocation_evaluated_at,
            "current_revocation_evaluated_at",
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
        final: CheckpointWitnessConflictRevocationCheckpointFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CurrentCheckpointCorpus,
        revocation_corpus: CurrentRevocationCorpus,
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
            raise ArtifactIntegrityError("stored 1.17.0 checkpoint corpus differs")
        predecessor = self._store.get(
            revocation_corpus.reference().artifact_id,
            expected_hash=revocation_corpus.reference().artifact_hash,
        )
        if predecessor.payload != revocation_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.16.0 revocation corpus differs")
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
        corpus: CurrentCheckpointCorpus,
        current_revocation_corpus: CurrentRevocationCorpus,
        credential_corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessBoundCheckpointCorpusSnapshot,
        checkpoint_corpus: InheritedCheckpointCorpus,
        revocation_corpus: InheritedRevocationCorpus,
        inherited_credential_corpus: (
            CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
        ),
        inherited_adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        current_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        current_checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        current_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        checkpoint_policy: InheritedCheckpointPolicy,
        checkpoint_log: InheritedCheckpointLog,
        checkpoints: tuple[InheritedCheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        predecessor_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        current_issuer_registry: CredentialIssuerRegistrySnapshot,
        current_credential_policy: CredentialPolicySnapshot,
        current_revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        current_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        current_revocation_events: tuple[
            AdjudicatorCredentialRevocationEventSnapshot, ...
        ],
        inherited_witness_registry: CheckpointWitnessRegistrySnapshot,
        inherited_witness_policy: CheckpointWitnessPolicySnapshot,
        inherited_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        inherited_head_checkpoint: InheritedCheckpointSnapshot,
        inherited_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        inherited_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        inherited_adjudication: WitnessConflictAdjudicationSnapshot,
        inherited_issuer_registry: CredentialIssuerRegistrySnapshot,
        inherited_credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        inherited_witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        current_checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        current_credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_verified_at: str,
        predecessor_witness_evaluated_at: str,
        inherited_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        inherited_credential_evaluated_at: str,
        inherited_adjudication_evaluated_at: str,
        inherited_adjudication_completed_at: str,
        inherited_credential_completed_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        prior_completed_at: str,
        current_revocation_completed_at: str,
        completed_at: str,
    ) -> VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt:
        """Return checkpoint verification plus exact delegated PR #38 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_corpus=current_revocation_corpus,
                checkpoint_policy=current_checkpoint_policy,
                checkpoint_log=current_checkpoint_log,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=current_checkpoint_verified_at,
                current_revocation_evaluated_at=current_revocation_evaluated_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_current_checkpoint_evidence(
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
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = (
                validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints(
                    plan=plan,
                    corpus=corpus,
                    policy=current_checkpoint_policy,
                    log=current_checkpoint_log,
                    ledger=current_revocation_ledger,
                    checkpoints=evidence.checkpoints,
                    verified_at=current_checkpoint_verified_at,
                    revocation_evaluated_at=current_revocation_evaluated_at,
                )
            )
        except (AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        delegated_plan = replace(
            plan,
            corpus_ref=current_revocation_corpus.reference(),
            content_ids=current_revocation_corpus.content_ids,
        )
        try:
            delegated = self._runner.run(
                plan=delegated_plan,
                corpus=current_revocation_corpus,
                credential_corpus=credential_corpus,
                adjudication_corpus=adjudication_corpus,
                witness_predecessor=witness_predecessor,
                checkpoint_corpus=checkpoint_corpus,
                revocation_corpus=revocation_corpus,
                inherited_credential_corpus=inherited_credential_corpus,
                inherited_adjudication_corpus=inherited_adjudication_corpus,
                checkpoint_policy=checkpoint_policy,
                checkpoint_log=checkpoint_log,
                checkpoints=checkpoints,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                conflict_witness_attestations=conflict_witness_attestations,
                predecessor_witness_attestations=predecessor_witness_attestations,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                conflict_adjudication_policy=conflict_adjudication_policy,
                conflict_adjudication=conflict_adjudication,
                current_issuer_registry=current_issuer_registry,
                current_credential_policy=current_credential_policy,
                current_revocation_policy=current_revocation_policy,
                current_revocation_ledger=current_revocation_ledger,
                current_revocation_events=current_revocation_events,
                inherited_witness_registry=inherited_witness_registry,
                inherited_witness_policy=inherited_witness_policy,
                inherited_witness_attestations=inherited_witness_attestations,
                inherited_head_checkpoint=inherited_head_checkpoint,
                inherited_adjudicator_registry=inherited_adjudicator_registry,
                inherited_adjudication_policy=inherited_adjudication_policy,
                inherited_adjudication=inherited_adjudication,
                inherited_issuer_registry=inherited_issuer_registry,
                inherited_credential_policy=inherited_credential_policy,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                revocation_events=revocation_events,
                inherited_witness_receipt=inherited_witness_receipt,
                checkpoint_executor=checkpoint_executor,
                experiment_run_id=experiment_run_id,
                current_revocation_evaluated_at=current_revocation_evaluated_at,
                current_credential_evaluated_at=current_credential_evaluated_at,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                conflict_adjudication_evaluated_at=(
                    conflict_adjudication_evaluated_at
                ),
                checkpoint_verified_at=checkpoint_verified_at,
                predecessor_witness_evaluated_at=predecessor_witness_evaluated_at,
                inherited_witness_evaluated_at=inherited_witness_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                inherited_credential_evaluated_at=inherited_credential_evaluated_at,
                inherited_adjudication_evaluated_at=(
                    inherited_adjudication_evaluated_at
                ),
                inherited_adjudication_completed_at=(
                    inherited_adjudication_completed_at
                ),
                inherited_credential_completed_at=inherited_credential_completed_at,
                revocation_completed_at=revocation_completed_at,
                checkpoint_completed_at=checkpoint_completed_at,
                prior_completed_at=prior_completed_at,
                completed_at=current_revocation_completed_at,
            )
        except CheckpointWitnessConflictRevocationExperimentError as exc:
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        suffix = (
            "completion"
            if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CheckpointWitnessConflictRevocationCheckpointFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=(
                CheckpointWitnessConflictRevocationCheckpointRunnerStatus.VERIFIED
            ),
            revocation_outcome=delegated.revocation_outcome,
            credential_outcome=delegated.credential_outcome,
            checkpoint_witness_outcome=delegated.checkpoint_witness_outcome,
            resolution_status=delegated.resolution_status,
            conflict_adjudication_outcome=delegated.conflict_adjudication_outcome,
            predecessor_witness_outcome=delegated.predecessor_witness_outcome,
            inherited_revocation_outcome=delegated.inherited_revocation_outcome,
            inherited_credential_outcome=delegated.inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                delegated.inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=delegated.inherited_resolution_status,
            inherited_adjudication_outcome=delegated.inherited_adjudication_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            predecessor_revocation_corpus_ref=corpus.predecessor_corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=current_checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_final_ref=delegated.final_manifest_ref,
            verified_checks=(
                CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
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
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.FINAL_PERSISTENCE,
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
            raise CheckpointWitnessConflictRevocationCheckpointExperimentError(
                CheckpointWitnessConflictRevocationCheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt(
            experiment_run_id=experiment_run_id,
            status=(
                CheckpointWitnessConflictRevocationCheckpointRunnerStatus.VERIFIED
            ),
            revocation_outcome=delegated.revocation_outcome,
            credential_outcome=delegated.credential_outcome,
            checkpoint_witness_outcome=delegated.checkpoint_witness_outcome,
            resolution_status=delegated.resolution_status,
            conflict_adjudication_outcome=delegated.conflict_adjudication_outcome,
            predecessor_witness_outcome=delegated.predecessor_witness_outcome,
            inherited_revocation_outcome=delegated.inherited_revocation_outcome,
            inherited_credential_outcome=delegated.inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                delegated.inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=delegated.inherited_resolution_status,
            inherited_adjudication_outcome=delegated.inherited_adjudication_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            predecessor_revocation_corpus_ref=corpus.predecessor_corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=current_checkpoint_log.head_checkpoint_ref,
            checkpoint_verification_ref=report_ref,
            revocation_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=(
                CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
    "CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner",
    "CheckpointWitnessConflictRevocationCheckpointExperimentError",
    "CheckpointWitnessConflictRevocationCheckpointFinalManifest",
    "CheckpointWitnessConflictRevocationCheckpointRunnerStage",
    "CheckpointWitnessConflictRevocationCheckpointRunnerStatus",
    "VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt",
]
