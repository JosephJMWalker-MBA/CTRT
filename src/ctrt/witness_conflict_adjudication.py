"""Authorized adjudication of conflicting checkpoint-witness observations."""

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
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessDecisionReport,
    CheckpointWitnessObservationKind,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
    StoredCheckpointWitnessEvidence,
    WitnessBoundCheckpointCorpusSnapshot,
    load_checkpoint_witness_evidence,
    validate_checkpoint_witness_attestations,
)
from ctrt.confidence import SystemAbstention
from ctrt.credential_revocation_checkpoints import (
    CredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class WitnessConflictAdjudicationError(ValueError):
    """Raised when witness-conflict adjudication evidence is invalid."""


class WitnessConflictAdjudicatorRegistryLifecycle(StrEnum):
    """Governance state of an adjudicator registry."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class WitnessConflictAdjudicationPolicyLifecycle(StrEnum):
    """Governance state of an adjudication policy."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class WitnessConflictAdjudicatorRole(StrEnum):
    """Authorized role for deciding a checkpoint-witness conflict."""

    WITNESS_CONFLICT_ADJUDICATOR = "witness_conflict_adjudicator"


class WitnessConflictResolutionStatus(StrEnum):
    """Lifecycle state of one witness-conflict case."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class WitnessConflictAdjudicationOutcome(StrEnum):
    """Whether adjudication permits downstream checkpoint execution."""

    EXECUTE = "execute"
    ABSTAIN = "abstain"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise WitnessConflictAdjudicationError(f"{field_name} must not be empty")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise WitnessConflictAdjudicationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise WitnessConflictAdjudicationError(
            f"{field_name} must include a timezone"
        )
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WitnessConflictAdjudicationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise WitnessConflictAdjudicationError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WitnessConflictAdjudicationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise WitnessConflictAdjudicationError(f"{field_name} must be a boolean")
    return value


def _reject_unknown(
    document: Mapping[str, object],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise WitnessConflictAdjudicationError(
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


def _stored_ref(value: object, field_name: str) -> StoredArtifactRef:
    return StoredArtifactRef.from_document(_mapping(value, field_name))


@dataclass(frozen=True, slots=True)
class WitnessConflictAdjudicatorRecord:
    """Privacy-preserving adjudicator identity revision and role."""

    adjudicator_id: str
    identity_revision: str
    role: WitnessConflictAdjudicatorRole

    def __post_init__(self) -> None:
        _require_non_empty(self.adjudicator_id, "adjudicator_id")
        _require_non_empty(self.identity_revision, "identity_revision")

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> WitnessConflictAdjudicatorRecord:
        _reject_unknown(
            document,
            {"adjudicator_id", "identity_revision", "role"},
            "witness conflict adjudicator",
        )
        return cls(
            adjudicator_id=_string(
                document.get("adjudicator_id"),
                "adjudicator_id",
            ),
            identity_revision=_string(
                document.get("identity_revision"),
                "identity_revision",
            ),
            role=WitnessConflictAdjudicatorRole(
                _string(document.get("role"), "role")
            ),
        )


@dataclass(frozen=True, slots=True)
class WitnessConflictAdjudicatorRegistrySnapshot:
    """Frozen registry of identities permitted to adjudicate witness conflicts."""

    registry_id: str
    registry_version: str
    status: WitnessConflictAdjudicatorRegistryLifecycle
    adjudicators: tuple[WitnessConflictAdjudicatorRecord, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.registry_id, "registry_id")
        _require_non_empty(self.registry_version, "registry_version")
        if not self.adjudicators:
            raise WitnessConflictAdjudicationError(
                "adjudicator registry requires adjudicators"
            )
        identities = tuple(item.adjudicator_id for item in self.adjudicators)
        if len(identities) != len(set(identities)):
            raise WitnessConflictAdjudicationError(
                "adjudicator registry IDs must be unique"
            )
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise WitnessConflictAdjudicationError(
                "adjudicator registry hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> WitnessConflictAdjudicatorRegistrySnapshot:
        _reject_unknown(
            document,
            {
                "registry_id",
                "registry_version",
                "status",
                "adjudicators",
                "created_at",
            },
            "witness conflict adjudicator registry",
        )
        values = document.get("adjudicators")
        if not isinstance(values, list):
            raise WitnessConflictAdjudicationError(
                "adjudicators must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            registry_id=_string(document.get("registry_id"), "registry_id"),
            registry_version=_string(
                document.get("registry_version"),
                "registry_version",
            ),
            status=WitnessConflictAdjudicatorRegistryLifecycle(
                _string(document.get("status"), "status")
            ),
            adjudicators=tuple(
                WitnessConflictAdjudicatorRecord.from_document(
                    _mapping(item, "witness conflict adjudicator")
                )
                for item in values
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def adjudicator(
        self,
        adjudicator_id: str,
    ) -> WitnessConflictAdjudicatorRecord | None:
        return next(
            (
                item
                for item in self.adjudicators
                if item.adjudicator_id == adjudicator_id
            ),
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
class WitnessConflictAdjudicationPolicySnapshot:
    """Frozen fail-closed rules for resolving witness head conflicts."""

    policy_id: str
    policy_version: str
    status: WitnessConflictAdjudicationPolicyLifecycle
    adjudicator_registry_ref: VersionedArtifactRef
    required_adjudicator_ids: tuple[str, ...]
    abstain_on_pending: bool
    abstain_on_unresolved: bool
    resolution_must_select_declared_head: bool
    forbid_vote_aggregation: bool
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        if not self.required_adjudicator_ids:
            raise WitnessConflictAdjudicationError(
                "adjudication policy requires named adjudicators"
            )
        if len(self.required_adjudicator_ids) != len(
            set(self.required_adjudicator_ids)
        ):
            raise WitnessConflictAdjudicationError(
                "adjudication policy IDs must be unique"
            )
        if not (
            self.abstain_on_pending
            and self.abstain_on_unresolved
            and self.resolution_must_select_declared_head
            and self.forbid_vote_aggregation
        ):
            raise WitnessConflictAdjudicationError(
                "initial adjudication policy must fail closed and forbid voting"
            )
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise WitnessConflictAdjudicationError(
                "adjudication policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> WitnessConflictAdjudicationPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "adjudicator_registry_ref",
                "required_adjudicator_ids",
                "abstain_on_pending",
                "abstain_on_unresolved",
                "resolution_must_select_declared_head",
                "forbid_vote_aggregation",
                "created_at",
            },
            "witness conflict adjudication policy",
        )
        values = document.get("required_adjudicator_ids")
        if not isinstance(values, list):
            raise WitnessConflictAdjudicationError(
                "required_adjudicator_ids must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=WitnessConflictAdjudicationPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            adjudicator_registry_ref=_versioned_ref(
                document.get("adjudicator_registry_ref"),
                "adjudicator_registry_ref",
            ),
            required_adjudicator_ids=tuple(
                _string(item, "required_adjudicator_id") for item in values
            ),
            abstain_on_pending=_boolean(
                document.get("abstain_on_pending"),
                "abstain_on_pending",
            ),
            abstain_on_unresolved=_boolean(
                document.get("abstain_on_unresolved"),
                "abstain_on_unresolved",
            ),
            resolution_must_select_declared_head=_boolean(
                document.get("resolution_must_select_declared_head"),
                "resolution_must_select_declared_head",
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
class WitnessForkEvidence:
    """One conflicting witness observation preserved for adjudication."""

    witness_id: str
    attestation_ref: StoredArtifactRef
    expected_head_ref: StoredArtifactRef
    observed_head_ref: StoredArtifactRef

    def __post_init__(self) -> None:
        _require_non_empty(self.witness_id, "witness_id")
        if self.expected_head_ref == self.observed_head_ref:
            raise WitnessConflictAdjudicationError(
                "fork evidence requires different expected and observed heads"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> WitnessForkEvidence:
        _reject_unknown(
            document,
            {
                "witness_id",
                "attestation_ref",
                "expected_head_ref",
                "observed_head_ref",
            },
            "witness fork evidence",
        )
        return cls(
            witness_id=_string(document.get("witness_id"), "witness_id"),
            attestation_ref=_stored_ref(
                document.get("attestation_ref"),
                "attestation_ref",
            ),
            expected_head_ref=_stored_ref(
                document.get("expected_head_ref"),
                "expected_head_ref",
            ),
            observed_head_ref=_stored_ref(
                document.get("observed_head_ref"),
                "observed_head_ref",
            ),
        )


@dataclass(frozen=True, slots=True)
class PreservedWitnessDissent:
    """A conflicting witness observation retained after adjudication."""

    witness_id: str
    attestation_ref: StoredArtifactRef
    observed_head_ref: StoredArtifactRef
    note: str

    def __post_init__(self) -> None:
        _require_non_empty(self.witness_id, "witness_id")
        _require_non_empty(self.note, "note")

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> PreservedWitnessDissent:
        _reject_unknown(
            document,
            {"witness_id", "attestation_ref", "observed_head_ref", "note"},
            "preserved witness dissent",
        )
        return cls(
            witness_id=_string(document.get("witness_id"), "witness_id"),
            attestation_ref=_stored_ref(
                document.get("attestation_ref"),
                "attestation_ref",
            ),
            observed_head_ref=_stored_ref(
                document.get("observed_head_ref"),
                "observed_head_ref",
            ),
            note=_string(document.get("note"), "note"),
        )


@dataclass(frozen=True, slots=True)
class WitnessConflictAdjudicationSnapshot:
    """Immutable adjudication record preserving conflict and dissent."""

    artifact_id: str
    adjudication_id: str
    witness_predecessor_corpus_ref: VersionedArtifactRef
    witness_registry_ref: VersionedArtifactRef
    witness_policy_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    adjudication_policy_ref: VersionedArtifactRef
    checkpoint_head_ref: StoredArtifactRef
    status: WitnessConflictResolutionStatus
    adjudicator_id: str | None
    adjudicator_identity_revision: str | None
    selected_head_ref: StoredArtifactRef | None
    fork_evidence: tuple[WitnessForkEvidence, ...]
    preserved_dissent: tuple[PreservedWitnessDissent, ...]
    rationale: str
    decided_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.adjudication_id, "adjudication_id")
        _require_non_empty(self.rationale, "rationale")
        if self.artifact_id != (
            f"witness-conflict-adjudication:{self.adjudication_id}"
        ):
            raise WitnessConflictAdjudicationError(
                "adjudication artifact ID must derive from adjudication_id"
            )
        fork_ids = tuple(item.witness_id for item in self.fork_evidence)
        dissent_ids = tuple(item.witness_id for item in self.preserved_dissent)
        if len(fork_ids) != len(set(fork_ids)):
            raise WitnessConflictAdjudicationError(
                "fork evidence witness IDs must be unique"
            )
        if len(dissent_ids) != len(set(dissent_ids)):
            raise WitnessConflictAdjudicationError(
                "preserved dissent witness IDs must be unique"
            )
        if self.status is WitnessConflictResolutionStatus.NOT_REQUIRED:
            if (
                self.fork_evidence
                or self.preserved_dissent
                or self.adjudicator_id is not None
                or self.adjudicator_identity_revision is not None
                or self.selected_head_ref is not None
            ):
                raise WitnessConflictAdjudicationError(
                    "not-required adjudication may not contain conflict decisions"
                )
        elif self.status is WitnessConflictResolutionStatus.PENDING:
            if not self.fork_evidence:
                raise WitnessConflictAdjudicationError(
                    "pending adjudication requires fork evidence"
                )
            if (
                self.adjudicator_id is not None
                or self.adjudicator_identity_revision is not None
                or self.selected_head_ref is not None
                or self.preserved_dissent
            ):
                raise WitnessConflictAdjudicationError(
                    "pending adjudication may not claim a decision"
                )
        else:
            if not self.fork_evidence:
                raise WitnessConflictAdjudicationError(
                    "decided adjudication requires fork evidence"
                )
            if (
                self.adjudicator_id is None
                or self.adjudicator_identity_revision is None
            ):
                raise WitnessConflictAdjudicationError(
                    "decided adjudication requires adjudicator identity"
                )
            if fork_ids != dissent_ids:
                raise WitnessConflictAdjudicationError(
                    "decided adjudication must preserve dissent for every conflict"
                )
            for fork, dissent in zip(
                self.fork_evidence,
                self.preserved_dissent,
                strict=True,
            ):
                if (
                    fork.attestation_ref != dissent.attestation_ref
                    or fork.observed_head_ref != dissent.observed_head_ref
                ):
                    raise WitnessConflictAdjudicationError(
                        "preserved dissent must match exact fork evidence"
                    )
            if self.status is WitnessConflictResolutionStatus.RESOLVED:
                if self.selected_head_ref is None:
                    raise WitnessConflictAdjudicationError(
                        "resolved adjudication requires selected head"
                    )
            elif self.selected_head_ref is not None:
                raise WitnessConflictAdjudicationError(
                    "unresolved adjudication may not select a head"
                )
        _parse_timestamp(self.decided_at, "decided_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise WitnessConflictAdjudicationError(
                "adjudication hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> WitnessConflictAdjudicationSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "adjudication_id",
                "witness_predecessor_corpus_ref",
                "witness_registry_ref",
                "witness_policy_ref",
                "adjudicator_registry_ref",
                "adjudication_policy_ref",
                "checkpoint_head_ref",
                "status",
                "adjudicator_id",
                "adjudicator_identity_revision",
                "selected_head_ref",
                "fork_evidence",
                "preserved_dissent",
                "rationale",
                "decided_at",
            },
            "witness conflict adjudication",
        )
        fork_values = document.get("fork_evidence")
        dissent_values = document.get("preserved_dissent")
        if not isinstance(fork_values, list):
            raise WitnessConflictAdjudicationError(
                "fork_evidence must be an array"
            )
        if not isinstance(dissent_values, list):
            raise WitnessConflictAdjudicationError(
                "preserved_dissent must be an array"
            )
        selected_value = document.get("selected_head_ref")
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            adjudication_id=_string(
                document.get("adjudication_id"),
                "adjudication_id",
            ),
            witness_predecessor_corpus_ref=_versioned_ref(
                document.get("witness_predecessor_corpus_ref"),
                "witness_predecessor_corpus_ref",
            ),
            witness_registry_ref=_versioned_ref(
                document.get("witness_registry_ref"),
                "witness_registry_ref",
            ),
            witness_policy_ref=_versioned_ref(
                document.get("witness_policy_ref"),
                "witness_policy_ref",
            ),
            adjudicator_registry_ref=_versioned_ref(
                document.get("adjudicator_registry_ref"),
                "adjudicator_registry_ref",
            ),
            adjudication_policy_ref=_versioned_ref(
                document.get("adjudication_policy_ref"),
                "adjudication_policy_ref",
            ),
            checkpoint_head_ref=_stored_ref(
                document.get("checkpoint_head_ref"),
                "checkpoint_head_ref",
            ),
            status=WitnessConflictResolutionStatus(
                _string(document.get("status"), "status")
            ),
            adjudicator_id=_optional_string(
                document.get("adjudicator_id"),
                "adjudicator_id",
            ),
            adjudicator_identity_revision=_optional_string(
                document.get("adjudicator_identity_revision"),
                "adjudicator_identity_revision",
            ),
            selected_head_ref=(
                None
                if selected_value is None
                else _stored_ref(selected_value, "selected_head_ref")
            ),
            fork_evidence=tuple(
                WitnessForkEvidence.from_document(
                    _mapping(item, "witness fork evidence")
                )
                for item in fork_values
            ),
            preserved_dissent=tuple(
                PreservedWitnessDissent.from_document(
                    _mapping(item, "preserved witness dissent")
                )
                for item in dissent_values
            ),
            rationale=_string(document.get("rationale"), "rationale"),
            decided_at=_string(document.get("decided_at"), "decided_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> WitnessConflictAdjudicationSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WitnessConflictAdjudicationError(
                "adjudication artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "adjudication"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise WitnessConflictAdjudicationError(
                "stored adjudication ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise WitnessConflictAdjudicationError(
                "stored adjudication hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise WitnessConflictAdjudicationError(
                "stored adjudication is not canonical"
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
class AdjudicationBoundWitnessCorpusSnapshot:
    """Witness-bound corpus plus exact adjudication authority and record."""

    corpus: WitnessBoundCheckpointCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    adjudication_policy_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicationBoundWitnessCorpusSnapshot:
        return cls(
            corpus=WitnessBoundCheckpointCorpusSnapshot.from_document(document),
            predecessor_corpus_ref=_versioned_ref(
                document.get("adjudication_predecessor_corpus_ref"),
                "adjudication_predecessor_corpus_ref",
            ),
            adjudicator_registry_ref=_versioned_ref(
                document.get("witness_conflict_adjudicator_registry_ref"),
                "witness_conflict_adjudicator_registry_ref",
            ),
            adjudication_policy_ref=_versioned_ref(
                document.get("witness_conflict_adjudication_policy_ref"),
                "witness_conflict_adjudication_policy_ref",
            ),
            adjudication_ref=_stored_ref(
                document.get("witness_conflict_adjudication_ref"),
                "witness_conflict_adjudication_ref",
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
class WitnessConflictAdjudicationDecisionReport:
    """Canonical decision preserving conflict, rationale, and dissent."""

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
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _require_non_empty(self.rationale, "rationale")
        expected = (
            WitnessConflictAdjudicationOutcome.EXECUTE
            if (
                self.witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
                or self.resolution_status
                is WitnessConflictResolutionStatus.RESOLVED
            )
            else WitnessConflictAdjudicationOutcome.ABSTAIN
        )
        if self.outcome is not expected:
            raise WitnessConflictAdjudicationError(
                "adjudication outcome differs from witness and resolution state"
            )
        if self.abstention.triggered != (
            self.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
        ):
            raise WitnessConflictAdjudicationError(
                "adjudication abstention differs from outcome"
            )
        _parse_timestamp(self.evaluated_at, "evaluated_at")

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "witness-conflict-adjudication-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredWitnessConflictAdjudicationEvidence:
    """Stored witness evidence plus adjudication authority and record."""

    corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    witness_evidence: StoredCheckpointWitnessEvidence


def load_witness_conflict_adjudication_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: AdjudicationBoundWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredWitnessConflictAdjudicationEvidence:
    """Load and reverify the complete adjudication-bound evidence graph."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored adjudication-bound corpus differs from expected"
        )
    registry_artifact = store.get(
        adjudicator_registry.registry_id,
        expected_hash=adjudicator_registry.artifact_hash,
    )
    if registry_artifact.payload != adjudicator_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudicator registry differs from expected"
        )
    policy_artifact = store.get(
        adjudication_policy.policy_id,
        expected_hash=adjudication_policy.artifact_hash,
    )
    if policy_artifact.payload != adjudication_policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudication policy differs from expected"
        )
    stored_adjudication = WitnessConflictAdjudicationSnapshot.from_artifact(
        store.get(
            adjudication.artifact_id,
            expected_hash=adjudication.artifact_hash,
        )
    )
    if stored_adjudication.reference() != corpus.adjudication_ref:
        raise ArtifactIntegrityError(
            "stored adjudication reference differs from corpus"
        )
    witness_evidence = load_checkpoint_witness_evidence(
        store,
        corpus=corpus.corpus,
        registry=witness_registry,
        policy=witness_policy,
    )
    return StoredWitnessConflictAdjudicationEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        adjudicator_registry_ref=store.reference(
            adjudicator_registry.registry_id
        ),
        adjudication_policy_ref=store.reference(adjudication_policy.policy_id),
        adjudication_ref=stored_adjudication.reference(),
        witness_evidence=witness_evidence,
    )


def validate_witness_conflict_adjudication(
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    witness_decision: CheckpointWitnessDecisionReport,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> WitnessConflictAdjudicationDecisionReport:
    """Validate authority and conflict resolution without counting witnesses."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise WitnessConflictAdjudicationError(
            "only a frozen plan may pass witness-conflict adjudication"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise WitnessConflictAdjudicationError(
            "experiment plan differs from adjudication-bound corpus"
        )
    if corpus.adjudicator_registry_ref != adjudicator_registry.reference():
        raise WitnessConflictAdjudicationError(
            "adjudicator registry reference differs from corpus"
        )
    if corpus.adjudication_policy_ref != adjudication_policy.reference():
        raise WitnessConflictAdjudicationError(
            "adjudication policy reference differs from corpus"
        )
    if corpus.adjudication_ref != adjudication.reference():
        raise WitnessConflictAdjudicationError(
            "adjudication record reference differs from corpus"
        )
    if (
        adjudicator_registry.status
        is not WitnessConflictAdjudicatorRegistryLifecycle.ACCEPTED
    ):
        raise WitnessConflictAdjudicationError(
            "adjudicator registry must be accepted"
        )
    if (
        adjudication_policy.status
        is not WitnessConflictAdjudicationPolicyLifecycle.ACCEPTED
    ):
        raise WitnessConflictAdjudicationError(
            "adjudication policy must be accepted"
        )
    if (
        adjudication_policy.adjudicator_registry_ref
        != adjudicator_registry.reference()
    ):
        raise WitnessConflictAdjudicationError(
            "adjudication policy registry reference differs"
        )
    registry_ids = tuple(
        item.adjudicator_id for item in adjudicator_registry.adjudicators
    )
    if adjudication_policy.required_adjudicator_ids != registry_ids:
        raise WitnessConflictAdjudicationError(
            "initial adjudication policy must require exact registry order"
        )
    if adjudication.witness_predecessor_corpus_ref != corpus.predecessor_corpus_ref:
        raise WitnessConflictAdjudicationError(
            "adjudication predecessor corpus reference differs"
        )
    if adjudication.witness_registry_ref != witness_registry.reference():
        raise WitnessConflictAdjudicationError(
            "adjudication witness registry reference differs"
        )
    if adjudication.witness_policy_ref != witness_policy.reference():
        raise WitnessConflictAdjudicationError(
            "adjudication witness policy reference differs"
        )
    if adjudication.adjudicator_registry_ref != adjudicator_registry.reference():
        raise WitnessConflictAdjudicationError(
            "adjudication registry reference differs"
        )
    if adjudication.adjudication_policy_ref != adjudication_policy.reference():
        raise WitnessConflictAdjudicationError(
            "adjudication policy reference differs"
        )
    if adjudication.checkpoint_head_ref != witness_decision.checkpoint_head_ref:
        raise WitnessConflictAdjudicationError(
            "adjudication checkpoint head differs from witness decision"
        )
    if _parse_timestamp(adjudication.decided_at, "decided_at") > evaluated:
        raise WitnessConflictAdjudicationError(
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
        if item.observation_kind
        is CheckpointWitnessObservationKind.CONFLICTING_HEAD
    )
    if conflicts != adjudication.fork_evidence:
        raise WitnessConflictAdjudicationError(
            "adjudication fork evidence differs from witness observations"
        )
    if not conflicts:
        if (
            witness_decision.outcome
            is not CheckpointWitnessDecisionOutcome.EXECUTE
            or adjudication.status
            is not WitnessConflictResolutionStatus.NOT_REQUIRED
        ):
            raise WitnessConflictAdjudicationError(
                "matching witnesses require not-required adjudication"
            )
    else:
        if (
            witness_decision.outcome
            is not CheckpointWitnessDecisionOutcome.ABSTAIN
            or adjudication.status
            is WitnessConflictResolutionStatus.NOT_REQUIRED
        ):
            raise WitnessConflictAdjudicationError(
                "conflicting witnesses require an adjudication state"
            )

    if adjudication.status in {
        WitnessConflictResolutionStatus.RESOLVED,
        WitnessConflictResolutionStatus.UNRESOLVED,
    }:
        if adjudication.adjudicator_id is None:
            raise WitnessConflictAdjudicationError(
                "decided adjudication requires adjudicator"
            )
        record = adjudicator_registry.adjudicator(adjudication.adjudicator_id)
        if record is None:
            raise WitnessConflictAdjudicationError(
                f"unknown adjudicator {adjudication.adjudicator_id!r}"
            )
        if record.identity_revision != adjudication.adjudicator_identity_revision:
            raise WitnessConflictAdjudicationError(
                "adjudicator identity revision differs"
            )
        if (
            record.role
            is not WitnessConflictAdjudicatorRole.WITNESS_CONFLICT_ADJUDICATOR
        ):
            raise WitnessConflictAdjudicationError(
                "adjudicator role may not resolve witness conflicts"
            )
    if (
        adjudication.status is WitnessConflictResolutionStatus.RESOLVED
        and adjudication_policy.resolution_must_select_declared_head
        and adjudication.selected_head_ref != witness_decision.checkpoint_head_ref
    ):
        raise WitnessConflictAdjudicationError(
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
            f"witness-conflict-adjudication:{adjudication.status.value}",
        )
    return WitnessConflictAdjudicationDecisionReport(
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
        abstention=SystemAbstention(
            triggered=bool(reasons),
            reasons=reasons,
        ),
        evaluated_at=evaluated_at,
    )


def persist_adjudication_bound_witness_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundWitnessCorpusSnapshot,
    predecessor_corpus: WitnessBoundCheckpointCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: CredentialRevocationLedgerCheckpointSnapshot,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredWitnessConflictAdjudicationEvidence:
    """Persist all adjudication evidence and publish the corpus manifest last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise WitnessConflictAdjudicationError(
            "witness predecessor corpus reference differs"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise WitnessConflictAdjudicationError(
            "adjudication corpus content population differs"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored witness predecessor corpus differs"
        )
    witness_decision = validate_checkpoint_witness_attestations(
        plan=plan,
        corpus=corpus.corpus,
        registry=witness_registry,
        policy=witness_policy,
        head_checkpoint=head_checkpoint,
        attestations=witness_attestations,
        evaluated_at=evaluated_at,
    )
    validate_witness_conflict_adjudication(
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
            raise ArtifactIntegrityError(
                "stored adjudication graph reference differs"
            )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored adjudication corpus reference differs"
        )
    return load_witness_conflict_adjudication_evidence(
        store,
        corpus=corpus,
        witness_registry=witness_registry,
        witness_policy=witness_policy,
        adjudicator_registry=adjudicator_registry,
        adjudication_policy=adjudication_policy,
        adjudication=adjudication,
    )
