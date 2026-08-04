"""Resolve checkpoint-witness conflict before executing the exact PR #35 layer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

import ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints as cp
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
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
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
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    WitnessBoundCheckpointCorpusSnapshot,
    validate_witness_attestations,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCheckpointWitnessCorpusSnapshot,
    ConflictAdjudicationDecisionReport,
    ConflictAdjudicationError,
    StoredConflictAdjudicationEvidence,
    load_conflict_adjudication_evidence,
    validate_conflict_adjudication,
)
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)
from ctrt.witness_gated_witness_conflict_adjudicator_checkpoint_runner import (
    VerifiedWitnessConflictAdjudicatorCheckpointReceipt,
    WitnessConflictAdjudicatorCheckpointExperimentError,
    WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner,
)

CheckpointCorpus = (
    cp.CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
)
CheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
CheckpointPolicy = cp.AdjudicatorCredentialRevocationCheckpointPolicySnapshot
CheckpointLog = cp.AdjudicatorCredentialRevocationCheckpointLogSnapshot
RevocationCorpus = (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
)


class AdjudicatedCheckpointWitnessConflictRunnerStage(StrEnum):
    """Boundary at which current witness-conflict adjudication failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    ADJUDICATION_VALIDATION = "adjudication-validation"
    ADJUDICATION_DECISION_PERSISTENCE = "adjudication-decision-persistence"
    WITNESS_EXECUTION = "witness-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatedCheckpointWitnessConflictRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class AdjudicatedCheckpointWitnessConflictExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatedCheckpointWitnessConflictRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS = (
    "exact-1.13.0-witness-predecessor-preserved",
    "exact-conflicting-checkpoint-witness-population-bound",
    "original-checkpoint-witness-abstention-preserved",
    "exact-checkpoint-witness-conflict-adjudicator-registry-bound",
    "exact-checkpoint-witness-conflict-adjudication-policy-bound",
    "checkpoint-witness-fork-evidence-reverified",
    "checkpoint-witness-dissent-preserved",
    "resolved-head-restricted-to-declared-checkpoint-head",
    "witness-adjudication-and-downstream-outcomes-finalized-separately",
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
class AdjudicatedCheckpointWitnessConflictFinalManifest:
    """Final marker preserving witness, adjudication, and downstream outcomes."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatedCheckpointWitnessConflictRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    resolution_status: WitnessConflictResolutionStatus
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    revocation_outcome: CredentialDecisionOutcome | None
    credential_outcome: CredentialDecisionOutcome | None
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
        expected_status = AdjudicatedCheckpointWitnessConflictRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("adjudicated checkpoint-witness conflict must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("adjudicated witness conflict requires unique contents")
        if not self.witness_attestation_refs:
            raise ValueError("adjudicated witness conflict requires attestations")
        if len(self.witness_attestation_refs) != len(set(self.witness_attestation_refs)):
            raise ValueError("adjudicated witness attestation refs must be unique")
        downstream = (
            self.predecessor_witness_outcome,
            self.revocation_outcome,
            self.credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudication-"
        )
        if (
            self.conflict_adjudication_outcome
            is WitnessConflictAdjudicationOutcome.ABSTAIN
        ):
            if any(item is not None for item in downstream):
                raise ValueError("adjudication abstention must not contain downstream outcomes")
            if self.predecessor_witness_final_ref is not None:
                raise ValueError("adjudication abstention must not contain downstream final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("adjudication abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.predecessor_witness_final_ref is None:
                raise ValueError("adjudication execution requires PR #35 final")
            if self.predecessor_witness_outcome is None:
                raise ValueError("adjudication execution requires predecessor witness outcome")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from adjudication and terminal outcomes")
        if self.verified_checks != ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS:
            raise ValueError("adjudicated witness conflict final lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatedCheckpointWitnessConflictReceipt:
    """Proof of conflict resolution plus optional exact PR #35 result."""

    experiment_run_id: str
    status: AdjudicatedCheckpointWitnessConflictRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    resolution_status: WitnessConflictResolutionStatus
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    revocation_outcome: CredentialDecisionOutcome | None
    credential_outcome: CredentialDecisionOutcome | None
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
    predecessor_witness_receipt: VerifiedWitnessConflictAdjudicatorCheckpointReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = AdjudicatedCheckpointWitnessConflictRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("verified adjudicated witness-conflict status required")
        downstream = (
            self.predecessor_witness_outcome,
            self.revocation_outcome,
            self.credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudication-"
        )
        if (
            self.conflict_adjudication_outcome
            is WitnessConflictAdjudicationOutcome.ABSTAIN
        ):
            if self.predecessor_witness_receipt is not None:
                raise ValueError("adjudication abstention must not contain PR #35 receipt")
            if any(item is not None for item in downstream):
                raise ValueError("adjudication abstention must not contain downstream outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.predecessor_witness_receipt
            if delegated is None:
                raise ValueError("adjudication execution requires PR #35 receipt")
            if (
                delegated.checkpoint_witness_outcome
                is not self.predecessor_witness_outcome
                or delegated.revocation_outcome is not self.revocation_outcome
                or delegated.credential_outcome is not self.credential_outcome
                or delegated.prior_checkpoint_witness_outcome
                is not self.inherited_checkpoint_witness_outcome
                or delegated.resolution_status is not self.inherited_resolution_status
                or delegated.adjudication_outcome
                is not self.inherited_adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("PR #35 receipt differs from adjudicated receipt")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong adjudication outcome")
        if self.verified_checks != ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS:
            raise ValueError("verified adjudicated witness conflict lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner:
    """Adjudicate exact `1.14.0` conflict before executing PR #35."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessBoundCheckpointCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_verified_at: str,
        predecessor_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("adjudicated checkpoint-witness conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match adjudication-bound corpus exactly")
        if corpus.predecessor_corpus_ref != witness_predecessor.reference():
            raise ValueError("adjudication corpus must bind exact 1.13.0 predecessor")
        if corpus.corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry differs from adjudication corpus")
        if corpus.corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy differs from adjudication corpus")
        if corpus.corpus.witness_attestation_refs != tuple(
            item.reference() for item in conflict_witness_attestations
        ):
            raise ValueError("conflicting witness population differs from corpus order")
        if corpus.adjudicator_registry_ref != conflict_adjudicator_registry.reference():
            raise ValueError("conflict adjudicator registry differs from corpus")
        if corpus.adjudication_policy_ref != conflict_adjudication_policy.reference():
            raise ValueError("conflict adjudication policy differs from corpus")
        if corpus.adjudication_ref != conflict_adjudication.reference():
            raise ValueError("conflict adjudication record differs from corpus")
        successor_time = _parse_timestamp(corpus.corpus.created_at, "corpus.created_at")
        witness_time = _parse_timestamp(
            conflict_witness_evaluated_at,
            "conflict_witness_evaluated_at",
        )
        conflict_time = _parse_timestamp(
            conflict_adjudication_evaluated_at,
            "conflict_adjudication_evaluated_at",
        )
        checkpoint_time = _parse_timestamp(
            checkpoint_verified_at,
            "checkpoint_verified_at",
        )
        predecessor_time = _parse_timestamp(
            predecessor_witness_evaluated_at,
            "predecessor_witness_evaluated_at",
        )
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        prior_completed = _parse_timestamp(prior_completed_at, "prior_completed_at")
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= witness_time
            <= conflict_time
            <= checkpoint_time
            <= predecessor_time
            <= revocation_time
            <= prior_completed
            <= completed
        ):
            raise ValueError("successor, witness, adjudication, and PR #35 chronology differs")

    def _persist_witness_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-witness-decision"
        )
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
        artifact_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudication-decision"
        )
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
        final: AdjudicatedCheckpointWitnessConflictFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
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
            raise ArtifactIntegrityError("stored adjudicated witness-conflict final differs")
        if self._store.get(
            final.adjudication_corpus_ref.artifact_id,
            expected_hash=final.adjudication_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored adjudication corpus differs")
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != witness_registry.canonical_payload:
            raise ArtifactIntegrityError("stored witness registry differs")
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != witness_policy.canonical_payload:
            raise ArtifactIntegrityError("stored witness policy differs")
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
        witness_id = (
            f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-witness-decision"
        )
        expected_witness = serialize_artifact(witness_id, witness_decision)
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != expected_witness.payload:
            raise ArtifactIntegrityError("stored conflicting witness decision differs")
        adjudication_id = (
            f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudication-decision"
        )
        expected_adjudication = serialize_artifact(
            adjudication_id,
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
        corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessBoundCheckpointCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        revocation_corpus: RevocationCorpus,
        credential_corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        checkpoint_policy: CheckpointPolicy,
        checkpoint_log: CheckpointLog,
        checkpoints: tuple[CheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        predecessor_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        inherited_witness_registry: CheckpointWitnessRegistrySnapshot,
        inherited_witness_policy: CheckpointWitnessPolicySnapshot,
        inherited_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        inherited_head_checkpoint: CheckpointSnapshot,
        inherited_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        inherited_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        inherited_adjudication: WitnessConflictAdjudicationSnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        inherited_witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_verified_at: str,
        predecessor_witness_evaluated_at: str,
        inherited_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        inherited_adjudication_evaluated_at: str,
        inherited_adjudication_completed_at: str,
        credential_completed_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> VerifiedAdjudicatedCheckpointWitnessConflictReceipt:
        """Return fail-closed adjudication or exact delegated PR #35 result."""

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
                checkpoint_verified_at=checkpoint_verified_at,
                predecessor_witness_evaluated_at=predecessor_witness_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                prior_completed_at=prior_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_conflict_adjudication_evidence(
                self._store,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=conflict_adjudicator_registry,
                adjudication_policy=conflict_adjudication_policy,
                adjudication=conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            ConflictAdjudicationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_witness_attestations(
                plan=plan,
                corpus=cast(Any, corpus.corpus),
                registry=witness_registry,
                policy=witness_policy,
                head_checkpoint=checkpoints[-1],
                attestations=evidence.witness_evidence.attestations,
                evaluated_at=conflict_witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.WITNESS_VALIDATION,
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
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            adjudication_decision = validate_conflict_adjudication(
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
        except (ConflictAdjudicationError, ValueError) as exc:
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.ADJUDICATION_VALIDATION,
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
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.ADJUDICATION_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedWitnessConflictAdjudicatorCheckpointReceipt | None = None
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
                delegated = self._runner.run(
                    plan=delegated_plan,
                    corpus=witness_predecessor,
                    checkpoint_corpus=checkpoint_corpus,
                    revocation_corpus=revocation_corpus,
                    credential_corpus=credential_corpus,
                    adjudication_corpus=adjudication_corpus,
                    checkpoint_policy=checkpoint_policy,
                    checkpoint_log=checkpoint_log,
                    checkpoints=checkpoints,
                    current_witness_registry=witness_registry,
                    current_witness_policy=witness_policy,
                    current_witness_attestations=predecessor_witness_attestations,
                    prior_witness_registry=inherited_witness_registry,
                    prior_witness_policy=inherited_witness_policy,
                    prior_witness_attestations=inherited_witness_attestations,
                    prior_head_checkpoint=inherited_head_checkpoint,
                    adjudicator_registry=inherited_adjudicator_registry,
                    adjudication_policy=inherited_adjudication_policy,
                    adjudication=inherited_adjudication,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    revocation_policy=revocation_policy,
                    revocation_ledger=revocation_ledger,
                    revocation_events=revocation_events,
                    prior_witness_receipt=inherited_witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    checkpoint_verified_at=checkpoint_verified_at,
                    current_witness_evaluated_at=predecessor_witness_evaluated_at,
                    prior_witness_evaluated_at=inherited_witness_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    adjudication_evaluated_at=inherited_adjudication_evaluated_at,
                    adjudication_completed_at=inherited_adjudication_completed_at,
                    credential_completed_at=credential_completed_at,
                    revocation_completed_at=revocation_completed_at,
                    checkpoint_completed_at=checkpoint_completed_at,
                    completed_at=prior_completed_at,
                )
            except WitnessConflictAdjudicatorCheckpointExperimentError as exc:
                raise AdjudicatedCheckpointWitnessConflictExperimentError(
                    AdjudicatedCheckpointWitnessConflictRunnerStage.WITNESS_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated is None:
            predecessor_witness_outcome = None
            revocation_outcome = None
            credential_outcome = None
            inherited_checkpoint_witness_outcome = None
            inherited_resolution_status = None
            inherited_adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            predecessor_final_ref = None
            suffix = "abstention"
        else:
            predecessor_witness_outcome = delegated.checkpoint_witness_outcome
            revocation_outcome = delegated.revocation_outcome
            credential_outcome = delegated.credential_outcome
            inherited_checkpoint_witness_outcome = (
                delegated.prior_checkpoint_witness_outcome
            )
            inherited_resolution_status = delegated.resolution_status
            inherited_adjudication_outcome = delegated.adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            predecessor_final_ref = delegated.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            f"witness-conflict-adjudication-{suffix}"
        )
        final = AdjudicatedCheckpointWitnessConflictFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatedCheckpointWitnessConflictRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            resolution_status=adjudication_decision.resolution_status,
            conflict_adjudication_outcome=adjudication_decision.outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
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
            verified_checks=ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
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
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.FINAL_PERSISTENCE,
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
            raise AdjudicatedCheckpointWitnessConflictExperimentError(
                AdjudicatedCheckpointWitnessConflictRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatedCheckpointWitnessConflictReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatedCheckpointWitnessConflictRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            resolution_status=adjudication_decision.resolution_status,
            conflict_adjudication_outcome=adjudication_decision.outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
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
            predecessor_witness_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
    "AdjudicatedCheckpointWitnessConflictExperimentError",
    "AdjudicatedCheckpointWitnessConflictFinalManifest",
    "AdjudicatedCheckpointWitnessConflictRunnerStage",
    "AdjudicatedCheckpointWitnessConflictRunnerStatus",
    "AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner",
    "VerifiedAdjudicatedCheckpointWitnessConflictReceipt",
]
