"""Checkpoint the exact checkpoint-conflict adjudicator credential revocation ledger head."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    load_adjudicator_credential_revocation_checkpoint_evidence as _load_checkpoint_evidence,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    persist_checkpoint_bound_adjudicator_revocation_corpus as _persist_checkpoint_corpus,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    validate_adjudicator_credential_revocation_checkpoints as _validate_checkpoints,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore, StoredArtifactRef
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes

__all__ = (
    "AdjudicatorCredentialRevocationCheckpointError",
    "AdjudicatorCredentialRevocationCheckpointLogSnapshot",
    "AdjudicatorCredentialRevocationCheckpointPolicySnapshot",
    "AdjudicatorCredentialRevocationCheckpointVerificationReport",
    "AdjudicatorCredentialRevocationLedgerCheckpointSnapshot",
    "CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot",
    "StoredAdjudicatorCredentialRevocationCheckpointEvidence",
    "load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence",
    "persist_checkpoint_bound_adjudicator_checkpoint_conflict_credential_revocation_corpus",
    "validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints",
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCredentialRevocationCheckpointError(
            f"{field_name} must be an object"
        )
    if any(not isinstance(key, str) for key in value):
        raise AdjudicatorCredentialRevocationCheckpointError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatorCredentialRevocationCheckpointError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AdjudicatorCredentialRevocationCheckpointError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise AdjudicatorCredentialRevocationCheckpointError(
            f"{field_name} must include a timezone"
        )
    return parsed


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
class CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot:
    """Compact successor binding the exact 1.6.0 ledger checkpoint head."""

    corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot
    corpus_id: str
    corpus_version: str
    status: str
    declared_content_ids: tuple[str, ...]
    predecessor_corpus_ref: VersionedArtifactRef
    checkpoint_policy_ref: VersionedArtifactRef
    checkpoint_log_ref: VersionedArtifactRef
    checkpoint_head_ref: StoredArtifactRef
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.corpus_id, "corpus_id"),
            (self.corpus_version, "corpus_version"),
            (self.status, "status"),
        ):
            _string(value, field_name)
        if self.status != "frozen":
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict revocation checkpoint corpus must be frozen"
            )
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict checkpoint predecessor differs from corpus"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict checkpoint content order differs from predecessor"
            )
        if len(self.declared_content_ids) != len(set(self.declared_content_ids)):
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict checkpoint content IDs must be unique"
            )
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict checkpoint corpus hash differs from payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    ) -> CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot:
        allowed = {
            "corpus_id",
            "corpus_version",
            "status",
            "content_ids",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_predecessor_corpus_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_policy_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_log_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_head_ref",
            "created_at",
        }
        unknown = sorted(set(document) - allowed)
        if unknown:
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict checkpoint corpus contains unsupported fields: "
                + ", ".join(unknown)
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise AdjudicatorCredentialRevocationCheckpointError(
                "checkpoint-conflict checkpoint content_ids must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            corpus=predecessor,
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(document.get("corpus_version"), "corpus_version"),
            status=_string(document.get("status"), "status"),
            declared_content_ids=tuple(
                _string(value, "content_ids") for value in content_ids
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_predecessor_corpus_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_predecessor_corpus_ref",
            ),
            checkpoint_policy_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_policy_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_policy_ref",
            ),
            checkpoint_log_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_log_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_log_ref",
            ),
            checkpoint_head_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get(
                        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_head_ref"
                    ),
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_head_ref",
                )
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @property
    def content_ids(self) -> tuple[str, ...]:
        return self.declared_content_ids

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.corpus_id,
            artifact_version=self.corpus_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.corpus_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


def load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
) -> StoredAdjudicatorCredentialRevocationCheckpointEvidence:
    """Load the generic checkpoint graph through the context-specific manifest."""

    return _load_checkpoint_evidence(
        store,
        corpus=cast(Any, corpus),
        policy=policy,
        log=log,
    )


def validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
    *,
    plan: ExperimentPlan,
    corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    checkpoints: tuple[AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...],
    verified_at: str,
) -> AdjudicatorCredentialRevocationCheckpointVerificationReport:
    """Verify continuity and exact coverage of the current 1.6.0 ledger head."""

    return _validate_checkpoints(
        plan=plan,
        corpus=cast(Any, corpus),
        policy=policy,
        log=log,
        ledger=ledger,
        checkpoints=checkpoints,
        verified_at=verified_at,
    )


def persist_checkpoint_bound_adjudicator_checkpoint_conflict_credential_revocation_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    predecessor_corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    checkpoints: tuple[AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...],
    verified_at: str,
) -> StoredAdjudicatorCredentialRevocationCheckpointEvidence:
    """Append policy, checkpoint, log, then publish the 1.7.0 manifest last."""

    return _persist_checkpoint_corpus(
        store,
        plan=plan,
        corpus=cast(Any, corpus),
        predecessor_corpus=cast(Any, predecessor_corpus),
        policy=policy,
        log=log,
        ledger=ledger,
        checkpoints=checkpoints,
        verified_at=verified_at,
    )
