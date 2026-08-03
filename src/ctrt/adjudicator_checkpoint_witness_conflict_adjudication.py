"""Authorized adjudication of adjudicator-checkpoint witness conflicts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    load_adjudicator_checkpoint_witness_evidence,
    validate_adjudicator_checkpoint_witness_attestations,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessObservationKind,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.confidence import SystemAbstention
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact
from ctrt.witness_conflict_adjudication import (
    PreservedWitnessDissent,
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicyLifecycle,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistryLifecycle,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictAdjudicatorRole,
    WitnessConflictResolutionStatus,
    WitnessForkEvidence,
)


class AdjudicatorCheckpointWitnessConflictAdjudicationError(ValueError):
    """Raised when adjudicator-checkpoint witness adjudication is invalid."""


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not value.strip():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            f"{field_name} must not be empty"
        )
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            f"{field_name} must include a timezone"
        )
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            f"{field_name} must be an object"
        )
    if any(not isinstance(key, str) for key in value):
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _versioned_ref(value: object, field_name: str) -> VersionedArtifactRef:
    document = _mapping(value, field_name)
    return VersionedArtifactRef(
        artifact_id=_string(document.get("artifact_id"), f"{field_name}.artifact_id"),
        artifact_version=_string(
            document.get("artifact_version"), f"{field_name}.artifact_version"
        ),
        artifact_hash=_string(document.get("artifact_hash"), f"{field_name}.artifact_hash"),
    )


@dataclass(frozen=True, slots=True)
class AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot:
    """Witness-bound adjudicator checkpoint corpus plus adjudication evidence."""

    corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    adjudication_policy_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot:
        return cls(
            corpus=WitnessBoundAdjudicatorCheckpointCorpusSnapshot.from_document(document),
            predecessor_corpus_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_witness_adjudication_predecessor_corpus_ref"
                ),
                "adjudicator_checkpoint_witness_adjudication_predecessor_corpus_ref",
            ),
            adjudicator_registry_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_witness_conflict_adjudicator_registry_ref"
                ),
                "adjudicator_checkpoint_witness_conflict_adjudicator_registry_ref",
            ),
            adjudication_policy_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_witness_conflict_adjudication_policy_ref"
                ),
                "adjudicator_checkpoint_witness_conflict_adjudication_policy_ref",
            ),
            adjudication_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get(
                        "adjudicator_checkpoint_witness_conflict_adjudication_ref"
                    ),
                    "adjudicator_checkpoint_witness_conflict_adjudication_ref",
                )
            ),
        )

    @property
    def content_ids(self) -> tuple[str, ...]:
        return self.corpus.content_ids

    def reference(self) -> VersionedArtifactRef:
        return self.corpus.reference()

    def artifact(self) -> CanonicalArtifact:
        return self.corpus.artifact()


@dataclass(frozen=True, slots=True)
class AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport:
    """Decision preserving the original witness result, fork, and dissent."""

    experiment_id: str
    experiment_version: str
    adjudication_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    adjudication_policy_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef
    witness_outcome: CheckpointWitnessDecisionOutcome
    resolution_status: WitnessConflictResolutionStatus
    outcome: WitnessConflictAdjudicationOutcome
    fork_evidence: tuple[WitnessForkEvidence, ...]
    preserved_dissent: tuple[PreservedWitnessDissent, ...]
    rationale: str
    abstention: SystemAbstention
    evaluated_at: str

    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or not self.experiment_version.strip():
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "adjudication decision identity fields must not be empty"
            )
        if not self.rationale.strip():
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "adjudication rationale must not be empty"
            )
        expected = (
            WitnessConflictAdjudicationOutcome.EXECUTE
            if self.witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
            or self.resolution_status is WitnessConflictResolutionStatus.RESOLVED
            else WitnessConflictAdjudicationOutcome.ABSTAIN
        )
        if self.outcome is not expected:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "adjudication outcome differs from witness and resolution state"
            )
        if self.abstention.triggered != (
            self.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
        ):
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "adjudication abstention differs from outcome"
            )
        _parse_timestamp(self.evaluated_at, "evaluated_at")

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "adjudicator-checkpoint-witness-conflict-adjudication-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence:
    """Stored witness graph plus exact adjudication authority and record."""

    corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    witness_evidence: StoredAdjudicatorCheckpointWitnessEvidence


def load_adjudicator_checkpoint_witness_conflict_adjudication_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence:
    """Load and reverify the complete adjudication-bound graph."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError("stored adjudication corpus differs from expected")
    registry_artifact = store.get(
        adjudicator_registry.registry_id,
        expected_hash=adjudicator_registry.artifact_hash,
    )
    if registry_artifact.payload != adjudicator_registry.canonical_payload:
        raise ArtifactIntegrityError("stored adjudicator registry differs from expected")
    policy_artifact = store.get(
        adjudication_policy.policy_id,
        expected_hash=adjudication_policy.artifact_hash,
    )
    if policy_artifact.payload != adjudication_policy.canonical_payload:
        raise ArtifactIntegrityError("stored adjudication policy differs from expected")
    stored_adjudication = WitnessConflictAdjudicationSnapshot.from_artifact(
        store.get(adjudication.artifact_id, expected_hash=adjudication.artifact_hash)
    )
    if stored_adjudication.reference() != corpus.adjudication_ref:
        raise ArtifactIntegrityError("stored adjudication reference differs from corpus")
    witness_evidence = load_adjudicator_checkpoint_witness_evidence(
        store,
        corpus=corpus.corpus,
        registry=witness_registry,
        policy=witness_policy,
    )
    return StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        adjudicator_registry_ref=store.reference(adjudicator_registry.registry_id),
        adjudication_policy_ref=store.reference(adjudication_policy.policy_id),
        adjudication_ref=stored_adjudication.reference(),
        witness_evidence=witness_evidence,
    )


def validate_adjudicator_checkpoint_witness_conflict_adjudication(
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport:
    """Validate authorized resolution without counting witnesses."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "only a frozen plan may pass witness-conflict adjudication"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "experiment plan differs from adjudication-bound corpus"
        )
    if corpus.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudicator registry reference differs from corpus"
        )
    if corpus.adjudication_policy_ref != adjudication_policy.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication policy reference differs from corpus"
        )
    if corpus.adjudication_ref != adjudication.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication record reference differs from corpus"
        )
    if (
        adjudicator_registry.status
        is not WitnessConflictAdjudicatorRegistryLifecycle.ACCEPTED
    ):
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudicator registry must be accepted"
        )
    if (
        adjudication_policy.status
        is not WitnessConflictAdjudicationPolicyLifecycle.ACCEPTED
    ):
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication policy must be accepted"
        )
    if adjudication_policy.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication policy registry reference differs"
        )
    registry_ids = tuple(item.adjudicator_id for item in adjudicator_registry.adjudicators)
    if adjudication_policy.required_adjudicator_ids != registry_ids:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication policy must require exact registry order"
        )
    if adjudication.witness_predecessor_corpus_ref != corpus.predecessor_corpus_ref:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication predecessor corpus reference differs"
        )
    if adjudication.witness_registry_ref != witness_registry.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication witness registry reference differs"
        )
    if adjudication.witness_policy_ref != witness_policy.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication witness policy reference differs"
        )
    if adjudication.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication registry reference differs"
        )
    if adjudication.adjudication_policy_ref != adjudication_policy.reference():
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication policy reference differs"
        )
    if adjudication.checkpoint_head_ref != witness_decision.checkpoint_head_ref:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication checkpoint head differs from witness decision"
        )
    if _parse_timestamp(adjudication.decided_at, "decided_at") > evaluated:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication decision occurs after evaluation"
        )

    conflicts = tuple(
        WitnessForkEvidence(
            witness_id=item.witness_id,
            attestation_ref=item.attestation_ref,
            expected_head_ref=item.expected_head_ref,
            observed_head_ref=item.observed_head_ref,
        )
        for item in witness_decision.observations
        if item.observation_kind is CheckpointWitnessObservationKind.CONFLICTING_HEAD
    )
    if conflicts != adjudication.fork_evidence:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication fork evidence differs from witness observations"
        )
    if not conflicts:
        if (
            witness_decision.outcome is not CheckpointWitnessDecisionOutcome.EXECUTE
            or adjudication.status is not WitnessConflictResolutionStatus.NOT_REQUIRED
        ):
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "matching witnesses require not-required adjudication"
            )
    elif (
        witness_decision.outcome is not CheckpointWitnessDecisionOutcome.ABSTAIN
        or adjudication.status is WitnessConflictResolutionStatus.NOT_REQUIRED
    ):
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "conflicting witnesses require an adjudication state"
        )

    if adjudication.status in {
        WitnessConflictResolutionStatus.RESOLVED,
        WitnessConflictResolutionStatus.UNRESOLVED,
    }:
        if adjudication.adjudicator_id is None:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "decided adjudication requires adjudicator"
            )
        record = adjudicator_registry.adjudicator(adjudication.adjudicator_id)
        if record is None:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                f"unknown adjudicator {adjudication.adjudicator_id!r}"
            )
        if record.identity_revision != adjudication.adjudicator_identity_revision:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "adjudicator identity revision differs"
            )
        if record.role is not WitnessConflictAdjudicatorRole.WITNESS_CONFLICT_ADJUDICATOR:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "adjudicator role may not resolve witness conflicts"
            )
    if (
        adjudication.status is WitnessConflictResolutionStatus.RESOLVED
        and adjudication_policy.resolution_must_select_declared_head
        and adjudication.selected_head_ref != witness_decision.checkpoint_head_ref
    ):
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "resolved adjudication must select declared checkpoint head"
        )

    if (
        witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE
        or adjudication.status is WitnessConflictResolutionStatus.RESOLVED
    ):
        outcome = WitnessConflictAdjudicationOutcome.EXECUTE
        reasons: tuple[str, ...] = ()
    else:
        outcome = WitnessConflictAdjudicationOutcome.ABSTAIN
        reasons = (
            "adjudicator-checkpoint-witness-conflict-adjudication:"
            f"{adjudication.status.value}",
        )
    return AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        adjudication_corpus_ref=corpus.reference(),
        adjudicator_registry_ref=adjudicator_registry.reference(),
        adjudication_policy_ref=adjudication_policy.reference(),
        adjudication_ref=adjudication.reference(),
        witness_outcome=witness_decision.outcome,
        resolution_status=adjudication.status,
        outcome=outcome,
        fork_evidence=adjudication.fork_evidence,
        preserved_dissent=adjudication.preserved_dissent,
        rationale=adjudication.rationale,
        abstention=SystemAbstention(triggered=bool(reasons), reasons=reasons),
        evaluated_at=evaluated_at,
    )


def persist_adjudication_bound_adjudicator_checkpoint_witness_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
    predecessor_corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence:
    """Publish adjudication evidence and the successor corpus manifest last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "witness predecessor corpus reference differs"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
            "adjudication corpus content population differs"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError("stored witness predecessor corpus differs")
    witness_decision = validate_adjudicator_checkpoint_witness_attestations(
        plan=plan,
        corpus=corpus.corpus,
        registry=witness_registry,
        policy=witness_policy,
        head_checkpoint=head_checkpoint,
        attestations=witness_attestations,
        evaluated_at=evaluated_at,
    )
    validate_adjudicator_checkpoint_witness_conflict_adjudication(
        plan=plan,
        corpus=corpus,
        witness_registry=witness_registry,
        witness_policy=witness_policy,
        adjudicator_registry=adjudicator_registry,
        adjudication_policy=adjudication_policy,
        witness_decision=witness_decision,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )
    for artifact in (
        witness_registry.artifact(),
        witness_policy.artifact(),
        *(item.artifact() for item in witness_attestations),
        adjudicator_registry.artifact(),
        adjudication_policy.artifact(),
        adjudication.artifact(),
    ):
        stored = store.append(artifact)
        if stored.artifact_hash != artifact.artifact_hash:
            raise ArtifactIntegrityError("stored adjudication graph reference differs")
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError("stored adjudication corpus reference differs")
    return load_adjudicator_checkpoint_witness_conflict_adjudication_evidence(
        store,
        corpus=corpus,
        witness_registry=witness_registry,
        witness_policy=witness_policy,
        adjudicator_registry=adjudicator_registry,
        adjudication_policy=adjudication_policy,
        adjudication=adjudication,
    )


__all__ = [
    "AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot",
    "AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport",
    "AdjudicatorCheckpointWitnessConflictAdjudicationError",
    "StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence",
    "load_adjudicator_checkpoint_witness_conflict_adjudication_evidence",
    "persist_adjudication_bound_adjudicator_checkpoint_witness_corpus",
    "validate_adjudicator_checkpoint_witness_conflict_adjudication",
]
