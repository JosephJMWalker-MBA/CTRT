"""Immutable witness observations for adjudicator revocation checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
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
    CheckpointWitnessPolicyLifecycle,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistryLifecycle,
    CheckpointWitnessRegistrySnapshot,
    CheckpointWitnessRole,
)
from ctrt.confidence import SystemAbstention
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef


class AdjudicatorCheckpointWitnessError(ValueError):
    """Raised when adjudicator-checkpoint witness evidence is invalid."""


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not value.strip():
        raise AdjudicatorCheckpointWitnessError(f"{field_name} must not be empty")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AdjudicatorCheckpointWitnessError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise AdjudicatorCheckpointWitnessError(
            f"{field_name} must include a timezone"
        )
    return parsed


def _versioned_ref(value: object, field_name: str) -> VersionedArtifactRef:
    if not isinstance(value, dict):
        raise AdjudicatorCheckpointWitnessError(f"{field_name} must be an object")
    try:
        artifact_id = value["artifact_id"]
        artifact_version = value["artifact_version"]
        artifact_hash = value["artifact_hash"]
    except KeyError as exc:
        raise AdjudicatorCheckpointWitnessError(
            f"{field_name} is missing {exc.args[0]}"
        ) from exc
    if not all(isinstance(item, str) and item.strip() for item in (artifact_id, artifact_version, artifact_hash)):
        raise AdjudicatorCheckpointWitnessError(
            f"{field_name} fields must be non-empty strings"
        )
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        artifact_hash=artifact_hash,
    )


@dataclass(frozen=True, slots=True)
class WitnessBoundAdjudicatorCheckpointCorpusSnapshot:
    """Adjudicator checkpoint corpus plus exact witness evidence references."""

    corpus: CheckpointBoundAdjudicatorRevocationCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    witness_registry_ref: VersionedArtifactRef
    witness_policy_ref: VersionedArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]

    @classmethod
    def from_document(
        cls,
        document: dict[str, Any],
    ) -> WitnessBoundAdjudicatorCheckpointCorpusSnapshot:
        refs = document.get("adjudicator_checkpoint_witness_attestation_refs")
        if not isinstance(refs, list):
            raise AdjudicatorCheckpointWitnessError(
                "adjudicator_checkpoint_witness_attestation_refs must be an array"
            )
        return cls(
            corpus=CheckpointBoundAdjudicatorRevocationCorpusSnapshot.from_document(
                document
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get("adjudicator_checkpoint_witness_predecessor_corpus_ref"),
                "adjudicator_checkpoint_witness_predecessor_corpus_ref",
            ),
            witness_registry_ref=_versioned_ref(
                document.get("adjudicator_checkpoint_witness_registry_ref"),
                "adjudicator_checkpoint_witness_registry_ref",
            ),
            witness_policy_ref=_versioned_ref(
                document.get("adjudicator_checkpoint_witness_policy_ref"),
                "adjudicator_checkpoint_witness_policy_ref",
            ),
            witness_attestation_refs=tuple(
                StoredArtifactRef.from_document(item) for item in refs
            ),
        )

    @property
    def content_ids(self) -> tuple[str, ...]:
        return self.corpus.content_ids

    def reference(self) -> VersionedArtifactRef:
        return self.corpus.reference()

    def artifact(self):
        return self.corpus.artifact()


@dataclass(frozen=True, slots=True)
class AdjudicatorCheckpointWitnessObservationSummary:
    """One named checkpoint observation without vote aggregation."""

    witness_id: str
    attestation_ref: StoredArtifactRef
    observation_kind: CheckpointWitnessObservationKind
    expected_head_ref: StoredArtifactRef
    observed_head_ref: StoredArtifactRef
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class AdjudicatorCheckpointWitnessDecisionReport:
    """Canonical decision preserving every named observation and conflict."""

    experiment_id: str
    experiment_version: str
    witness_corpus_ref: VersionedArtifactRef
    witness_registry_ref: VersionedArtifactRef
    witness_policy_ref: VersionedArtifactRef
    checkpoint_head_ref: StoredArtifactRef
    outcome: CheckpointWitnessDecisionOutcome
    observations: tuple[AdjudicatorCheckpointWitnessObservationSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or not self.experiment_version.strip():
            raise AdjudicatorCheckpointWitnessError(
                "witness decision identity fields must not be empty"
            )
        if not self.observations:
            raise AdjudicatorCheckpointWitnessError(
                "witness decision requires named observations"
            )
        ids = tuple(item.witness_id for item in self.observations)
        if len(ids) != len(set(ids)):
            raise AdjudicatorCheckpointWitnessError(
                "witness decision observation IDs must be unique"
            )
        expected = (
            CheckpointWitnessDecisionOutcome.ABSTAIN
            if any(item.abstention.triggered for item in self.observations)
            else CheckpointWitnessDecisionOutcome.EXECUTE
        )
        if self.outcome is not expected:
            raise AdjudicatorCheckpointWitnessError(
                "witness decision outcome differs from observations"
            )
        _parse_timestamp(self.evaluated_at, "evaluated_at")

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "adjudicator-checkpoint-witness-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredAdjudicatorCheckpointWitnessEvidence:
    """Stored registry, policy, and exact attestation population."""

    corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    attestation_refs: tuple[StoredArtifactRef, ...]
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...]

    def __post_init__(self) -> None:
        if len(self.attestation_refs) != len(self.attestations):
            raise AdjudicatorCheckpointWitnessError(
                "stored witness evidence requires one ref per attestation"
            )


def load_adjudicator_checkpoint_witness_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
) -> StoredAdjudicatorCheckpointWitnessEvidence:
    """Load and reverify witness corpus, registry, policy, and attestations."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored adjudicator witness corpus differs from expected"
        )
    registry_artifact = store.get(
        registry.registry_id,
        expected_hash=registry.artifact_hash,
    )
    if registry_artifact.payload != registry.canonical_payload:
        raise ArtifactIntegrityError("stored witness registry differs from expected")
    policy_artifact = store.get(
        policy.policy_id,
        expected_hash=policy.artifact_hash,
    )
    if policy_artifact.payload != policy.canonical_payload:
        raise ArtifactIntegrityError("stored witness policy differs from expected")
    attestations: list[CheckpointWitnessAttestationSnapshot] = []
    for reference in corpus.witness_attestation_refs:
        artifact = store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        attestation = CheckpointWitnessAttestationSnapshot.from_artifact(artifact)
        if attestation.reference() != reference:
            raise ArtifactIntegrityError(
                "stored witness attestation reference differs from corpus"
            )
        attestations.append(attestation)
    return StoredAdjudicatorCheckpointWitnessEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        witness_registry_ref=store.reference(registry.registry_id),
        witness_policy_ref=store.reference(policy.policy_id),
        attestation_refs=tuple(item.reference() for item in attestations),
        attestations=tuple(attestations),
    )


def validate_adjudicator_checkpoint_witness_attestations(
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> AdjudicatorCheckpointWitnessDecisionReport:
    """Validate exact witness identity and preserve conflicts without voting."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise AdjudicatorCheckpointWitnessError(
            "only a frozen experiment plan may pass witness validation"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise AdjudicatorCheckpointWitnessError(
            "experiment plan differs from witness-bound corpus"
        )
    if corpus.witness_registry_ref != registry.reference():
        raise AdjudicatorCheckpointWitnessError(
            "witness registry reference differs from corpus"
        )
    if corpus.witness_policy_ref != policy.reference():
        raise AdjudicatorCheckpointWitnessError(
            "witness policy reference differs from corpus"
        )
    if registry.status is not CheckpointWitnessRegistryLifecycle.ACCEPTED:
        raise AdjudicatorCheckpointWitnessError("witness registry must be accepted")
    if policy.status is not CheckpointWitnessPolicyLifecycle.ACCEPTED:
        raise AdjudicatorCheckpointWitnessError("witness policy must be accepted")
    if policy.witness_registry_ref != registry.reference():
        raise AdjudicatorCheckpointWitnessError(
            "witness policy registry reference differs"
        )
    registry_ids = tuple(item.witness_id for item in registry.witnesses)
    if policy.required_witness_ids != registry_ids:
        raise AdjudicatorCheckpointWitnessError(
            "witness policy must require the exact registry order"
        )
    if tuple(item.reference() for item in attestations) != corpus.witness_attestation_refs:
        raise AdjudicatorCheckpointWitnessError(
            "witness attestation population differs from corpus"
        )
    if len(attestations) != len(policy.required_witness_ids):
        raise AdjudicatorCheckpointWitnessError(
            "witness attestation population differs from required witnesses"
        )
    if head_checkpoint.reference() != corpus.corpus.checkpoint_head_ref:
        raise AdjudicatorCheckpointWitnessError(
            "witness validation head differs from checkpoint corpus"
        )

    observations: list[AdjudicatorCheckpointWitnessObservationSummary] = []
    seen: set[str] = set()
    for expected_witness_id, attestation in zip(
        policy.required_witness_ids,
        attestations,
        strict=True,
    ):
        if attestation.witness_id in seen:
            raise AdjudicatorCheckpointWitnessError(
                "witness attestations must identify unique witnesses"
            )
        seen.add(attestation.witness_id)
        if attestation.witness_id != expected_witness_id:
            raise AdjudicatorCheckpointWitnessError(
                "witness attestation order differs from required registry order"
            )
        witness = registry.witness(attestation.witness_id)
        if witness is None:
            raise AdjudicatorCheckpointWitnessError(
                f"unknown checkpoint witness {attestation.witness_id!r}"
            )
        if witness.identity_revision != attestation.witness_identity_revision:
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: identity revision differs"
            )
        if witness.role is not CheckpointWitnessRole.CHECKPOINT_OBSERVER:
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: role may not observe checkpoints"
            )
        if attestation.checkpoint_corpus_ref != corpus.predecessor_corpus_ref:
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: checkpoint corpus reference differs"
            )
        if attestation.checkpoint_log_ref != corpus.corpus.checkpoint_log_ref:
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: checkpoint log reference differs"
            )
        if attestation.expected_head_ref != head_checkpoint.reference():
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: expected checkpoint head differs"
            )
        if _parse_timestamp(attestation.observed_at, "observed_at") < _parse_timestamp(
            head_checkpoint.published_at,
            "published_at",
        ):
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: observation predates checkpoint publication"
            )
        if _parse_timestamp(attestation.received_at, "received_at") > evaluated:
            raise AdjudicatorCheckpointWitnessError(
                f"{attestation.witness_id}: attestation received after evaluation"
            )
        reasons = (
            (f"adjudicator-checkpoint-witness-conflicting-head:{attestation.witness_id}",)
            if policy.abstain_on_conflicting_head
            and attestation.observation_kind
            is CheckpointWitnessObservationKind.CONFLICTING_HEAD
            else ()
        )
        observations.append(
            AdjudicatorCheckpointWitnessObservationSummary(
                witness_id=attestation.witness_id,
                attestation_ref=attestation.reference(),
                observation_kind=attestation.observation_kind,
                expected_head_ref=attestation.expected_head_ref,
                observed_head_ref=attestation.observed_head_ref,
                abstention=SystemAbstention(
                    triggered=bool(reasons),
                    reasons=reasons,
                ),
            )
        )

    outcome = (
        CheckpointWitnessDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in observations)
        else CheckpointWitnessDecisionOutcome.EXECUTE
    )
    return AdjudicatorCheckpointWitnessDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        witness_corpus_ref=corpus.reference(),
        witness_registry_ref=registry.reference(),
        witness_policy_ref=policy.reference(),
        checkpoint_head_ref=head_checkpoint.reference(),
        outcome=outcome,
        observations=tuple(observations),
        evaluated_at=evaluated_at,
    )


def persist_witness_bound_adjudicator_checkpoint_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    predecessor_corpus: CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> StoredAdjudicatorCheckpointWitnessEvidence:
    """Persist witness members first and publish the successor corpus last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise AdjudicatorCheckpointWitnessError(
            "predecessor adjudicator checkpoint corpus reference differs"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise AdjudicatorCheckpointWitnessError(
            "witness corpus content population differs"
        )
    if predecessor_corpus.checkpoint_policy_ref != corpus.corpus.checkpoint_policy_ref:
        raise AdjudicatorCheckpointWitnessError(
            "witness corpus checkpoint policy differs from predecessor"
        )
    if predecessor_corpus.checkpoint_log_ref != corpus.corpus.checkpoint_log_ref:
        raise AdjudicatorCheckpointWitnessError(
            "witness corpus checkpoint log differs from predecessor"
        )
    if predecessor_corpus.checkpoint_head_ref != corpus.corpus.checkpoint_head_ref:
        raise AdjudicatorCheckpointWitnessError(
            "witness corpus checkpoint head differs from predecessor"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored predecessor adjudicator checkpoint corpus differs"
        )
    validate_adjudicator_checkpoint_witness_attestations(
        plan=plan,
        corpus=corpus,
        registry=registry,
        policy=policy,
        head_checkpoint=head_checkpoint,
        attestations=attestations,
        evaluated_at=evaluated_at,
    )
    if store.append(registry.artifact()).artifact_hash != registry.artifact_hash:
        raise ArtifactIntegrityError("stored witness registry reference differs")
    if store.append(policy.artifact()).artifact_hash != policy.artifact_hash:
        raise ArtifactIntegrityError("stored witness policy reference differs")
    for attestation in attestations:
        if store.append(attestation.artifact()) != attestation.reference():
            raise ArtifactIntegrityError(
                "stored witness attestation reference differs"
            )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError("stored witness corpus reference differs")
    return load_adjudicator_checkpoint_witness_evidence(
        store,
        corpus=corpus,
        registry=registry,
        policy=policy,
    )
