"""Adjudicate conflicts over the current revocation-checkpoint witnesses."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import Any, Self, cast

import ctrt.adjudicator_checkpoint_witness_conflict_adjudication as base
import ctrt.current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints as cp
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)

_witness = import_module(
    "ctrt.current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_witness"
)


def _module_attribute(name: str) -> Any:
    return vars(_witness)[name]


AdjudicatorCheckpointWitnessDecisionReport = _module_attribute(
    "AdjudicatorCheckpointWitnessDecisionReport"
)
load_witness_evidence = _module_attribute(
    "load_current_conflict_adjudicator_revocation_checkpoint_witness_evidence"
)
validate_witnesses = _module_attribute(
    "validate_current_conflict_adjudicator_revocation_checkpoint_witnesses"
)

CheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
CheckpointCorpus = (
    cp.CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
)
WitnessCorpus = Any
ConflictAdjudicationDecisionReport = (
    base.AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport
)
ConflictAdjudicationError = (
    base.AdjudicatorCheckpointWitnessConflictAdjudicationError
)
StoredConflictAdjudicationEvidence = (
    base.StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence
)

_PREFIX = (
    "current_checkpoint_witness_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness"
)

__all__ = (
    "AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot",
    "ConflictAdjudicationDecisionReport",
    "ConflictAdjudicationError",
    "ConflictingCurrentRevocationCheckpointWitnessCorpusSnapshot",
    "StoredConflictAdjudicationEvidence",
    "load_current_revocation_checkpoint_conflict_adjudication_evidence",
    "persist_current_revocation_checkpoint_adjudication_bound_corpus",
    "validate_current_revocation_checkpoint_conflict_adjudication",
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConflictAdjudicationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ConflictAdjudicationError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConflictAdjudicationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConflictAdjudicationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ConflictAdjudicationError(
            f"{field_name} must include a timezone"
        )
    return parsed


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


def _allowed_fields() -> set[str]:
    return {
        "corpus_id",
        "corpus_version",
        "status",
        "content_ids",
        f"{_PREFIX}_predecessor_corpus_ref",
        f"{_PREFIX}_registry_ref",
        f"{_PREFIX}_policy_ref",
        f"{_PREFIX}_attestation_refs",
        f"{_PREFIX}_adjudication_predecessor_corpus_ref",
        f"{_PREFIX}_conflict_adjudicator_registry_ref",
        f"{_PREFIX}_conflict_adjudication_policy_ref",
        f"{_PREFIX}_conflict_adjudication_ref",
        "created_at",
    }


@dataclass(frozen=True, slots=True)
class ConflictingCurrentRevocationCheckpointWitnessCorpusSnapshot:
    """The exact conflicting witness population over the 1.22.0 head."""

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
            raise ConflictAdjudicationError(
                "current revocation-checkpoint adjudication corpus must be frozen"
            )
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise ConflictAdjudicationError(
                "current revocation-checkpoint predecessor differs from 1.22.0"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise ConflictAdjudicationError(
                "current revocation-checkpoint content order differs from 1.22.0"
            )
        if len(self.declared_content_ids) != len(set(self.declared_content_ids)):
            raise ConflictAdjudicationError(
                "current revocation-checkpoint content IDs must be unique"
            )
        if not self.witness_attestation_refs:
            raise ConflictAdjudicationError(
                "current revocation-checkpoint adjudication requires attestations"
            )
        if len(self.witness_attestation_refs) != len(
            set(self.witness_attestation_refs)
        ):
            raise ConflictAdjudicationError(
                "current revocation-checkpoint attestation refs must be unique"
            )
        if _parse_timestamp(self.created_at, "created_at") < _parse_timestamp(
            self.corpus.created_at,
            "checkpoint_predecessor.created_at",
        ):
            raise ConflictAdjudicationError(
                "current revocation-checkpoint adjudication may not precede 1.22.0"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ConflictAdjudicationError(
                "current revocation-checkpoint corpus hash differs from payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: CheckpointCorpus,
    ) -> Self:
        unknown = sorted(set(document) - _allowed_fields())
        if unknown:
            raise ConflictAdjudicationError(
                "current revocation-checkpoint adjudication corpus contains "
                "unsupported fields: " + ", ".join(unknown)
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise ConflictAdjudicationError("content_ids must be an array")
        refs = document.get(f"{_PREFIX}_attestation_refs")
        if not isinstance(refs, list):
            raise ConflictAdjudicationError(
                "current revocation-checkpoint attestation refs must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            corpus=predecessor,
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(
                document.get("corpus_version"),
                "corpus_version",
            ),
            status=_string(document.get("status"), "status"),
            declared_content_ids=tuple(
                _string(value, "content_id") for value in content_ids
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get(f"{_PREFIX}_predecessor_corpus_ref"),
                f"{_PREFIX}_predecessor_corpus_ref",
            ),
            witness_registry_ref=_versioned_ref(
                document.get(f"{_PREFIX}_registry_ref"),
                f"{_PREFIX}_registry_ref",
            ),
            witness_policy_ref=_versioned_ref(
                document.get(f"{_PREFIX}_policy_ref"),
                f"{_PREFIX}_policy_ref",
            ),
            witness_attestation_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(
                        item,
                        "current revocation-checkpoint attestation ref",
                    )
                )
                for item in refs
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


@dataclass(frozen=True, slots=True)
class AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot:
    """The conflicting population plus exact adjudication authority."""

    corpus: ConflictingCurrentRevocationCheckpointWitnessCorpusSnapshot
    witness_predecessor: WitnessCorpus
    predecessor_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    adjudication_policy_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef

    def __post_init__(self) -> None:
        if self.predecessor_corpus_ref != self.witness_predecessor.reference():
            raise ConflictAdjudicationError(
                "adjudication predecessor differs from exact 1.23.0 corpus"
            )
        if self.content_ids != self.witness_predecessor.content_ids:
            raise ConflictAdjudicationError(
                "adjudication content order differs from 1.23.0"
            )
        if (
            self.corpus.predecessor_corpus_ref
            != self.witness_predecessor.predecessor_corpus_ref
        ):
            raise ConflictAdjudicationError(
                "adjudication changed the 1.22.0 checkpoint predecessor"
            )
        if (
            self.corpus.witness_registry_ref
            != self.witness_predecessor.witness_registry_ref
        ):
            raise ConflictAdjudicationError(
                "adjudication changed the current witness registry"
            )
        if (
            self.corpus.witness_policy_ref
            != self.witness_predecessor.witness_policy_ref
        ):
            raise ConflictAdjudicationError(
                "adjudication changed the current witness policy"
            )
        if _parse_timestamp(
            self.corpus.created_at,
            "created_at",
        ) < _parse_timestamp(
            self.witness_predecessor.created_at,
            "witness_predecessor.created_at",
        ):
            raise ConflictAdjudicationError(
                "adjudication successor may not precede 1.23.0"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        checkpoint_predecessor: CheckpointCorpus,
        witness_predecessor: WitnessCorpus,
    ) -> Self:
        witness_corpus = (
            ConflictingCurrentRevocationCheckpointWitnessCorpusSnapshot.from_document(
                document,
                predecessor=checkpoint_predecessor,
            )
        )
        return cls(
            corpus=witness_corpus,
            witness_predecessor=witness_predecessor,
            predecessor_corpus_ref=_versioned_ref(
                document.get(
                    f"{_PREFIX}_adjudication_predecessor_corpus_ref"
                ),
                f"{_PREFIX}_adjudication_predecessor_corpus_ref",
            ),
            adjudicator_registry_ref=_versioned_ref(
                document.get(
                    f"{_PREFIX}_conflict_adjudicator_registry_ref"
                ),
                f"{_PREFIX}_conflict_adjudicator_registry_ref",
            ),
            adjudication_policy_ref=_versioned_ref(
                document.get(
                    f"{_PREFIX}_conflict_adjudication_policy_ref"
                ),
                f"{_PREFIX}_conflict_adjudication_policy_ref",
            ),
            adjudication_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get(f"{_PREFIX}_conflict_adjudication_ref"),
                    f"{_PREFIX}_conflict_adjudication_ref",
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


def load_current_revocation_checkpoint_conflict_adjudication_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredConflictAdjudicationEvidence:
    """Load and reverify the complete 1.24.0 adjudication graph."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored current revocation-checkpoint adjudication corpus differs"
        )
    registry_artifact = store.get(
        adjudicator_registry.registry_id,
        expected_hash=adjudicator_registry.artifact_hash,
    )
    if registry_artifact.payload != adjudicator_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored current revocation-checkpoint adjudicator registry differs"
        )
    policy_artifact = store.get(
        adjudication_policy.policy_id,
        expected_hash=adjudication_policy.artifact_hash,
    )
    if policy_artifact.payload != adjudication_policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored current revocation-checkpoint adjudication policy differs"
        )
    stored_adjudication = WitnessConflictAdjudicationSnapshot.from_artifact(
        store.get(
            adjudication.artifact_id,
            expected_hash=adjudication.artifact_hash,
        )
    )
    if stored_adjudication.reference() != corpus.adjudication_ref:
        raise ArtifactIntegrityError(
            "stored current revocation-checkpoint adjudication differs from corpus"
        )
    witness_evidence = load_witness_evidence(
        store,
        corpus=cast(Any, corpus.corpus),
        registry=witness_registry,
        policy=witness_policy,
    )
    return StoredConflictAdjudicationEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        adjudicator_registry_ref=store.reference(adjudicator_registry.registry_id),
        adjudication_policy_ref=store.reference(adjudication_policy.policy_id),
        adjudication_ref=stored_adjudication.reference(),
        witness_evidence=witness_evidence,
    )


def validate_current_revocation_checkpoint_conflict_adjudication(
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    witness_decision: Any,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> ConflictAdjudicationDecisionReport:
    """Validate exact resolution while preserving the witness abstention."""

    return base.validate_adjudicator_checkpoint_witness_conflict_adjudication(
        plan=plan,
        corpus=cast(Any, corpus),
        witness_registry=witness_registry,
        witness_policy=witness_policy,
        adjudicator_registry=adjudicator_registry,
        adjudication_policy=adjudication_policy,
        witness_decision=witness_decision,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )


def persist_current_revocation_checkpoint_adjudication_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
    witness_predecessor: WitnessCorpus,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: CheckpointSnapshot,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredConflictAdjudicationEvidence:
    """Append dependencies, then publish the 1.24.0 manifest last."""

    if witness_predecessor.reference() != corpus.predecessor_corpus_ref:
        raise ConflictAdjudicationError(
            "current witness predecessor corpus reference differs"
        )
    if witness_predecessor.content_ids != corpus.content_ids:
        raise ConflictAdjudicationError(
            "current adjudication corpus content population differs"
        )
    predecessor = store.get(
        witness_predecessor.reference().artifact_id,
        expected_hash=witness_predecessor.reference().artifact_hash,
    )
    if predecessor.payload != witness_predecessor.artifact().payload:
        raise ArtifactIntegrityError("stored 1.23.0 witness predecessor differs")
    witness_decision = validate_witnesses(
        plan=plan,
        corpus=cast(Any, corpus.corpus),
        registry=witness_registry,
        policy=witness_policy,
        head_checkpoint=head_checkpoint,
        attestations=witness_attestations,
        evaluated_at=evaluated_at,
    )
    validate_current_revocation_checkpoint_conflict_adjudication(
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
                "stored current revocation-checkpoint conflict graph differs"
            )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored current revocation-checkpoint adjudication corpus differs"
        )
    return load_current_revocation_checkpoint_conflict_adjudication_evidence(
        store,
        corpus=corpus,
        witness_registry=witness_registry,
        witness_policy=witness_policy,
        adjudicator_registry=adjudicator_registry,
        adjudication_policy=adjudication_policy,
        adjudication=adjudication,
    )
