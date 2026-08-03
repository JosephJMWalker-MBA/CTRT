"""Bind named witness observations to the exact checkpoint-conflict revocation head."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
)
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
    "WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot",
    "load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence",
    "persist_witness_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_corpus",
    "validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations",
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
class WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot:
    """Compact successor binding named witnesses to the immutable 1.7.0 head."""

    corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot
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
                "checkpoint-conflict revocation checkpoint witness corpus must be frozen"
            )
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness predecessor differs from corpus"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness content order differs from predecessor"
            )
        if len(self.declared_content_ids) != len(set(self.declared_content_ids)):
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness content IDs must be unique"
            )
        if not self.witness_attestation_refs:
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness corpus requires attestations"
            )
        if len(self.witness_attestation_refs) != len(set(self.witness_attestation_refs)):
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness attestation refs must be unique"
            )
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness corpus hash differs from payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    ) -> WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot:
        allowed = {
            "corpus_id",
            "corpus_version",
            "status",
            "content_ids",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_predecessor_corpus_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_registry_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_policy_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_attestation_refs",
            "created_at",
        }
        unknown = sorted(set(document) - allowed)
        if unknown:
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness corpus contains unsupported fields: "
                + ", ".join(unknown)
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness content_ids must be an array"
            )
        attestation_refs = document.get(
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_attestation_refs"
        )
        if not isinstance(attestation_refs, list):
            raise AdjudicatorCheckpointWitnessError(
                "checkpoint-conflict witness attestation refs must be an array"
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
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_predecessor_corpus_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_predecessor_corpus_ref",
            ),
            witness_registry_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_registry_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_registry_ref",
            ),
            witness_policy_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_policy_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_policy_ref",
            ),
            witness_attestation_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(item, "checkpoint-conflict witness attestation ref")
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


def load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
) -> StoredAdjudicatorCheckpointWitnessEvidence:
    """Load the generic named-witness graph through the 1.8.0 manifest."""

    return _load_witness_evidence(
        store,
        corpus=cast(Any, corpus),
        registry=registry,
        policy=policy,
    )


def validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations(
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
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


def persist_witness_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
    predecessor_corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    registry: CheckpointWitnessRegistrySnapshot,
    policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    evaluated_at: str,
) -> StoredAdjudicatorCheckpointWitnessEvidence:
    """Append registry, policy, attestations, then publish 1.8.0 last."""

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
