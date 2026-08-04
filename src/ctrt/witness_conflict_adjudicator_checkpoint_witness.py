"""Bind named observations to the exact witness-conflict adjudicator checkpoint."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self, cast

from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    AdjudicatorCheckpointWitnessObservationSummary,
    StoredAdjudicatorCheckpointWitnessEvidence,
)
from ctrt.adjudicator_checkpoint_witness_attestation import (
    load_adjudicator_checkpoint_witness_evidence as _load_witness_evidence,
)
from ctrt.adjudicator_checkpoint_witness_attestation import (
    persist_witness_bound_adjudicator_checkpoint_corpus as _persist_witness_corpus,
)
from ctrt.adjudicator_checkpoint_witness_attestation import (
    validate_adjudicator_checkpoint_witness_attestations as _validate_witnesses,
)
from ctrt.artifact_store import FileSystemArtifactStore, StoredArtifactRef
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot as CheckpointSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints import (
    CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
    as CheckpointCorpus,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes

__all__ = (
    "AdjudicatorCheckpointWitnessDecisionReport",
    "AdjudicatorCheckpointWitnessError",
    "AdjudicatorCheckpointWitnessObservationSummary",
    "StoredAdjudicatorCheckpointWitnessEvidence",
    "WitnessBoundCheckpointCorpusSnapshot",
    "load_witness_evidence",
    "persist_witness_corpus",
    "validate_witness_attestations",
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCheckpointWitnessError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise AdjudicatorCheckpointWitnessError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatorCheckpointWitnessError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
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
class WitnessBoundCheckpointCorpusSnapshot:
    """Compact successor binding named witnesses to the immutable 1.12.0 head."""

    corpus: CheckpointCorpus
    corpus_id: str
    corpus_version: str
    status: str
    declared_content_ids: tuple[str, ...]
    predecessor_corpus_ref: VersionedArtifactRef
    witness_registry_ref: VersionedArtifactRef
    witness_policy_ref: VersionedArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
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
            raise AdjudicatorCheckpointWitnessError(
                "witness-conflict adjudicator checkpoint witness corpus must be frozen"
            )
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise AdjudicatorCheckpointWitnessError(
                "witness predecessor differs from the 1.12.0 corpus"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise AdjudicatorCheckpointWitnessError(
                "witness content order differs from predecessor"
            )
        if len(self.declared_content_ids) != len(set(self.declared_content_ids)):
            raise AdjudicatorCheckpointWitnessError(
                "witness content IDs must be unique"
            )
        if not self.witness_attestation_refs:
            raise AdjudicatorCheckpointWitnessError(
                "witness corpus requires attestations"
            )
        if len(self.witness_attestation_refs) != len(set(self.witness_attestation_refs)):
            raise AdjudicatorCheckpointWitnessError(
                "witness attestation refs must be unique"
            )
        if _parse_timestamp(self.created_at, "created_at") < _parse_timestamp(
            self.corpus.created_at,
            "predecessor.created_at",
        ):
            raise AdjudicatorCheckpointWitnessError(
                "witness successor may not precede its 1.12.0 predecessor"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCheckpointWitnessError(
                "witness corpus hash differs from payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: CheckpointCorpus,
    ) -> Self:
        prefix = (
            "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
            "credential_revocation_checkpoint_witness"
        )
        allowed = {
            "corpus_id",
            "corpus_version",
            "status",
            "content_ids",
            f"{prefix}_predecessor_corpus_ref",
            f"{prefix}_registry_ref",
            f"{prefix}_policy_ref",
            f"{prefix}_attestation_refs",
            "created_at",
        }
        unknown = sorted(set(document) - allowed)
        if unknown:
            raise AdjudicatorCheckpointWitnessError(
                "witness corpus contains unsupported fields: " + ", ".join(unknown)
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise AdjudicatorCheckpointWitnessError(
                "witness content_ids must be an array"
            )
        attestation_refs = document.get(f"{prefix}_attestation_refs")
        if not isinstance(attestation_refs, list):
            raise AdjudicatorCheckpointWitnessError(
                "witness attestation refs must be an array"
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
                document.get(f"{prefix}_predecessor_corpus_ref"),
                f"{prefix}_predecessor_corpus_ref",
            ),
            witness_registry_ref=_versioned_ref(
                document.get(f"{prefix}_registry_ref"),
                f"{prefix}_registry_ref",
            ),
            witness_policy_ref=_versioned_ref(
                document.get(f"{prefix}_policy_ref"),
                f"{prefix}_policy_ref",
            ),
            witness_attestation_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(item, "witness attestation ref")
                )
                for item in attestation_refs
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


def load_witness_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: WitnessBoundCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
) -> StoredAdjudicatorCheckpointWitnessEvidence:
    """Load the generic named-witness graph through the 1.13.0 manifest."""

    return _load_witness_evidence(
        store,
        corpus=cast(Any, corpus),
        registry=registry,
        policy=policy,
    )


def validate_witness_attestations(
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: CheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> AdjudicatorCheckpointWitnessDecisionReport:
    """Preserve every named head observation and abstain on any conflict."""

    return _validate_witnesses(
        plan=plan,
        corpus=cast(Any, corpus),
        registry=registry,
        policy=policy,
        head_checkpoint=head_checkpoint,
        attestations=attestations,
        evaluated_at=evaluated_at,
    )


def persist_witness_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundCheckpointCorpusSnapshot,
    predecessor_corpus: CheckpointCorpus,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: CheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> StoredAdjudicatorCheckpointWitnessEvidence:
    """Append registry, policy, attestations, then publish 1.13.0 last."""

    return _persist_witness_corpus(
        store,
        plan=plan,
        corpus=cast(Any, corpus),
        predecessor_corpus=cast(Any, predecessor_corpus),
        registry=registry,
        policy=policy,
        head_checkpoint=head_checkpoint,
        attestations=attestations,
        evaluated_at=evaluated_at,
    )
