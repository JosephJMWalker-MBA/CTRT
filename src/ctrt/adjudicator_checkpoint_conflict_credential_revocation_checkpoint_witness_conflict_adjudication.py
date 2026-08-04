"""Authorized adjudication of checkpoint-conflict revocation witness observations."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestation import (
    WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
)
from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
)
from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport,
    AdjudicatorCheckpointWitnessConflictAdjudicationError,
    StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence,
)
from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    load_adjudicator_checkpoint_witness_conflict_adjudication_evidence as _load_evidence,
)
from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    persist_adjudication_bound_adjudicator_checkpoint_witness_corpus as _persist_corpus,
)
from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    validate_adjudicator_checkpoint_witness_conflict_adjudication as _validate_adjudication,
)
from ctrt.artifact_store import FileSystemArtifactStore, StoredArtifactRef
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

__all__ = (
    "AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot",
    "AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport",
    "AdjudicatorCheckpointWitnessConflictAdjudicationError",
    "StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence",
    "load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication_evidence",
    "persist_adjudication_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_corpus",
    "validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication",
)

_WITNESS_FIELDS = {
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
_PREFIX = (
    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness_conflict_adjudication"
)
_ADJUDICATION_FIELDS = {
    f"{_PREFIX}_predecessor_corpus_ref",
    f"{_PREFIX}_adjudicator_registry_ref",
    f"{_PREFIX}_policy_ref",
    f"{_PREFIX}_ref",
}


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
            document.get("artifact_version"),
            f"{field_name}.artifact_version",
        ),
        artifact_hash=_string(
            document.get("artifact_hash"),
            f"{field_name}.artifact_hash",
        ),
    )


@dataclass(frozen=True, slots=True)
class AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot:
    """Compact 1.9.0 successor preserving the exact 1.8.0 witness authority."""

    corpus: WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    adjudication_policy_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        checkpoint_predecessor: (
            CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot
        ),
        witness_predecessor: (
            WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot
        ),
    ) -> AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot:
        unknown = sorted(set(document) - _WITNESS_FIELDS - _ADJUDICATION_FIELDS)
        if unknown:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "checkpoint-conflict witness adjudication corpus contains unsupported "
                f"fields: {', '.join(unknown)}"
            )

        witness_document = {
            key: value for key, value in document.items() if key in _WITNESS_FIELDS
        }
        parsed_witness = (
            WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot.from_document(
                witness_document,
                predecessor=checkpoint_predecessor,
            )
        )
        payload = canonical_json_bytes(document)
        witness_view = replace(
            parsed_witness,
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

        predecessor_ref = _versioned_ref(
            document.get(f"{_PREFIX}_predecessor_corpus_ref"),
            f"{_PREFIX}_predecessor_corpus_ref",
        )
        if predecessor_ref != witness_predecessor.reference():
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "witness adjudication predecessor differs from exact 1.8.0 corpus"
            )
        if witness_view.content_ids != witness_predecessor.content_ids:
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "witness adjudication content order differs from predecessor"
            )
        if (
            witness_view.witness_registry_ref
            != witness_predecessor.witness_registry_ref
            or witness_view.witness_policy_ref
            != witness_predecessor.witness_policy_ref
        ):
            raise AdjudicatorCheckpointWitnessConflictAdjudicationError(
                "witness adjudication must preserve the 1.8.0 witness authority"
            )

        return cls(
            corpus=witness_view,
            predecessor_corpus_ref=predecessor_ref,
            adjudicator_registry_ref=_versioned_ref(
                document.get(f"{_PREFIX}_adjudicator_registry_ref"),
                f"{_PREFIX}_adjudicator_registry_ref",
            ),
            adjudication_policy_ref=_versioned_ref(
                document.get(f"{_PREFIX}_policy_ref"),
                f"{_PREFIX}_policy_ref",
            ),
            adjudication_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get(f"{_PREFIX}_ref"),
                    f"{_PREFIX}_ref",
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


def load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence:
    """Load and reverify the complete 1.9.0 adjudication graph."""

    return cast(
        StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence,
        _load_evidence(
            store,
            corpus=cast(Any, corpus),
            witness_registry=witness_registry,
            witness_policy=witness_policy,
            adjudicator_registry=adjudicator_registry,
            adjudication_policy=adjudication_policy,
            adjudication=adjudication,
        ),
    )


def validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication(
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport:
    """Validate resolution while preserving the original witness outcome."""

    return _validate_adjudication(
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


def persist_adjudication_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot,
    predecessor_corpus: WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
    witness_registry: CheckpointWitnessRegistrySnapshot,
    witness_policy: CheckpointWitnessPolicySnapshot,
    head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence:
    """Publish authority and adjudication, then the 1.9.0 manifest last."""

    return cast(
        StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence,
        _persist_corpus(
            store,
            plan=plan,
            corpus=cast(Any, corpus),
            predecessor_corpus=cast(Any, predecessor_corpus),
            witness_registry=witness_registry,
            witness_policy=witness_policy,
            head_checkpoint=head_checkpoint,
            witness_attestations=witness_attestations,
            adjudicator_registry=adjudicator_registry,
            adjudication_policy=adjudication_policy,
            adjudication=adjudication,
            evaluated_at=evaluated_at,
        ),
    )
