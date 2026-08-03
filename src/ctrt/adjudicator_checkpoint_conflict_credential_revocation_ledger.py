"""Bind checkpoint-conflict adjudicator credentials to append-only revocation history."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    StoredAdjudicatorCredentialRevocationEvidence,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    load_adjudicator_credential_revocation_evidence as _load_revocation_evidence,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    persist_adjudicator_credential_revocation_bound_corpus as _persist_revocation_corpus,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    validate_adjudicator_credential_revocation_ledger as _validate_revocation_ledger,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.experiments import ExperimentPlan, VersionedArtifactRef
from ctrt.reviewer_credential_attestation import CredentialIssuerRegistrySnapshot
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCredentialRevocationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} keys must be strings"
        )
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _parse_timestamp(value: str, field_name: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise AdjudicatorCredentialRevocationError(
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
class RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot:
    """A compact successor manifest over the immutable credential-bound corpus."""

    corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot
    corpus_id: str
    corpus_version: str
    status: str
    declared_content_ids: tuple[str, ...]
    predecessor_corpus_ref: VersionedArtifactRef
    revocation_policy_ref: VersionedArtifactRef
    revocation_ledger_ref: VersionedArtifactRef
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
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation corpus must be frozen"
            )
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation predecessor differs from corpus"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation content order differs from predecessor"
            )
        if len(self.declared_content_ids) != len(set(self.declared_content_ids)):
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation content IDs must be unique"
            )
        _parse_timestamp(self.created_at, "created_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation corpus hash differs from payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    ) -> RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot:
        allowed = {
            "corpus_id",
            "corpus_version",
            "status",
            "content_ids",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_predecessor_corpus_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_policy_ref",
            "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_ledger_ref",
            "created_at",
        }
        unknown = sorted(set(document) - allowed)
        if unknown:
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation corpus contains unsupported fields: "
                + ", ".join(unknown)
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise AdjudicatorCredentialRevocationError(
                "checkpoint-conflict revocation content_ids must be an array"
            )
        declared_content_ids = tuple(
            _string(value, "content_ids") for value in content_ids
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
            declared_content_ids=declared_content_ids,
            predecessor_corpus_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_predecessor_corpus_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_predecessor_corpus_ref",
            ),
            revocation_policy_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_policy_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_policy_ref",
            ),
            revocation_ledger_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_ledger_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_ledger_ref",
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


def load_adjudicator_checkpoint_conflict_credential_revocation_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
) -> StoredAdjudicatorCredentialRevocationEvidence:
    """Load the generic revocation graph through the checkpoint-conflict manifest."""

    return _load_revocation_evidence(
        store,
        corpus=cast(Any, corpus),
        policy=policy,
        ledger=ledger,
    )


def validate_adjudicator_checkpoint_conflict_credential_revocation_ledger(
    *,
    plan: ExperimentPlan,
    corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
    evaluated_at: str,
) -> AdjudicatorCredentialRevocationDecisionReport:
    """Evaluate immutable status history without changing credential semantics."""

    return _validate_revocation_ledger(
        plan=plan,
        corpus=cast(Any, corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        revocation_policy=revocation_policy,
        ledger=ledger,
        attestations=attestations,
        adjudication=adjudication,
        events=events,
        evaluated_at=evaluated_at,
    )


def persist_adjudicator_checkpoint_conflict_credential_revocation_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    predecessor_corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
    evaluated_at: str,
) -> StoredAdjudicatorCredentialRevocationEvidence:
    """Append policy, events, ledger, then publish the compact manifest last."""

    return _persist_revocation_corpus(
        store,
        plan=plan,
        corpus=cast(Any, corpus),
        predecessor_corpus=cast(Any, predecessor_corpus),
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        revocation_policy=revocation_policy,
        ledger=ledger,
        attestations=attestations,
        adjudication=adjudication,
        events=events,
        evaluated_at=evaluated_at,
    )
