"""Resolve the current revocation-checkpoint witness conflict before PR #45."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_witness import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    WitnessBoundCurrentConflictAdjudicatorRevocationCheckpointCorpusSnapshot,
    validate_current_conflict_adjudicator_revocation_checkpoint_witnesses,
)
from ctrt.current_revocation_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
    ConflictAdjudicationDecisionReport,
    ConflictAdjudicationError,
    StoredConflictAdjudicationEvidence,
    load_current_revocation_checkpoint_conflict_adjudication_evidence,
    validate_current_revocation_checkpoint_conflict_adjudication,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_gated_current_revocation_checkpoint_runner import (
    CurrentRevocationCheckpointWitnessExperimentError,
    VerifiedCurrentRevocationCheckpointWitnessReceipt,
    WitnessGatedCurrentRevocationCheckpointExperimentRunner,
)

WitnessCorpus = WitnessBoundCurrentConflictAdjudicatorRevocationCheckpointCorpusSnapshot

_ARTIFACT_PREFIX = (
    "current-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint-witness-conflict-adjudication"
)


class AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage(StrEnum):
    """Boundary at which current revocation-checkpoint adjudication failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    ADJUDICATION_VALIDATION = "adjudication-validation"
    ADJUDICATION_DECISION_PERSISTENCE = "adjudication-decision-persistence"
    WITNESS_EXECUTION = "witness-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS = (
    "exact-1.23.0-current-revocation-checkpoint-witness-predecessor-preserved",
    "exact-conflicting-current-revocation-checkpoint-witness-population-bound",
    "original-current-revocation-checkpoint-witness-abstention-preserved",
    "exact-current-revocation-checkpoint-conflict-adjudicator-registry-bound",
    "exact-current-revocation-checkpoint-conflict-adjudication-policy-bound",
    "current-revocation-checkpoint-fork-evidence-reverified",
    "current-revocation-checkpoint-dissent-preserved",
    "resolved-head-restricted-to-exact-1.22.0-checkpoint-head",
    "current-revocation-checkpoint-adjudication-and-pr45-outcomes-finalized-separately",
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
class AdjudicatedCurrentRevocationCheckpointWitnessFinalManifest:
    """Final preserving conflict, resolution, and every PR #45 outcome."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome
    )
    current_revocation_checkpoint_resolution_status: WitnessConflictResolutionStatus
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome
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
    adjudication_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    conflict_adjudicator_registry_ref: StoredArtifactRef
    conflict_adjudication_policy_ref: StoredArtifactRef
    conflict_adjudication_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    predecessor_witness_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("adjudicated current revocation-checkpoint must be verified")
        if not self.witness_attestation_refs:
            raise ValueError("adjudicated current conflict requires attestations")
        if len(self.witness_attestation_refs) != len(
            set(self.witness_attestation_refs)
        ):
            raise ValueError("adjudicated current conflict refs must be unique")
        downstream = (
            self.resolved_current_revocation_checkpoint_witness_outcome,
            self.current_conflict_adjudicator_revocation_outcome,
            self.current_conflict_adjudicator_credential_outcome,
            self.conflicting_witness_outcome,
            self.current_resolution_status,
            self.current_conflict_adjudication_outcome,
            self.resolved_current_witness_outcome,
            self.current_revocation_outcome,
            self.current_credential_outcome,
            self.lower_checkpoint_witness_outcome,
            self.lower_resolution_status,
            self.lower_conflict_adjudication_outcome,
            self.lower_predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if (
            self.current_revocation_checkpoint_conflict_adjudication_outcome
            is WitnessConflictAdjudicationOutcome.ABSTAIN
        ):
            if any(item is not None for item in downstream):
                raise ValueError(
                    "current adjudication abstention may not claim PR #45 outcomes"
                )
            if self.predecessor_witness_final_ref is not None:
                raise ValueError(
                    "current adjudication abstention may not contain PR #45 final"
                )
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("current adjudication abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.predecessor_witness_final_ref is None:
                raise ValueError("current adjudication execution requires PR #45 final")
            if self.resolved_current_revocation_checkpoint_witness_outcome is None:
                raise ValueError(
                    "current adjudication execution requires resolved witness outcome"
                )
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from adjudication outcome")
        if (
            self.verified_checks
            != ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS
        ):
            raise ValueError("adjudicated current conflict lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt:
    """Proof of conflict resolution plus optional exact PR #45 result."""

    experiment_run_id: str
    status: AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome
    )
    current_revocation_checkpoint_resolution_status: WitnessConflictResolutionStatus
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome
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
    adjudication_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    conflict_adjudicator_registry_ref: StoredArtifactRef
    conflict_adjudication_policy_ref: StoredArtifactRef
    conflict_adjudication_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    predecessor_witness_receipt: VerifiedCurrentRevocationCheckpointWitnessReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("verified adjudicated current revocation-checkpoint required")
        downstream = (
            self.resolved_current_revocation_checkpoint_witness_outcome,
            self.current_conflict_adjudicator_revocation_outcome,
            self.current_conflict_adjudicator_credential_outcome,
            self.conflicting_witness_outcome,
            self.current_resolution_status,
            self.current_conflict_adjudication_outcome,
            self.resolved_current_witness_outcome,
            self.current_revocation_outcome,
            self.current_credential_outcome,
            self.lower_checkpoint_witness_outcome,
            self.lower_resolution_status,
            self.lower_conflict_adjudication_outcome,
            self.lower_predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if (
            self.current_revocation_checkpoint_conflict_adjudication_outcome
            is WitnessConflictAdjudicationOutcome.ABSTAIN
        ):
            if self.predecessor_witness_receipt is not None:
                raise ValueError(
                    "current adjudication abstention may not contain PR #45 receipt"
                )
            if any(item is not None for item in downstream):
                raise ValueError(
                    "current adjudication abstention may not contain downstream outcomes"
                )
            expected_id = prefix + "abstention"
        else:
            delegated = self.predecessor_witness_receipt
            if delegated is None:
                raise ValueError("current adjudication execution requires PR #45 receipt")
            if delegated.experiment_run_id != self.experiment_run_id:
                raise ValueError("PR #45 receipt belongs to another experiment run")
            if (
                delegated.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
                is not self.resolved_current_revocation_checkpoint_witness_outcome
                or delegated.current_conflict_adjudicator_revocation_outcome
                is not self.current_conflict_adjudicator_revocation_outcome
                or delegated.current_conflict_adjudicator_credential_outcome
                is not self.current_conflict_adjudicator_credential_outcome
                or delegated.conflicting_witness_outcome
                is not self.conflicting_witness_outcome
                or delegated.current_resolution_status
                is not self.current_resolution_status
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
                or delegated.lower_resolution_status
                is not self.lower_resolution_status
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
                raise ValueError("PR #45 receipt differs from adjudicated receipt")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong adjudication outcome")
        if (
            self.verified_checks
            != ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS
        ):
            raise ValueError("verified adjudicated current conflict lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner:
    """Adjudicate exact 1.24.0 conflict before executing PR #45."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = WitnessGatedCurrentRevocationCheckpointExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessCorpus,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        witness_checkpoint_verified_at: str,
        canonical_witness_evaluated_at: str,
        current_checkpoint_verified_at: str,
        current_conflict_adjudicator_revocation_evaluated_at: str,
        revocation_completed_at: str,
        current_checkpoint_completed_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("adjudicated current conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match adjudication-bound corpus exactly")
        if corpus.predecessor_corpus_ref != witness_predecessor.reference():
            raise ValueError("adjudication corpus must bind exact 1.23.0 predecessor")
        if corpus.corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry differs from adjudication corpus")
        if corpus.corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy differs from adjudication corpus")
        expected_attestations = tuple(
            item.reference() for item in conflict_witness_attestations
        )
        if corpus.corpus.witness_attestation_refs != expected_attestations:
            raise ValueError("conflicting witness population differs from corpus")
        if (
            corpus.adjudicator_registry_ref
            != conflict_adjudicator_registry.reference()
        ):
            raise ValueError("conflict adjudicator registry differs from corpus")
        if (
            corpus.adjudication_policy_ref
            != conflict_adjudication_policy.reference()
        ):
            raise ValueError("conflict adjudication policy differs from corpus")
        if corpus.adjudication_ref != conflict_adjudication.reference():
            raise ValueError("conflict adjudication record differs from corpus")
        successor_time = _parse_timestamp(corpus.corpus.created_at, "corpus.created_at")
        conflict_witness_time = _parse_timestamp(
            conflict_witness_evaluated_at,
            "conflict_witness_evaluated_at",
        )
        conflict_time = _parse_timestamp(
            conflict_adjudication_evaluated_at,
            "conflict_adjudication_evaluated_at",
        )
        witness_checkpoint_time = _parse_timestamp(
            witness_checkpoint_verified_at,
            "witness_checkpoint_verified_at",
        )
        canonical_witness_time = _parse_timestamp(
            canonical_witness_evaluated_at,
            "canonical_witness_evaluated_at",
        )
        checkpoint_time = _parse_timestamp(
            current_checkpoint_verified_at,
            "current_checkpoint_verified_at",
        )
        revocation_time = _parse_timestamp(
            current_conflict_adjudicator_revocation_evaluated_at,
            "current_conflict_adjudicator_revocation_evaluated_at",
        )
        revocation_completed = _parse_timestamp(
            revocation_completed_at,
            "revocation_completed_at",
        )
        checkpoint_completed = _parse_timestamp(
            current_checkpoint_completed_at,
            "current_checkpoint_completed_at",
        )
        prior_completed = _parse_timestamp(prior_completed_at, "prior_completed_at")
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= conflict_witness_time
            <= conflict_time
            <= witness_checkpoint_time
            <= canonical_witness_time
            <= checkpoint_time
            <= revocation_time
            <= revocation_completed
            <= checkpoint_completed
            <= prior_completed
            <= completed
        ):
            raise ValueError(
                "successor, conflict, adjudication, and PR #45 chronology differs"
            )

    def _persist_witness_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-witness-decision"
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored conflicting witness decision differs")
        return reference

    def _persist_adjudication_decision(
        self,
        *,
        experiment_run_id: str,
        decision: ConflictAdjudicationDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision"
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored conflict adjudication decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: AdjudicatedCurrentRevocationCheckpointWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessCorpus,
        evidence: StoredConflictAdjudicationEvidence,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
        adjudication_decision: ConflictAdjudicationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored adjudicated current conflict differs")
        if self._store.get(
            final.adjudication_corpus_ref.artifact_id,
            expected_hash=final.adjudication_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.24.0 adjudication corpus differs")
        predecessor = self._store.get(
            witness_predecessor.reference().artifact_id,
            expected_hash=witness_predecessor.reference().artifact_hash,
        )
        if predecessor.payload != witness_predecessor.artifact().payload:
            raise ArtifactIntegrityError("stored 1.23.0 witness predecessor differs")
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != witness_registry.canonical_payload:
            raise ArtifactIntegrityError("stored current witness registry differs")
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != witness_policy.canonical_payload:
            raise ArtifactIntegrityError("stored current witness policy differs")
        for reference in evidence.witness_evidence.attestation_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        if self._store.get(
            final.conflict_adjudicator_registry_ref.artifact_id,
            expected_hash=final.conflict_adjudicator_registry_ref.artifact_hash,
        ).payload != conflict_adjudicator_registry.canonical_payload:
            raise ArtifactIntegrityError("stored conflict adjudicator registry differs")
        if self._store.get(
            final.conflict_adjudication_policy_ref.artifact_id,
            expected_hash=final.conflict_adjudication_policy_ref.artifact_hash,
        ).payload != conflict_adjudication_policy.canonical_payload:
            raise ArtifactIntegrityError("stored conflict adjudication policy differs")
        if self._store.get(
            final.conflict_adjudication_ref.artifact_id,
            expected_hash=final.conflict_adjudication_ref.artifact_hash,
        ).payload != conflict_adjudication.canonical_payload:
            raise ArtifactIntegrityError("stored conflict adjudication record differs")
        expected_witness = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-witness-decision",
            witness_decision,
        )
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != expected_witness.payload:
            raise ArtifactIntegrityError("stored conflicting witness decision differs")
        expected_adjudication = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            adjudication_decision,
        )
        if self._store.get(
            final.adjudication_decision_ref.artifact_id,
            expected_hash=final.adjudication_decision_ref.artifact_hash,
        ).payload != expected_adjudication.payload:
            raise ArtifactIntegrityError("stored conflict adjudication decision differs")
        if final.predecessor_witness_final_ref is not None:
            self._store.get(
                final.predecessor_witness_final_ref.artifact_id,
                expected_hash=final.predecessor_witness_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessCorpus,
        current_checkpoint_corpus: Any,
        current_checkpoint_policy: Any,
        current_checkpoint_log: Any,
        current_checkpoints: tuple[Any, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        canonical_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        current_conflict_adjudicator_revocation_ledger: Any,
        experiment_run_id: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        witness_checkpoint_verified_at: str,
        canonical_witness_evaluated_at: str,
        current_checkpoint_verified_at: str,
        current_conflict_adjudicator_revocation_evaluated_at: str,
        revocation_completed_at: str,
        current_checkpoint_completed_at: str,
        prior_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt:
        """Return adjudication abstention or the exact delegated PR #45 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_predecessor=witness_predecessor,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                conflict_witness_attestations=conflict_witness_attestations,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                conflict_adjudication_policy=conflict_adjudication_policy,
                conflict_adjudication=conflict_adjudication,
                experiment_run_id=experiment_run_id,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                conflict_adjudication_evaluated_at=(
                    conflict_adjudication_evaluated_at
                ),
                witness_checkpoint_verified_at=witness_checkpoint_verified_at,
                canonical_witness_evaluated_at=canonical_witness_evaluated_at,
                current_checkpoint_verified_at=current_checkpoint_verified_at,
                current_conflict_adjudicator_revocation_evaluated_at=(
                    current_conflict_adjudicator_revocation_evaluated_at
                ),
                revocation_completed_at=revocation_completed_at,
                current_checkpoint_completed_at=current_checkpoint_completed_at,
                prior_completed_at=prior_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = (
                load_current_revocation_checkpoint_conflict_adjudication_evidence(
                    self._store,
                    corpus=corpus,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    adjudicator_registry=conflict_adjudicator_registry,
                    adjudication_policy=conflict_adjudication_policy,
                    adjudication=conflict_adjudication,
                )
            )
        except (
            ArtifactStoreError,
            ConflictAdjudicationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            witness_decision = (
                validate_current_conflict_adjudicator_revocation_checkpoint_witnesses(
                    plan=plan,
                    corpus=cast(Any, corpus.corpus),
                    registry=witness_registry,
                    policy=witness_policy,
                    head_checkpoint=current_checkpoints[-1],
                    attestations=evidence.witness_evidence.attestations,
                    evaluated_at=conflict_witness_evaluated_at,
                )
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.WITNESS_VALIDATION,
                str(exc),
            ) from exc

        try:
            witness_decision_ref = self._persist_witness_decision(
                experiment_run_id=experiment_run_id,
                decision=witness_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            adjudication_decision = (
                validate_current_revocation_checkpoint_conflict_adjudication(
                    plan=plan,
                    corpus=corpus,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    adjudicator_registry=conflict_adjudicator_registry,
                    adjudication_policy=conflict_adjudication_policy,
                    witness_decision=witness_decision,
                    adjudication=conflict_adjudication,
                    evaluated_at=conflict_adjudication_evaluated_at,
                )
            )
        except (ConflictAdjudicationError, ValueError) as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.ADJUDICATION_VALIDATION,
                str(exc),
            ) from exc

        try:
            adjudication_decision_ref = self._persist_adjudication_decision(
                experiment_run_id=experiment_run_id,
                decision=adjudication_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.ADJUDICATION_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated_receipt: VerifiedCurrentRevocationCheckpointWitnessReceipt | None = None
        if (
            adjudication_decision.outcome
            is WitnessConflictAdjudicationOutcome.EXECUTE
        ):
            delegated_plan = replace(
                plan,
                corpus_ref=witness_predecessor.reference(),
                content_ids=witness_predecessor.content_ids,
            )
            try:
                delegated_receipt = self._runner.run(
                    plan=delegated_plan,
                    corpus=witness_predecessor,
                    checkpoint_corpus=current_checkpoint_corpus,
                    current_checkpoint_policy=current_checkpoint_policy,
                    current_checkpoint_log=current_checkpoint_log,
                    current_checkpoints=current_checkpoints,
                    current_witness_registry=witness_registry,
                    current_witness_policy=witness_policy,
                    current_witness_attestations=canonical_witness_attestations,
                    current_conflict_adjudicator_revocation_ledger=(
                        current_conflict_adjudicator_revocation_ledger
                    ),
                    experiment_run_id=experiment_run_id,
                    witness_checkpoint_verified_at=witness_checkpoint_verified_at,
                    current_witness_evaluated_at=canonical_witness_evaluated_at,
                    current_checkpoint_verified_at=current_checkpoint_verified_at,
                    current_conflict_adjudicator_revocation_evaluated_at=(
                        current_conflict_adjudicator_revocation_evaluated_at
                    ),
                    revocation_completed_at=revocation_completed_at,
                    current_checkpoint_completed_at=current_checkpoint_completed_at,
                    completed_at=prior_completed_at,
                    **delegated,
                )
            except CurrentRevocationCheckpointWitnessExperimentError as exc:
                raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                    AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.WITNESS_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated_receipt is None:
            resolved_current_revocation_checkpoint_witness_outcome = None
            current_conflict_adjudicator_revocation_outcome = None
            current_conflict_adjudicator_credential_outcome = None
            conflicting_witness_outcome = None
            current_resolution_status = None
            current_conflict_adjudication_outcome = None
            resolved_current_witness_outcome = None
            current_revocation_outcome = None
            current_credential_outcome = None
            lower_checkpoint_witness_outcome = None
            lower_resolution_status = None
            lower_conflict_adjudication_outcome = None
            lower_predecessor_witness_outcome = None
            inherited_revocation_outcome = None
            inherited_credential_outcome = None
            inherited_checkpoint_witness_outcome = None
            inherited_resolution_status = None
            inherited_adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            predecessor_final_ref = None
            suffix = "abstention"
        else:
            resolved_current_revocation_checkpoint_witness_outcome = (
                delegated_receipt.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
            )
            current_conflict_adjudicator_revocation_outcome = (
                delegated_receipt.current_conflict_adjudicator_revocation_outcome
            )
            current_conflict_adjudicator_credential_outcome = (
                delegated_receipt.current_conflict_adjudicator_credential_outcome
            )
            conflicting_witness_outcome = delegated_receipt.conflicting_witness_outcome
            current_resolution_status = delegated_receipt.current_resolution_status
            current_conflict_adjudication_outcome = (
                delegated_receipt.current_conflict_adjudication_outcome
            )
            resolved_current_witness_outcome = (
                delegated_receipt.resolved_current_witness_outcome
            )
            current_revocation_outcome = delegated_receipt.current_revocation_outcome
            current_credential_outcome = delegated_receipt.current_credential_outcome
            lower_checkpoint_witness_outcome = (
                delegated_receipt.lower_checkpoint_witness_outcome
            )
            lower_resolution_status = delegated_receipt.lower_resolution_status
            lower_conflict_adjudication_outcome = (
                delegated_receipt.lower_conflict_adjudication_outcome
            )
            lower_predecessor_witness_outcome = (
                delegated_receipt.lower_predecessor_witness_outcome
            )
            inherited_revocation_outcome = (
                delegated_receipt.inherited_revocation_outcome
            )
            inherited_credential_outcome = (
                delegated_receipt.inherited_credential_outcome
            )
            inherited_checkpoint_witness_outcome = (
                delegated_receipt.inherited_checkpoint_witness_outcome
            )
            inherited_resolution_status = (
                delegated_receipt.inherited_resolution_status
            )
            inherited_adjudication_outcome = (
                delegated_receipt.inherited_adjudication_outcome
            )
            terminal_outcome = delegated_receipt.terminal_outcome
            predecessor_final_ref = delegated_receipt.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = AdjudicatedCurrentRevocationCheckpointWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED,
            conflicting_current_revocation_checkpoint_witness_outcome=(
                witness_decision.outcome
            ),
            current_revocation_checkpoint_resolution_status=(
                adjudication_decision.resolution_status
            ),
            current_revocation_checkpoint_conflict_adjudication_outcome=(
                adjudication_decision.outcome
            ),
            resolved_current_revocation_checkpoint_witness_outcome=(
                resolved_current_revocation_checkpoint_witness_outcome
            ),
            current_conflict_adjudicator_revocation_outcome=(
                current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=conflicting_witness_outcome,
            current_resolution_status=current_resolution_status,
            current_conflict_adjudication_outcome=current_conflict_adjudication_outcome,
            resolved_current_witness_outcome=resolved_current_witness_outcome,
            current_revocation_outcome=current_revocation_outcome,
            current_credential_outcome=current_credential_outcome,
            lower_checkpoint_witness_outcome=lower_checkpoint_witness_outcome,
            lower_resolution_status=lower_resolution_status,
            lower_conflict_adjudication_outcome=(
                lower_conflict_adjudication_outcome
            ),
            lower_predecessor_witness_outcome=lower_predecessor_witness_outcome,
            inherited_revocation_outcome=inherited_revocation_outcome,
            inherited_credential_outcome=inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=inherited_resolution_status,
            inherited_adjudication_outcome=inherited_adjudication_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            witness_registry_ref=evidence.witness_evidence.witness_registry_ref,
            witness_policy_ref=evidence.witness_evidence.witness_policy_ref,
            witness_attestation_refs=evidence.witness_evidence.attestation_refs,
            conflict_adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            conflict_adjudication_policy_ref=evidence.adjudication_policy_ref,
            conflict_adjudication_ref=evidence.adjudication_ref,
            witness_decision_ref=witness_decision_ref,
            adjudication_decision_ref=adjudication_decision_ref,
            predecessor_witness_final_ref=predecessor_final_ref,
            verified_checks=(
                ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS
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
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.FINAL_PERSISTENCE,
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
                witness_predecessor=witness_predecessor,
                evidence=evidence,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                conflict_adjudication_policy=conflict_adjudication_policy,
                conflict_adjudication=conflict_adjudication,
                witness_decision=witness_decision,
                adjudication_decision=adjudication_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedCurrentRevocationCheckpointWitnessExperimentError(
                AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED,
            conflicting_current_revocation_checkpoint_witness_outcome=(
                witness_decision.outcome
            ),
            current_revocation_checkpoint_resolution_status=(
                adjudication_decision.resolution_status
            ),
            current_revocation_checkpoint_conflict_adjudication_outcome=(
                adjudication_decision.outcome
            ),
            resolved_current_revocation_checkpoint_witness_outcome=(
                resolved_current_revocation_checkpoint_witness_outcome
            ),
            current_conflict_adjudicator_revocation_outcome=(
                current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=conflicting_witness_outcome,
            current_resolution_status=current_resolution_status,
            current_conflict_adjudication_outcome=current_conflict_adjudication_outcome,
            resolved_current_witness_outcome=resolved_current_witness_outcome,
            current_revocation_outcome=current_revocation_outcome,
            current_credential_outcome=current_credential_outcome,
            lower_checkpoint_witness_outcome=lower_checkpoint_witness_outcome,
            lower_resolution_status=lower_resolution_status,
            lower_conflict_adjudication_outcome=(
                lower_conflict_adjudication_outcome
            ),
            lower_predecessor_witness_outcome=lower_predecessor_witness_outcome,
            inherited_revocation_outcome=inherited_revocation_outcome,
            inherited_credential_outcome=inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=inherited_resolution_status,
            inherited_adjudication_outcome=inherited_adjudication_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            witness_registry_ref=evidence.witness_evidence.witness_registry_ref,
            witness_policy_ref=evidence.witness_evidence.witness_policy_ref,
            witness_attestation_refs=evidence.witness_evidence.attestation_refs,
            conflict_adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            conflict_adjudication_policy_ref=evidence.adjudication_policy_ref,
            conflict_adjudication_ref=evidence.adjudication_ref,
            witness_decision_ref=witness_decision_ref,
            adjudication_decision_ref=adjudication_decision_ref,
            predecessor_witness_receipt=delegated_receipt,
            final_manifest_ref=final_ref,
            verified_checks=(
                ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
    "AdjudicatedCurrentRevocationCheckpointWitnessExperimentError",
    "AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner",
    "AdjudicatedCurrentRevocationCheckpointWitnessFinalManifest",
    "AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage",
    "AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus",
    "VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt",
]
