"""Credential the adjudicator resolving the current checkpoint-witness conflict."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self, cast

import ctrt.adjudicator_credential_attestation as base
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.current_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot,
)
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.reviewer_credential_attestation import CredentialIssuerRegistrySnapshot
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)

CredentialAttestationSnapshot = base.AdjudicatorCredentialAttestationSnapshot
CredentialDecisionReport = base.AdjudicatorCredentialDecisionReport
CredentialEvidenceEntry = base.AdjudicatorCredentialEvidenceEntry
CredentialError = base.AdjudicatorCredentialError
CredentialPolicySnapshot = base.AdjudicatorCredentialPolicySnapshot
StoredCredentialEvidence = base.StoredAdjudicatorCredentialEvidence

CREDENTIAL_PREFIX = "current_checkpoint_witness_conflict_adjudicator_credential"

__all__ = (
    "CredentialAttestationSnapshot",
    "CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot",
    "CredentialDecisionReport",
    "CredentialError",
    "CredentialPolicySnapshot",
    "StoredCredentialEvidence",
    "load_current_checkpoint_witness_conflict_credential_evidence",
    "persist_current_checkpoint_witness_conflict_credential_corpus",
    "validate_current_checkpoint_witness_conflict_credentials",
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CredentialError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CredentialError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CredentialError(f"{field_name} must be a non-empty string")
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CredentialError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CredentialError(f"{field_name} must include a timezone")
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


def _allowed_fields() -> set[str]:
    return {
        "corpus_id",
        "corpus_version",
        "status",
        "content_ids",
        f"{CREDENTIAL_PREFIX}_predecessor_corpus_ref",
        f"{CREDENTIAL_PREFIX}_issuer_registry_ref",
        f"{CREDENTIAL_PREFIX}_policy_ref",
        f"{CREDENTIAL_PREFIX}s",
        "created_at",
    }


@dataclass(frozen=True, slots=True)
class CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot:
    """Exact `1.19.0` adjudication plus issuer-bound credential evidence."""

    corpus: AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot
    corpus_id: str
    corpus_version: str
    status: str
    declared_content_ids: tuple[str, ...]
    predecessor_corpus_ref: VersionedArtifactRef
    issuer_registry_ref: VersionedArtifactRef
    credential_policy_ref: VersionedArtifactRef
    credential_entries: tuple[CredentialEvidenceEntry, ...]
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
            raise CredentialError("credential-bound corpus must be frozen")
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise CredentialError(
                "credential predecessor differs from exact 1.19.0 corpus"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise CredentialError("credential content order differs from 1.19.0")
        if len(self.declared_content_ids) != len(set(self.declared_content_ids)):
            raise CredentialError("credential-bound content IDs must be unique")
        ids = tuple(item.adjudicator_id for item in self.credential_entries)
        if not ids:
            raise CredentialError("credential-bound corpus requires credentials")
        if len(ids) != len(set(ids)):
            raise CredentialError("credential entries must use unique adjudicator IDs")
        if _parse_timestamp(self.created_at, "created_at") < _parse_timestamp(
            self.corpus.corpus.created_at,
            "adjudication_predecessor.created_at",
        ):
            raise CredentialError("credential successor may not precede 1.19.0")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise CredentialError("credential-bound corpus hash differs from payload")

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot,
    ) -> Self:
        unknown = sorted(set(document) - _allowed_fields())
        if unknown:
            raise CredentialError(
                "credential-bound corpus contains unsupported fields: "
                + ", ".join(unknown)
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise CredentialError("content_ids must be an array")
        entries = document.get(f"{CREDENTIAL_PREFIX}s")
        if not isinstance(entries, list):
            raise CredentialError("credential entries must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            corpus=predecessor,
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(document.get("corpus_version"), "corpus_version"),
            status=_string(document.get("status"), "status"),
            declared_content_ids=tuple(
                _string(value, "content_id") for value in content_ids
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get(f"{CREDENTIAL_PREFIX}_predecessor_corpus_ref"),
                f"{CREDENTIAL_PREFIX}_predecessor_corpus_ref",
            ),
            issuer_registry_ref=_versioned_ref(
                document.get(f"{CREDENTIAL_PREFIX}_issuer_registry_ref"),
                f"{CREDENTIAL_PREFIX}_issuer_registry_ref",
            ),
            credential_policy_ref=_versioned_ref(
                document.get(f"{CREDENTIAL_PREFIX}_policy_ref"),
                f"{CREDENTIAL_PREFIX}_policy_ref",
            ),
            credential_entries=tuple(
                CredentialEvidenceEntry.from_document(
                    _mapping(item, "credential entry")
                )
                for item in entries
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


def load_current_checkpoint_witness_conflict_credential_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: CredentialPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredCredentialEvidence:
    """Load and reverify the complete `1.20.0` credential graph."""

    return base.load_adjudicator_credential_evidence(
        store,
        corpus=cast(Any, corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        adjudication=adjudication,
    )


def validate_current_checkpoint_witness_conflict_credentials(
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: CredentialPolicySnapshot,
    attestations: tuple[CredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> CredentialDecisionReport:
    """Validate exact authorization without altering disagreement or adjudication."""

    return base.validate_adjudicator_credential_attestations(
        plan=plan,
        corpus=cast(Any, corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        attestations=attestations,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )


def persist_current_checkpoint_witness_conflict_credential_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
    predecessor_corpus: AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: CredentialPolicySnapshot,
    attestations: tuple[CredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredCredentialEvidence:
    """Publish issuer, policy, credential, then the `1.20.0` manifest last."""

    return base.persist_credential_bound_adjudication_corpus(
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
