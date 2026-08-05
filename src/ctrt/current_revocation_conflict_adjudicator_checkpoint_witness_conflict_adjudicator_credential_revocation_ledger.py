"""Bind the exact `1.30.0` conflict-adjudicator credential to status history."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import Any, Self, cast

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

_credential = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential"
)
CredentialCorpus = vars(_credential)[
    "CredentialBoundCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessCorpusSnapshot"
]
CredentialAttestationSnapshot = vars(_credential)["CredentialAttestationSnapshot"]
CredentialPolicySnapshot = vars(_credential)["CredentialPolicySnapshot"]

_PREFIX = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation"
)
_LONG_CORPUS = (
    "RevocationBoundCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialCorpusSnapshot"
)
_LONG_LOAD = (
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_evidence"
)
_LONG_PERSIST = (
    "persist_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_bound_corpus"
)
_LONG_VALIDATE = (
    "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_ledger"
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must be an object"
        )
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
class RevocationCorpusSnapshot:
    """Compact `1.31.0` successor over the immutable `1.30.0` credential."""

    corpus: Any
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
                "current conflict-adjudicator credential revocation "
                "corpus must be frozen"
            )
        if self.predecessor_corpus_ref != self.corpus.reference():
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential predecessor differs "
                "from exact 1.30.0"
            )
        if self.declared_content_ids != self.corpus.content_ids:
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential content order differs"
            )
        if len(self.declared_content_ids) != len(
            set(self.declared_content_ids)
        ):
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential content IDs "
                "must be unique"
            )
        if _parse_timestamp(self.created_at, "created_at") < _parse_timestamp(
            self.corpus.created_at,
            "credential_predecessor.created_at",
        ):
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential successor may not "
                "precede 1.30.0"
            )
        expected = (
            f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        )
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential corpus hash differs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
        *,
        predecessor: Any,
    ) -> Self:
        allowed = {
            "corpus_id",
            "corpus_version",
            "status",
            "content_ids",
            f"{_PREFIX}_predecessor_corpus_ref",
            f"{_PREFIX}_policy_ref",
            f"{_PREFIX}_ledger_ref",
            "created_at",
        }
        unknown = sorted(set(document) - allowed)
        if unknown:
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential revocation corpus "
                f"contains unsupported fields: {', '.join(unknown)}"
            )
        content_ids = document.get("content_ids")
        if not isinstance(content_ids, list):
            raise AdjudicatorCredentialRevocationError(
                "current conflict-adjudicator credential content_ids "
                "must be an array"
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
                _string(value, "content_ids") for value in content_ids
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get(f"{_PREFIX}_predecessor_corpus_ref"),
                f"{_PREFIX}_predecessor_corpus_ref",
            ),
            revocation_policy_ref=_versioned_ref(
                document.get(f"{_PREFIX}_policy_ref"),
                f"{_PREFIX}_policy_ref",
            ),
            revocation_ledger_ref=_versioned_ref(
                document.get(f"{_PREFIX}_ledger_ref"),
                f"{_PREFIX}_ledger_ref",
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=(
                f"sha256:{hashlib.sha256(payload).hexdigest()}"
            ),
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


def _validate_as_of_chronology(
    *,
    corpus: RevocationCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
    evaluated_at: str,
) -> None:
    """Require recorded history to exist before an as-of decision uses it."""

    policy_created = _parse_timestamp(policy.created_at, "policy.created_at")
    ledger_created = _parse_timestamp(ledger.created_at, "ledger.created_at")
    corpus_created = _parse_timestamp(corpus.created_at, "corpus.created_at")
    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if not policy_created <= ledger_created <= corpus_created <= evaluated:
        raise AdjudicatorCredentialRevocationError(
            "revocation policy, ledger, corpus, and evaluation chronology differs"
        )
    for event in events:
        recorded = _parse_timestamp(event.recorded_at, "event.recorded_at")
        if not policy_created <= recorded <= ledger_created:
            raise AdjudicatorCredentialRevocationError(
                f"{event.event_id}: event recording chronology differs from "
                "policy and frozen ledger"
            )


def load_revocation_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: RevocationCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
) -> StoredAdjudicatorCredentialRevocationEvidence:
    """Load the complete generic revocation graph through `1.31.0`."""

    return _load_revocation_evidence(
        store,
        corpus=cast(Any, corpus),
        policy=policy,
        ledger=ledger,
    )


def validate_revocation_ledger(
    *,
    plan: ExperimentPlan,
    corpus: RevocationCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: Any,
    revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    attestations: tuple[Any, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
    evaluated_at: str,
) -> AdjudicatorCredentialRevocationDecisionReport:
    """Evaluate append-only history without rewriting credential evidence."""

    _validate_as_of_chronology(
        corpus=corpus,
        policy=revocation_policy,
        ledger=ledger,
        events=events,
        evaluated_at=evaluated_at,
    )
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


def persist_revocation_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: RevocationCorpusSnapshot,
    predecessor_corpus: Any,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: Any,
    revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
    attestations: tuple[Any, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
    evaluated_at: str,
) -> StoredAdjudicatorCredentialRevocationEvidence:
    """Append policy, events, ledger, then publish `1.31.0` manifest last."""

    _validate_as_of_chronology(
        corpus=corpus,
        policy=revocation_policy,
        ledger=ledger,
        events=events,
        evaluated_at=evaluated_at,
    )
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


globals()[_LONG_CORPUS] = RevocationCorpusSnapshot
globals()[_LONG_LOAD] = load_revocation_evidence
globals()[_LONG_PERSIST] = persist_revocation_bound_corpus
globals()[_LONG_VALIDATE] = validate_revocation_ledger

__all__ = (
    "AdjudicatorCredentialRevocationDecisionReport",
    "AdjudicatorCredentialRevocationError",
    "AdjudicatorCredentialRevocationEventSnapshot",
    "AdjudicatorCredentialRevocationLedgerSnapshot",
    "AdjudicatorCredentialRevocationPolicySnapshot",
    _LONG_CORPUS,
    "StoredAdjudicatorCredentialRevocationEvidence",
    _LONG_LOAD,
    _LONG_PERSIST,
    _LONG_VALIDATE,
)
