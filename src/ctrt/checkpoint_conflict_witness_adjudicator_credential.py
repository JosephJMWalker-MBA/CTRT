"""Credential the authority resolving checkpoint-conflict revocation witness conflicts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, TypeAlias, cast

from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    AdjudicatorCheckpointConflictCredentialError,
    StoredAdjudicatorCheckpointConflictCredentialEvidence,
)
from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    load_adjudicator_checkpoint_conflict_credential_evidence as _load_evidence,
)
from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    persist_credential_bound_adjudicator_checkpoint_conflict_corpus as _persist_corpus,
)
from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    validate_adjudicator_checkpoint_conflict_credentials as _validate_credentials,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialDecisionReport,
    AdjudicatorCredentialEvidenceEntry,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    ConflictAdjudicationError,
)
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.reviewer_credential_attestation import CredentialIssuerRegistrySnapshot
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)

CheckpointConflictWitnessAdjudicatorCredentialError = (
    AdjudicatorCheckpointConflictCredentialError
)
CredentialDecisionReport: TypeAlias = AdjudicatorCredentialDecisionReport
StoredCredentialEvidence: TypeAlias = (
    StoredAdjudicatorCheckpointConflictCredentialEvidence
)

__all__ = (
    "CheckpointConflictWitnessAdjudicatorCredentialError",
    "CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot",
    "CredentialDecisionReport",
    "StoredCredentialEvidence",
    "load_checkpoint_conflict_witness_adjudicator_credential_evidence",
    "persist_checkpoint_conflict_witness_adjudicator_credential_corpus",
    "validate_checkpoint_conflict_witness_adjudicator_credentials",
)

_PREFIX = "checkpoint_conflict_revocation_witness_conflict_adjudicator_credential"
_CREDENTIAL_FIELDS = {
    f"{_PREFIX}_predecessor_corpus_ref",
    f"{_PREFIX}_issuer_registry_ref",
    f"{_PREFIX}_policy_ref",
    f"{_PREFIX}s",
}


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CheckpointConflictWitnessAdjudicatorCredentialError(
            f"{field_name} must be an object"
        )
    if any(not isinstance(key, str) for key in value):
        raise CheckpointConflictWitnessAdjudicatorCredentialError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckpointConflictWitnessAdjudicatorCredentialError(
            f"{field_name} must be a non-empty string"
        )
    return value


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


@dataclass(frozen=True, slots=True)
class CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot:
    """Compact 1.10.0 successor binding credentials to the 1.9.0 authority."""

    corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    issuer_registry_ref: VersionedArtifactRef
    credential_policy_ref: VersionedArtifactRef
    credential_entries: tuple[AdjudicatorCredentialEvidenceEntry, ...]

    def __post_init__(self) -> None:
        ids = tuple(item.adjudicator_id for item in self.credential_entries)
        if not ids:
            raise CheckpointConflictWitnessAdjudicatorCredentialError(
                "credential-bound witness-conflict corpus requires credentials"
            )
        if len(ids) != len(set(ids)):
            raise CheckpointConflictWitnessAdjudicatorCredentialError(
                "witness-conflict credential entries must use unique IDs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        checkpoint_predecessor: Any,
        witness_predecessor: Any,
        adjudication_predecessor: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    ) -> CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot:
        predecessor_document = {
            key: value
            for key, value in document.items()
            if key not in _CREDENTIAL_FIELDS
        }
        try:
            parsed = CheckpointConflictWitnessAdjudicationCorpusSnapshot.from_document(
                predecessor_document,
                checkpoint_predecessor=checkpoint_predecessor,
                witness_predecessor=witness_predecessor,
            )
        except ConflictAdjudicationError as exc:
            raise CheckpointConflictWitnessAdjudicatorCredentialError(
                str(exc)
            ) from exc
        payload = canonical_json_bytes(document)
        credential_view = replace(
            parsed,
            corpus=replace(
                parsed.corpus,
                canonical_payload=payload,
                artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
            ),
        )

        predecessor_ref = _versioned_ref(
            document.get(f"{_PREFIX}_predecessor_corpus_ref"),
            f"{_PREFIX}_predecessor_corpus_ref",
        )
        if predecessor_ref != adjudication_predecessor.reference():
            raise CheckpointConflictWitnessAdjudicatorCredentialError(
                "credential predecessor differs from exact 1.9.0 corpus"
            )
        preserved_authority = (
            parsed.content_ids,
            parsed.predecessor_corpus_ref,
            parsed.adjudicator_registry_ref,
            parsed.adjudication_policy_ref,
            parsed.adjudication_ref,
            parsed.corpus.predecessor_corpus_ref,
            parsed.corpus.witness_registry_ref,
            parsed.corpus.witness_policy_ref,
            parsed.corpus.witness_attestation_refs,
        )
        expected_authority = (
            adjudication_predecessor.content_ids,
            adjudication_predecessor.predecessor_corpus_ref,
            adjudication_predecessor.adjudicator_registry_ref,
            adjudication_predecessor.adjudication_policy_ref,
            adjudication_predecessor.adjudication_ref,
            adjudication_predecessor.corpus.predecessor_corpus_ref,
            adjudication_predecessor.corpus.witness_registry_ref,
            adjudication_predecessor.corpus.witness_policy_ref,
            adjudication_predecessor.corpus.witness_attestation_refs,
        )
        if preserved_authority != expected_authority:
            raise CheckpointConflictWitnessAdjudicatorCredentialError(
                "credential corpus must preserve the exact 1.9.0 authority graph"
            )
        values = document.get(f"{_PREFIX}s")
        if not isinstance(values, list):
            raise CheckpointConflictWitnessAdjudicatorCredentialError(
                f"{_PREFIX}s must be an array"
            )
        entries = tuple(
            AdjudicatorCredentialEvidenceEntry.from_document(
                _mapping(value, f"{_PREFIX}s")
            )
            for value in values
        )
        return cls(
            corpus=credential_view,
            predecessor_corpus_ref=predecessor_ref,
            issuer_registry_ref=_versioned_ref(
                document.get(f"{_PREFIX}_issuer_registry_ref"),
                f"{_PREFIX}_issuer_registry_ref",
            ),
            credential_policy_ref=_versioned_ref(
                document.get(f"{_PREFIX}_policy_ref"),
                f"{_PREFIX}_policy_ref",
            ),
            credential_entries=entries,
        )

    @property
    def content_ids(self) -> tuple[str, ...]:
        return self.corpus.content_ids

    def reference(self) -> VersionedArtifactRef:
        return self.corpus.reference()

    def artifact(self) -> CanonicalArtifact:
        return self.corpus.artifact()


def load_checkpoint_conflict_witness_adjudicator_credential_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredCredentialEvidence:
    """Load and reverify the complete 1.10.0 credential graph."""

    return _load_evidence(
        store,
        corpus=cast(Any, corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        adjudication=adjudication,
    )


def validate_checkpoint_conflict_witness_adjudicator_credentials(
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> CredentialDecisionReport:
    """Evaluate exact credentials without rewriting witness or adjudication evidence."""

    return _validate_credentials(
        plan=plan,
        corpus=cast(Any, corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        attestations=attestations,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )


def persist_checkpoint_conflict_witness_adjudicator_credential_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
    predecessor_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredCredentialEvidence:
    """Publish issuer, policy, attestations, then the 1.10.0 manifest last."""

    return _persist_corpus(
        store,
        plan=plan,
        corpus=cast(Any, corpus),
        predecessor_corpus=cast(Any, predecessor_corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        attestations=attestations,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )
