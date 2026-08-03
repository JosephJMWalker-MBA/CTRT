"""Immutable checkpoints for append-only credential revocation ledgers."""

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
from ctrt.credential_revocation_ledger import (
    CredentialRevocationLedgerSnapshot,
    RevocationBoundCredentialCorpusSnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class CredentialRevocationCheckpointError(ValueError):
    """Raised when checkpoint provenance or sequencing is invalid."""


class CredentialRevocationCheckpointPolicyLifecycle(StrEnum):
    """Governance state of one checkpoint policy."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class CredentialRevocationCheckpointLogLifecycle(StrEnum):
    """Governance state of one immutable checkpoint population."""

    DRAFT = "draft"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise CredentialRevocationCheckpointError(
            f"{field_name} must not be empty"
        )


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CredentialRevocationCheckpointError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise CredentialRevocationCheckpointError(
            f"{field_name} must include a timezone"
        )
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CredentialRevocationCheckpointError(
            f"{field_name} must be an object"
        )
    if any(not isinstance(key, str) for key in value):
        raise CredentialRevocationCheckpointError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CredentialRevocationCheckpointError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise CredentialRevocationCheckpointError(
            f"{field_name} must be a boolean"
        )
    return value


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CredentialRevocationCheckpointError(
            f"{field_name} must be an integer"
        )
    return value


def _reject_unknown(
    document: Mapping[str, object],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise CredentialRevocationCheckpointError(
            f"{field_name} contains unsupported fields: {', '.join(unknown)}"
        )


def _versioned_ref(value: object, field_name: str) -> VersionedArtifactRef:
    document = _mapping(value, field_name)
    return VersionedArtifactRef(
        artifact_id=_string(
            document.get("artifact_id"),
            f"{field_name}.artifact_id",
        ),
        artifact_version=_string(
            document.get("artifact_version"),
            f"{field_name}.artifact_version",
        ),
        artifact_hash=_string(
            document.get("artifact_hash"),
            f"{field_name}.artifact_hash",
        ),
    )


def _stored_ref_or_none(
    value: object,
    field_name: str,
) -> StoredArtifactRef | None:
    if value is None:
        return None
    return StoredArtifactRef.from_document(_mapping(value, field_name))


def _event_population_hash(event_refs: tuple[StoredArtifactRef, ...]) -> str:
    payload = canonical_json_bytes(
        {
            "event_refs": [
                {
                    "artifact_id": item.artifact_id,
                    "artifact_hash": item.artifact_hash,
                    "canonicalization_version": item.canonicalization_version,
                    "media_type": item.media_type,
                }
                for item in event_refs
            ]
        }
    )
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True, slots=True)
class CredentialRevocationCheckpointPolicySnapshot:
    """Frozen rules for sequential checkpoint publication."""

    policy_id: str
    policy_version: str
    status: CredentialRevocationCheckpointPolicyLifecycle
    require_exact_event_order: bool
    require_prefix_extension: bool
    require_contiguous_sequence: bool
    require_monotonic_publication_time: bool
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        _parse_timestamp(self.created_at, "created_at")
        if not all(
            (
                self.require_exact_event_order,
                self.require_prefix_extension,
                self.require_contiguous_sequence,
                self.require_monotonic_publication_time,
            )
        ):
            raise CredentialRevocationCheckpointError(
                "initial checkpoint policy requires exact ordered, contiguous, "
                "prefix-extending publication"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CredentialRevocationCheckpointError(
                "checkpoint policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialRevocationCheckpointPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "require_exact_event_order",
                "require_prefix_extension",
                "require_contiguous_sequence",
                "require_monotonic_publication_time",
                "created_at",
            },
            "credential revocation checkpoint policy",
        )
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=CredentialRevocationCheckpointPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            require_exact_event_order=_boolean(
                document.get("require_exact_event_order"),
                "require_exact_event_order",
            ),
            require_prefix_extension=_boolean(
                document.get("require_prefix_extension"),
                "require_prefix_extension",
            ),
            require_contiguous_sequence=_boolean(
                document.get("require_contiguous_sequence"),
                "require_contiguous_sequence",
            ),
            require_monotonic_publication_time=_boolean(
                document.get("require_monotonic_publication_time"),
                "require_monotonic_publication_time",
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
class CredentialRevocationLedgerCheckpointSnapshot:
    """One immutable publication checkpoint for an ordered ledger state."""

    artifact_id: str
    checkpoint_id: str
    sequence_number: int
    revocation_corpus_ref: VersionedArtifactRef
    revocation_ledger_ref: VersionedArtifactRef
    event_refs: tuple[StoredArtifactRef, ...]
    event_count: int
    event_population_hash: str
    predecessor_checkpoint_ref: StoredArtifactRef | None
    published_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.checkpoint_id, "checkpoint_id")
        if self.artifact_id != (
            f"credential-revocation-checkpoint:{self.checkpoint_id}"
        ):
            raise CredentialRevocationCheckpointError(
                "checkpoint artifact ID must derive from checkpoint_id"
            )
        if self.sequence_number < 0:
            raise CredentialRevocationCheckpointError(
                "checkpoint sequence_number must be non-negative"
            )
        if self.event_count != len(self.event_refs):
            raise CredentialRevocationCheckpointError(
                "checkpoint event_count must equal event reference count"
            )
        event_ids = tuple(item.artifact_id for item in self.event_refs)
        if len(event_ids) != len(set(event_ids)):
            raise CredentialRevocationCheckpointError(
                "checkpoint event references must be unique"
            )
        expected_population_hash = _event_population_hash(self.event_refs)
        if self.event_population_hash != expected_population_hash:
            raise CredentialRevocationCheckpointError(
                "checkpoint event population hash differs from ordered refs"
            )
        _parse_timestamp(self.published_at, "published_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CredentialRevocationCheckpointError(
                "checkpoint hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialRevocationLedgerCheckpointSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "checkpoint_id",
                "sequence_number",
                "revocation_corpus_ref",
                "revocation_ledger_ref",
                "event_refs",
                "event_count",
                "event_population_hash",
                "predecessor_checkpoint_ref",
                "published_at",
            },
            "credential revocation ledger checkpoint",
        )
        refs_value = document.get("event_refs")
        if not isinstance(refs_value, list):
            raise CredentialRevocationCheckpointError(
                "checkpoint event_refs must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            checkpoint_id=_string(
                document.get("checkpoint_id"),
                "checkpoint_id",
            ),
            sequence_number=_integer(
                document.get("sequence_number"),
                "sequence_number",
            ),
            revocation_corpus_ref=_versioned_ref(
                document.get("revocation_corpus_ref"),
                "revocation_corpus_ref",
            ),
            revocation_ledger_ref=_versioned_ref(
                document.get("revocation_ledger_ref"),
                "revocation_ledger_ref",
            ),
            event_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(item, "checkpoint event ref")
                )
                for item in refs_value
            ),
            event_count=_integer(document.get("event_count"), "event_count"),
            event_population_hash=_string(
                document.get("event_population_hash"),
                "event_population_hash",
            ),
            predecessor_checkpoint_ref=_stored_ref_or_none(
                document.get("predecessor_checkpoint_ref"),
                "predecessor_checkpoint_ref",
            ),
            published_at=_string(
                document.get("published_at"),
                "published_at",
            ),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> CredentialRevocationLedgerCheckpointSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialRevocationCheckpointError(
                "checkpoint artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(
            _mapping(document, "credential revocation checkpoint")
        )
        if snapshot.artifact_id != artifact.artifact_id:
            raise CredentialRevocationCheckpointError(
                "stored checkpoint ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise CredentialRevocationCheckpointError(
                "stored checkpoint hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise CredentialRevocationCheckpointError(
                "stored checkpoint is not canonical"
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
class CredentialRevocationCheckpointLogSnapshot:
    """Frozen ordered population of sequential revocation checkpoints."""

    log_id: str
    log_version: str
    status: CredentialRevocationCheckpointLogLifecycle
    checkpoint_policy_ref: VersionedArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    head_checkpoint_ref: StoredArtifactRef
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.log_id, "log_id")
        _require_non_empty(self.log_version, "log_version")
        _parse_timestamp(self.created_at, "created_at")
        if not self.checkpoint_refs:
            raise CredentialRevocationCheckpointError(
                "checkpoint log requires at least one checkpoint"
            )
        checkpoint_ids = tuple(item.artifact_id for item in self.checkpoint_refs)
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise CredentialRevocationCheckpointError(
                "checkpoint log references must be unique"
            )
        if self.head_checkpoint_ref != self.checkpoint_refs[-1]:
            raise CredentialRevocationCheckpointError(
                "checkpoint log head must be its final checkpoint"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CredentialRevocationCheckpointError(
                "checkpoint log hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialRevocationCheckpointLogSnapshot:
        _reject_unknown(
            document,
            {
                "log_id",
                "log_version",
                "status",
                "checkpoint_policy_ref",
                "checkpoint_refs",
                "head_checkpoint_ref",
                "created_at",
            },
            "credential revocation checkpoint log",
        )
        refs_value = document.get("checkpoint_refs")
        if not isinstance(refs_value, list):
            raise CredentialRevocationCheckpointError(
                "checkpoint_refs must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            log_id=_string(document.get("log_id"), "log_id"),
            log_version=_string(document.get("log_version"), "log_version"),
            status=CredentialRevocationCheckpointLogLifecycle(
                _string(document.get("status"), "status")
            ),
            checkpoint_policy_ref=_versioned_ref(
                document.get("checkpoint_policy_ref"),
                "checkpoint_policy_ref",
            ),
            checkpoint_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(item, "checkpoint ref")
                )
                for item in refs_value
            ),
            head_checkpoint_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("head_checkpoint_ref"),
                    "head_checkpoint_ref",
                )
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.log_id,
            artifact_version=self.log_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.log_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class CheckpointBoundRevocationCorpusSnapshot:
    """Revocation-bound corpus plus exact checkpoint policy, log, and head."""

    corpus: RevocationBoundCredentialCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    checkpoint_policy_ref: VersionedArtifactRef
    checkpoint_log_ref: VersionedArtifactRef
    checkpoint_head_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CheckpointBoundRevocationCorpusSnapshot:
        return cls(
            corpus=RevocationBoundCredentialCorpusSnapshot.from_document(
                document
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get("checkpoint_predecessor_corpus_ref"),
                "checkpoint_predecessor_corpus_ref",
            ),
            checkpoint_policy_ref=_versioned_ref(
                document.get("credential_revocation_checkpoint_policy_ref"),
                "credential_revocation_checkpoint_policy_ref",
            ),
            checkpoint_log_ref=_versioned_ref(
                document.get("credential_revocation_checkpoint_log_ref"),
                "credential_revocation_checkpoint_log_ref",
            ),
            checkpoint_head_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("credential_revocation_checkpoint_head_ref"),
                    "credential_revocation_checkpoint_head_ref",
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
class CredentialRevocationCheckpointVerificationReport:
    """Canonical proof that one frozen checkpoint chain has a valid head."""

    experiment_id: str
    experiment_version: str
    checkpoint_corpus_ref: VersionedArtifactRef
    checkpoint_policy_ref: VersionedArtifactRef
    checkpoint_log_ref: VersionedArtifactRef
    head_checkpoint_ref: StoredArtifactRef
    checkpoint_count: int
    head_sequence_number: int
    head_event_count: int
    head_event_population_hash: str
    verified_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        if self.checkpoint_count < 1:
            raise CredentialRevocationCheckpointError(
                "checkpoint verification requires checkpoints"
            )
        if self.head_sequence_number != self.checkpoint_count - 1:
            raise CredentialRevocationCheckpointError(
                "checkpoint head sequence must equal checkpoint count minus one"
            )
        if self.head_event_count < 0:
            raise CredentialRevocationCheckpointError(
                "head event count must be non-negative"
            )
        _require_non_empty(
            self.head_event_population_hash,
            "head_event_population_hash",
        )
        _parse_timestamp(self.verified_at, "verified_at")

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "credential-revocation-checkpoint-verification"
        )


@dataclass(frozen=True, slots=True)
class StoredCredentialRevocationCheckpointEvidence:
    """Stored policy, log, and exact immutable checkpoint population."""

    corpus_ref: StoredArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoints: tuple[CredentialRevocationLedgerCheckpointSnapshot, ...]

    def __post_init__(self) -> None:
        if len(self.checkpoint_refs) != len(self.checkpoints):
            raise CredentialRevocationCheckpointError(
                "stored checkpoint evidence requires one ref per checkpoint"
            )


def _load_checkpoint(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> CredentialRevocationLedgerCheckpointSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    checkpoint = CredentialRevocationLedgerCheckpointSnapshot.from_artifact(
        artifact
    )
    if checkpoint.reference() != reference:
        raise ArtifactIntegrityError(
            "stored checkpoint reference differs from log"
        )
    return checkpoint


def load_credential_revocation_checkpoint_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CheckpointBoundRevocationCorpusSnapshot,
    policy: CredentialRevocationCheckpointPolicySnapshot,
    log: CredentialRevocationCheckpointLogSnapshot,
) -> StoredCredentialRevocationCheckpointEvidence:
    """Load and reverify the corpus, policy, log, and checkpoint population."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored checkpoint-bound corpus differs from expected"
        )
    policy_artifact = store.get(
        policy.policy_id,
        expected_hash=policy.artifact_hash,
    )
    if policy_artifact.payload != policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored checkpoint policy differs from expected"
        )
    log_artifact = store.get(
        log.log_id,
        expected_hash=log.artifact_hash,
    )
    if log_artifact.payload != log.canonical_payload:
        raise ArtifactIntegrityError(
            "stored checkpoint log differs from expected"
        )
    checkpoints = tuple(
        _load_checkpoint(store, reference)
        for reference in log.checkpoint_refs
    )
    return StoredCredentialRevocationCheckpointEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        checkpoint_policy_ref=store.reference(policy.policy_id),
        checkpoint_log_ref=store.reference(log.log_id),
        checkpoint_refs=tuple(item.reference() for item in checkpoints),
        checkpoints=checkpoints,
    )


def validate_credential_revocation_checkpoints(
    *,
    plan: ExperimentPlan,
    corpus: CheckpointBoundRevocationCorpusSnapshot,
    policy: CredentialRevocationCheckpointPolicySnapshot,
    log: CredentialRevocationCheckpointLogSnapshot,
    ledger: CredentialRevocationLedgerSnapshot,
    checkpoints: tuple[CredentialRevocationLedgerCheckpointSnapshot, ...],
    verified_at: str,
) -> CredentialRevocationCheckpointVerificationReport:
    """Verify checkpoint order, extension, chronology, and exact current head."""

    verified = _parse_timestamp(verified_at, "verified_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise CredentialRevocationCheckpointError(
            "only a frozen experiment plan may pass checkpoint verification"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != (
        corpus.content_ids
    ):
        raise CredentialRevocationCheckpointError(
            "experiment plan differs from checkpoint-bound corpus"
        )
    if corpus.checkpoint_policy_ref != policy.reference():
        raise CredentialRevocationCheckpointError(
            "checkpoint policy reference differs from corpus"
        )
    if corpus.checkpoint_log_ref != log.reference():
        raise CredentialRevocationCheckpointError(
            "checkpoint log reference differs from corpus"
        )
    if corpus.checkpoint_head_ref != log.head_checkpoint_ref:
        raise CredentialRevocationCheckpointError(
            "checkpoint head reference differs from corpus"
        )
    if policy.status is not (
        CredentialRevocationCheckpointPolicyLifecycle.ACCEPTED
    ):
        raise CredentialRevocationCheckpointError(
            "checkpoint policy must be accepted"
        )
    if log.status is not CredentialRevocationCheckpointLogLifecycle.FROZEN:
        raise CredentialRevocationCheckpointError(
            "checkpoint log must be frozen"
        )
    if log.checkpoint_policy_ref != policy.reference():
        raise CredentialRevocationCheckpointError(
            "checkpoint log policy reference differs"
        )
    if tuple(item.reference() for item in checkpoints) != log.checkpoint_refs:
        raise CredentialRevocationCheckpointError(
            "checkpoint population differs from log"
        )

    previous: CredentialRevocationLedgerCheckpointSnapshot | None = None
    for expected_sequence, checkpoint in enumerate(checkpoints):
        if checkpoint.sequence_number != expected_sequence:
            raise CredentialRevocationCheckpointError(
                "checkpoint sequence numbers must be contiguous from zero"
            )
        if previous is None:
            if checkpoint.predecessor_checkpoint_ref is not None:
                raise CredentialRevocationCheckpointError(
                    "genesis checkpoint may not name a predecessor"
                )
        else:
            if checkpoint.predecessor_checkpoint_ref != previous.reference():
                raise CredentialRevocationCheckpointError(
                    "checkpoint must reference its immediate predecessor"
                )
            if checkpoint.event_refs[: previous.event_count] != (
                previous.event_refs
            ):
                raise CredentialRevocationCheckpointError(
                    "checkpoint event population must preserve prior order "
                    "without omission"
                )
            if checkpoint.event_count < previous.event_count:
                raise CredentialRevocationCheckpointError(
                    "checkpoint event count may not roll back"
                )
            if _parse_timestamp(
                checkpoint.published_at,
                "published_at",
            ) <= _parse_timestamp(previous.published_at, "published_at"):
                raise CredentialRevocationCheckpointError(
                    "checkpoint publication time must increase"
                )
        if _parse_timestamp(checkpoint.published_at, "published_at") > verified:
            raise CredentialRevocationCheckpointError(
                "checkpoint may not be verified before publication"
            )
        previous = checkpoint

    head = checkpoints[-1]
    if head.reference() != log.head_checkpoint_ref:
        raise CredentialRevocationCheckpointError(
            "checkpoint log head differs from final checkpoint"
        )
    if head.revocation_corpus_ref != corpus.predecessor_corpus_ref:
        raise CredentialRevocationCheckpointError(
            "checkpoint head corpus reference differs from predecessor corpus"
        )
    if head.revocation_ledger_ref != ledger.reference():
        raise CredentialRevocationCheckpointError(
            "checkpoint head ledger reference differs"
        )
    if head.event_refs != ledger.event_refs:
        raise CredentialRevocationCheckpointError(
            "checkpoint head event order differs from ledger"
        )
    if head.event_count != len(ledger.event_refs):
        raise CredentialRevocationCheckpointError(
            "checkpoint head event count differs from ledger"
        )
    if _parse_timestamp(log.created_at, "created_at") < _parse_timestamp(
        head.published_at,
        "published_at",
    ):
        raise CredentialRevocationCheckpointError(
            "checkpoint log may not predate its head publication"
        )
    return CredentialRevocationCheckpointVerificationReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        checkpoint_corpus_ref=corpus.reference(),
        checkpoint_policy_ref=policy.reference(),
        checkpoint_log_ref=log.reference(),
        head_checkpoint_ref=head.reference(),
        checkpoint_count=len(checkpoints),
        head_sequence_number=head.sequence_number,
        head_event_count=head.event_count,
        head_event_population_hash=head.event_population_hash,
        verified_at=verified_at,
    )


def persist_checkpoint_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CheckpointBoundRevocationCorpusSnapshot,
    predecessor_corpus: RevocationBoundCredentialCorpusSnapshot,
    policy: CredentialRevocationCheckpointPolicySnapshot,
    log: CredentialRevocationCheckpointLogSnapshot,
    ledger: CredentialRevocationLedgerSnapshot,
    checkpoints: tuple[CredentialRevocationLedgerCheckpointSnapshot, ...],
    verified_at: str,
) -> StoredCredentialRevocationCheckpointEvidence:
    """Persist policy, checkpoints, log, and publish the new corpus last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise CredentialRevocationCheckpointError(
            "predecessor revocation corpus reference differs"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise CredentialRevocationCheckpointError(
            "checkpoint corpus content population differs"
        )
    if predecessor_corpus.revocation_policy_ref != (
        corpus.corpus.revocation_policy_ref
    ):
        raise CredentialRevocationCheckpointError(
            "checkpoint corpus revocation policy differs from predecessor"
        )
    if predecessor_corpus.revocation_ledger_ref != (
        corpus.corpus.revocation_ledger_ref
    ):
        raise CredentialRevocationCheckpointError(
            "checkpoint corpus revocation ledger differs from predecessor"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored predecessor revocation corpus differs"
        )
    validate_credential_revocation_checkpoints(
        plan=plan,
        corpus=corpus,
        policy=policy,
        log=log,
        ledger=ledger,
        checkpoints=checkpoints,
        verified_at=verified_at,
    )
    if store.append(policy.artifact()).artifact_hash != policy.artifact_hash:
        raise ArtifactIntegrityError(
            "stored checkpoint policy reference differs"
        )
    for checkpoint in checkpoints:
        if store.append(checkpoint.artifact()) != checkpoint.reference():
            raise ArtifactIntegrityError(
                "stored checkpoint reference differs"
            )
    if store.append(log.artifact()).artifact_hash != log.artifact_hash:
        raise ArtifactIntegrityError(
            "stored checkpoint log reference differs"
        )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored checkpoint corpus reference differs"
        )
    return load_credential_revocation_checkpoint_evidence(
        store,
        corpus=corpus,
        policy=policy,
        log=log,
    )
