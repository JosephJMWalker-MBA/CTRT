"""Immutable witness observations for revocation-ledger checkpoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.confidence import SystemAbstention
from ctrt.credential_revocation_checkpoints import (
    CheckpointBoundRevocationCorpusSnapshot,
    CredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class CheckpointWitnessError(ValueError):
    """Raised when witness identity, provenance, or observations are invalid."""


class CheckpointWitnessRegistryLifecycle(StrEnum):
    """Governance state of one witness registry."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class CheckpointWitnessPolicyLifecycle(StrEnum):
    """Governance state of one witness policy."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class CheckpointWitnessRole(StrEnum):
    """Bound role of a checkpoint witness."""

    CHECKPOINT_OBSERVER = "checkpoint_observer"


class CheckpointWitnessObservationKind(StrEnum):
    """Relationship between a witness-observed head and the declared head."""

    MATCHES_HEAD = "matches_head"
    CONFLICTING_HEAD = "conflicting_head"


class CheckpointWitnessDecisionOutcome(StrEnum):
    """Whether witness evidence permits downstream checkpoint execution."""

    EXECUTE = "execute"
    ABSTAIN = "abstain"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise CheckpointWitnessError(f"{field_name} must not be empty")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CheckpointWitnessError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise CheckpointWitnessError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CheckpointWitnessError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CheckpointWitnessError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckpointWitnessError(f"{field_name} must be a non-empty string")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise CheckpointWitnessError(f"{field_name} must be a boolean")
    return value


def _reject_unknown(
    document: Mapping[str, object],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise CheckpointWitnessError(
            f"{field_name} contains unsupported fields: {', '.join(unknown)}"
        )


def _versioned_ref(value: object, field_name: str) -> VersionedArtifactRef:
    document = _mapping(value, field_name)
    return VersionedArtifactRef(
        artifact_id=_string(document.get("artifact_id"), f"{field_name}.artifact_id"),
        artifact_version=_string(
            document.get("artifact_version"),
            f"{field_name}.artifact_version",
        ),
        artifact_hash=_string(
            document.get("artifact_hash"),
            f"{field_name}.artifact_hash",
        ),
    )


@dataclass(frozen=True, slots=True)
class CheckpointWitnessRecord:
    """Privacy-preserving synthetic witness identity revision and role."""

    witness_id: str
    identity_revision: str
    role: CheckpointWitnessRole

    def __post_init__(self) -> None:
        _require_non_empty(self.witness_id, "witness_id")
        _require_non_empty(self.identity_revision, "identity_revision")

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CheckpointWitnessRecord:
        _reject_unknown(
            document,
            {"witness_id", "identity_revision", "role"},
            "checkpoint witness record",
        )
        return cls(
            witness_id=_string(document.get("witness_id"), "witness_id"),
            identity_revision=_string(
                document.get("identity_revision"),
                "identity_revision",
            ),
            role=CheckpointWitnessRole(_string(document.get("role"), "role")),
        )


@dataclass(frozen=True, slots=True)
class CheckpointWitnessRegistrySnapshot:
    """Frozen registry of synthetic witnesses permitted to observe checkpoints."""

    registry_id: str
    registry_version: str
    status: CheckpointWitnessRegistryLifecycle
    witnesses: tuple[CheckpointWitnessRecord, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.registry_id, "registry_id")
        _require_non_empty(self.registry_version, "registry_version")
        if not self.witnesses:
            raise CheckpointWitnessError("witness registry requires witnesses")
        witness_ids = tuple(item.witness_id for item in self.witnesses)
        if len(witness_ids) != len(set(witness_ids)):
            raise CheckpointWitnessError("witness registry IDs must be unique")
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CheckpointWitnessError(
                "witness registry hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CheckpointWitnessRegistrySnapshot:
        _reject_unknown(
            document,
            {
                "registry_id",
                "registry_version",
                "status",
                "witnesses",
                "created_at",
            },
            "checkpoint witness registry",
        )
        witnesses_value = document.get("witnesses")
        if not isinstance(witnesses_value, list):
            raise CheckpointWitnessError("witnesses must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            registry_id=_string(document.get("registry_id"), "registry_id"),
            registry_version=_string(
                document.get("registry_version"),
                "registry_version",
            ),
            status=CheckpointWitnessRegistryLifecycle(
                _string(document.get("status"), "status")
            ),
            witnesses=tuple(
                CheckpointWitnessRecord.from_document(
                    _mapping(item, "checkpoint witness record")
                )
                for item in witnesses_value
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def witness(self, witness_id: str) -> CheckpointWitnessRecord | None:
        return next(
            (item for item in self.witnesses if item.witness_id == witness_id),
            None,
        )

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.registry_id,
            artifact_version=self.registry_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.registry_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class CheckpointWitnessPolicySnapshot:
    """Frozen rules for required witnesses and conflicting-head abstention."""

    policy_id: str
    policy_version: str
    status: CheckpointWitnessPolicyLifecycle
    witness_registry_ref: VersionedArtifactRef
    required_witness_ids: tuple[str, ...]
    abstain_on_conflicting_head: bool
    forbid_vote_aggregation: bool
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        if not self.required_witness_ids:
            raise CheckpointWitnessError("witness policy requires named witnesses")
        if len(self.required_witness_ids) != len(set(self.required_witness_ids)):
            raise CheckpointWitnessError(
                "witness policy required IDs must be unique"
            )
        if not self.abstain_on_conflicting_head or not self.forbid_vote_aggregation:
            raise CheckpointWitnessError(
                "initial witness policy requires conflict abstention and forbids votes"
            )
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CheckpointWitnessError(
                "witness policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CheckpointWitnessPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "witness_registry_ref",
                "required_witness_ids",
                "abstain_on_conflicting_head",
                "forbid_vote_aggregation",
                "created_at",
            },
            "checkpoint witness policy",
        )
        required_value = document.get("required_witness_ids")
        if not isinstance(required_value, list):
            raise CheckpointWitnessError("required_witness_ids must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=CheckpointWitnessPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            witness_registry_ref=_versioned_ref(
                document.get("witness_registry_ref"),
                "witness_registry_ref",
            ),
            required_witness_ids=tuple(
                _string(item, "required_witness_id") for item in required_value
            ),
            abstain_on_conflicting_head=_boolean(
                document.get("abstain_on_conflicting_head"),
                "abstain_on_conflicting_head",
            ),
            forbid_vote_aggregation=_boolean(
                document.get("forbid_vote_aggregation"),
                "forbid_vote_aggregation",
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.policy_id,
            artifact_version=self.policy_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.policy_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class CheckpointWitnessAttestationSnapshot:
    """One immutable claim about the checkpoint head observed by a witness."""

    artifact_id: str
    attestation_id: str
    witness_id: str
    witness_identity_revision: str
    checkpoint_corpus_ref: VersionedArtifactRef
    checkpoint_log_ref: VersionedArtifactRef
    expected_head_ref: StoredArtifactRef
    observed_head_ref: StoredArtifactRef
    observation_kind: CheckpointWitnessObservationKind
    observed_at: str
    received_at: str
    note: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.attestation_id, "attestation_id"),
            (self.witness_id, "witness_id"),
            (self.witness_identity_revision, "witness_identity_revision"),
            (self.note, "note"),
        ):
            _require_non_empty(value, field_name)
        if self.artifact_id != (
            f"checkpoint-witness-attestation:{self.attestation_id}"
        ):
            raise CheckpointWitnessError(
                "witness attestation artifact ID must derive from attestation_id"
            )
        expected_kind = (
            CheckpointWitnessObservationKind.MATCHES_HEAD
            if self.observed_head_ref == self.expected_head_ref
            else CheckpointWitnessObservationKind.CONFLICTING_HEAD
        )
        if self.observation_kind is not expected_kind:
            raise CheckpointWitnessError(
                "witness observation kind must derive from exact head references"
            )
        observed = _parse_timestamp(self.observed_at, "observed_at")
        received = _parse_timestamp(self.received_at, "received_at")
        if received < observed:
            raise CheckpointWitnessError(
                "witness attestation may not be received before observation"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CheckpointWitnessError(
                "witness attestation hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CheckpointWitnessAttestationSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "attestation_id",
                "witness_id",
                "witness_identity_revision",
                "checkpoint_corpus_ref",
                "checkpoint_log_ref",
                "expected_head_ref",
                "observed_head_ref",
                "observation_kind",
                "observed_at",
                "received_at",
                "note",
            },
            "checkpoint witness attestation",
        )
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            attestation_id=_string(
                document.get("attestation_id"),
                "attestation_id",
            ),
            witness_id=_string(document.get("witness_id"), "witness_id"),
            witness_identity_revision=_string(
                document.get("witness_identity_revision"),
                "witness_identity_revision",
            ),
            checkpoint_corpus_ref=_versioned_ref(
                document.get("checkpoint_corpus_ref"),
                "checkpoint_corpus_ref",
            ),
            checkpoint_log_ref=_versioned_ref(
                document.get("checkpoint_log_ref"),
                "checkpoint_log_ref",
            ),
            expected_head_ref=StoredArtifactRef.from_document(
                _mapping(document.get("expected_head_ref"), "expected_head_ref")
            ),
            observed_head_ref=StoredArtifactRef.from_document(
                _mapping(document.get("observed_head_ref"), "observed_head_ref")
            ),
            observation_kind=CheckpointWitnessObservationKind(
                _string(document.get("observation_kind"), "observation_kind")
            ),
            observed_at=_string(document.get("observed_at"), "observed_at"),
            received_at=_string(document.get("received_at"), "received_at"),
            note=_string(document.get("note"), "note"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> CheckpointWitnessAttestationSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CheckpointWitnessError(
                "witness attestation artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "witness attestation"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise CheckpointWitnessError(
                "stored witness attestation ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise CheckpointWitnessError(
                "stored witness attestation hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise CheckpointWitnessError(
                "stored witness attestation is not canonical"
            )
        return snapshot

    def reference(self) -> StoredArtifactRef:
        return StoredArtifactRef(
            artifact_id=self.artifact_id,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.artifact_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class WitnessBoundCheckpointCorpusSnapshot:
    """Checkpoint-bound corpus plus exact witness registry, policy, and evidence."""

    corpus: CheckpointBoundRevocationCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    witness_registry_ref: VersionedArtifactRef
    witness_policy_ref: VersionedArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> WitnessBoundCheckpointCorpusSnapshot:
        refs_value = document.get("checkpoint_witness_attestation_refs")
        if not isinstance(refs_value, list):
            raise CheckpointWitnessError(
                "checkpoint_witness_attestation_refs must be an array"
            )
        return cls(
            corpus=CheckpointBoundRevocationCorpusSnapshot.from_document(document),
            predecessor_corpus_ref=_versioned_ref(
                document.get("witness_predecessor_corpus_ref"),
                "witness_predecessor_corpus_ref",
            ),
            witness_registry_ref=_versioned_ref(
                document.get("checkpoint_witness_registry_ref"),
                "checkpoint_witness_registry_ref",
            ),
            witness_policy_ref=_versioned_ref(
                document.get("checkpoint_witness_policy_ref"),
                "checkpoint_witness_policy_ref",
            ),
            witness_attestation_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(item, "checkpoint witness attestation ref")
                )
                for item in refs_value
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
class CheckpointWitnessObservationSummary:
    """Decision-facing witness observation without vote aggregation."""

    witness_id: str
    attestation_ref: StoredArtifactRef
    observation_kind: CheckpointWitnessObservationKind
    expected_head_ref: StoredArtifactRef
    observed_head_ref: StoredArtifactRef
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class CheckpointWitnessDecisionReport:
    """Canonical witness decision preserving each named observation."""

    experiment_id: str
    experiment_version: str
    witness_corpus_ref: VersionedArtifactRef
    witness_registry_ref: VersionedArtifactRef
    witness_policy_ref: VersionedArtifactRef
    checkpoint_head_ref: StoredArtifactRef
    outcome: CheckpointWitnessDecisionOutcome
    observations: tuple[CheckpointWitnessObservationSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        if not self.observations:
            raise CheckpointWitnessError(
                "witness decision requires named observations"
            )
        witness_ids = tuple(item.witness_id for item in self.observations)
        if len(witness_ids) != len(set(witness_ids)):
            raise CheckpointWitnessError(
                "witness decision observation IDs must be unique"
            )
        expected = (
            CheckpointWitnessDecisionOutcome.ABSTAIN
            if any(item.abstention.triggered for item in self.observations)
            else CheckpointWitnessDecisionOutcome.EXECUTE
        )
        if self.outcome is not expected:
            raise CheckpointWitnessError(
                "witness decision outcome differs from observations"
            )
        _parse_timestamp(self.evaluated_at, "evaluated_at")

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "checkpoint-witness-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredCheckpointWitnessEvidence:
    """Stored registry, policy, and exact witness attestation population."""

    corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    attestation_refs: tuple[StoredArtifactRef, ...]
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...]

    def __post_init__(self) -> None:
        if len(self.attestation_refs) != len(self.attestations):
            raise CheckpointWitnessError(
                "stored witness evidence requires one ref per attestation"
            )


def _load_attestation(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> CheckpointWitnessAttestationSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    attestation = CheckpointWitnessAttestationSnapshot.from_artifact(artifact)
    if attestation.reference() != reference:
        raise ArtifactIntegrityError(
            "stored witness attestation reference differs from corpus"
        )
    return attestation


def load_checkpoint_witness_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: WitnessBoundCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
) -> StoredCheckpointWitnessEvidence:
    """Load and reverify witness corpus, registry, policy, and attestations."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored witness-bound corpus differs from expected"
        )
    registry_artifact = store.get(
        registry.registry_id,
        expected_hash=registry.artifact_hash,
    )
    if registry_artifact.payload != registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored witness registry differs from expected"
        )
    policy_artifact = store.get(
        policy.policy_id,
        expected_hash=policy.artifact_hash,
    )
    if policy_artifact.payload != policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored witness policy differs from expected"
        )
    attestations = tuple(
        _load_attestation(store, reference)
        for reference in corpus.witness_attestation_refs
    )
    return StoredCheckpointWitnessEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        witness_registry_ref=store.reference(registry.registry_id),
        witness_policy_ref=store.reference(policy.policy_id),
        attestation_refs=tuple(item.reference() for item in attestations),
        attestations=attestations,
    )


def validate_checkpoint_witness_attestations(
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: CredentialRevocationLedgerCheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> CheckpointWitnessDecisionReport:
    """Validate exact witness identity and preserve conflicts without voting."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise CheckpointWitnessError(
            "only a frozen experiment plan may pass witness validation"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise CheckpointWitnessError(
            "experiment plan differs from witness-bound corpus"
        )
    if corpus.witness_registry_ref != registry.reference():
        raise CheckpointWitnessError(
            "witness registry reference differs from corpus"
        )
    if corpus.witness_policy_ref != policy.reference():
        raise CheckpointWitnessError(
            "witness policy reference differs from corpus"
        )
    if registry.status is not CheckpointWitnessRegistryLifecycle.ACCEPTED:
        raise CheckpointWitnessError("witness registry must be accepted")
    if policy.status is not CheckpointWitnessPolicyLifecycle.ACCEPTED:
        raise CheckpointWitnessError("witness policy must be accepted")
    if policy.witness_registry_ref != registry.reference():
        raise CheckpointWitnessError(
            "witness policy registry reference differs"
        )
    registry_ids = tuple(item.witness_id for item in registry.witnesses)
    if policy.required_witness_ids != registry_ids:
        raise CheckpointWitnessError(
            "initial witness policy must require the exact registry order"
        )
    if tuple(item.reference() for item in attestations) != (
        corpus.witness_attestation_refs
    ):
        raise CheckpointWitnessError(
            "witness attestation population differs from corpus"
        )
    if len(attestations) != len(policy.required_witness_ids):
        raise CheckpointWitnessError(
            "witness attestation population differs from required witnesses"
        )
    if head_checkpoint.reference() != corpus.corpus.checkpoint_head_ref:
        raise CheckpointWitnessError(
            "witness validation head differs from checkpoint corpus"
        )

    observations: list[CheckpointWitnessObservationSummary] = []
    seen: set[str] = set()
    for expected_witness_id, attestation in zip(
        policy.required_witness_ids,
        attestations,
        strict=True,
    ):
        if attestation.witness_id in seen:
            raise CheckpointWitnessError(
                "witness attestations must identify unique witnesses"
            )
        seen.add(attestation.witness_id)
        if attestation.witness_id != expected_witness_id:
            raise CheckpointWitnessError(
                "witness attestation order differs from required registry order"
            )
        witness = registry.witness(attestation.witness_id)
        if witness is None:
            raise CheckpointWitnessError(
                f"unknown checkpoint witness {attestation.witness_id!r}"
            )
        if witness.identity_revision != attestation.witness_identity_revision:
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: identity revision differs"
            )
        if witness.role is not CheckpointWitnessRole.CHECKPOINT_OBSERVER:
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: role may not observe checkpoints"
            )
        if attestation.checkpoint_corpus_ref != corpus.predecessor_corpus_ref:
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: checkpoint corpus reference differs"
            )
        if attestation.checkpoint_log_ref != corpus.corpus.checkpoint_log_ref:
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: checkpoint log reference differs"
            )
        if attestation.expected_head_ref != head_checkpoint.reference():
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: expected checkpoint head differs"
            )
        if _parse_timestamp(attestation.observed_at, "observed_at") < (
            _parse_timestamp(head_checkpoint.published_at, "published_at")
        ):
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: observation predates checkpoint publication"
            )
        if _parse_timestamp(attestation.received_at, "received_at") > evaluated:
            raise CheckpointWitnessError(
                f"{attestation.witness_id}: attestation received after evaluation"
            )
        reasons: list[str] = []
        if (
            policy.abstain_on_conflicting_head
            and attestation.observation_kind
            is CheckpointWitnessObservationKind.CONFLICTING_HEAD
        ):
            reasons.append(
                f"checkpoint-witness-conflicting-head:{attestation.witness_id}"
            )
        observations.append(
            CheckpointWitnessObservationSummary(
                witness_id=attestation.witness_id,
                attestation_ref=attestation.reference(),
                observation_kind=attestation.observation_kind,
                expected_head_ref=attestation.expected_head_ref,
                observed_head_ref=attestation.observed_head_ref,
                abstention=SystemAbstention(
                    triggered=bool(reasons),
                    reasons=tuple(reasons),
                ),
            )
        )

    outcome = (
        CheckpointWitnessDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in observations)
        else CheckpointWitnessDecisionOutcome.EXECUTE
    )
    return CheckpointWitnessDecisionReport(
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


def persist_witness_bound_checkpoint_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundCheckpointCorpusSnapshot,
    predecessor_corpus: CheckpointBoundRevocationCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: CredentialRevocationLedgerCheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> StoredCheckpointWitnessEvidence:
    """Persist registry, policy, attestations, and publish the corpus last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise CheckpointWitnessError(
            "predecessor checkpoint corpus reference differs"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise CheckpointWitnessError(
            "witness corpus content population differs"
        )
    if predecessor_corpus.checkpoint_policy_ref != (
        corpus.corpus.checkpoint_policy_ref
    ):
        raise CheckpointWitnessError(
            "witness corpus checkpoint policy differs from predecessor"
        )
    if predecessor_corpus.checkpoint_log_ref != corpus.corpus.checkpoint_log_ref:
        raise CheckpointWitnessError(
            "witness corpus checkpoint log differs from predecessor"
        )
    if predecessor_corpus.checkpoint_head_ref != (
        corpus.corpus.checkpoint_head_ref
    ):
        raise CheckpointWitnessError(
            "witness corpus checkpoint head differs from predecessor"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored predecessor checkpoint corpus differs"
        )
    validate_checkpoint_witness_attestations(
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
    return load_checkpoint_witness_evidence(
        store,
        corpus=corpus,
        registry=registry,
        policy=policy,
    )
