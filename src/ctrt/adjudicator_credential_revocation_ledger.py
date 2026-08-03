"""Append-only adjudicator credential status events and as-of evaluation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
    CredentialBoundAdjudicationCorpusSnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.confidence import SystemAbstention
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.reviewer_credential_attestation import (
    CredentialAttestationStatus,
    CredentialDecisionOutcome,
    CredentialIssuerRegistryLifecycle,
    CredentialIssuerRegistrySnapshot,
    CredentialPolicyLifecycle,
)
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistryLifecycle,
    WitnessConflictAdjudicatorRegistrySnapshot,
)


class AdjudicatorCredentialRevocationError(ValueError):
    """Raised when adjudicator revocation provenance or status is invalid."""


class AdjudicatorCredentialRevocationPolicyLifecycle(StrEnum):
    """Governance state of an adjudicator credential revocation policy."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class AdjudicatorCredentialRevocationLedgerLifecycle(StrEnum):
    """Governance state of a frozen adjudicator status-event population."""

    DRAFT = "draft"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must not be empty"
        )


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
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


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must be a boolean"
        )
    return value


def _status_tuple(
    value: object,
    field_name: str,
) -> tuple[CredentialAttestationStatus, ...]:
    if not isinstance(value, list):
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must be an array"
        )
    result = tuple(
        CredentialAttestationStatus(_string(item, field_name)) for item in value
    )
    if len(result) != len(set(result)):
        raise AdjudicatorCredentialRevocationError(
            f"{field_name} must not contain duplicates"
        )
    return result


def _reject_unknown(
    document: Mapping[str, object],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise AdjudicatorCredentialRevocationError(
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


@dataclass(frozen=True, slots=True)
class AdjudicatorCredentialRevocationPolicySnapshot:
    """Frozen issuer, supersession, timing, and abstention rules."""

    policy_id: str
    policy_version: str
    status: AdjudicatorCredentialRevocationPolicyLifecycle
    permitted_effects: tuple[CredentialAttestationStatus, ...]
    require_attestation_issuer: bool
    require_monotonic_effective_time: bool
    require_linear_supersession: bool
    abstain_on_statuses: tuple[CredentialAttestationStatus, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        _parse_timestamp(self.created_at, "created_at")
        required = {
            CredentialAttestationStatus.ACTIVE,
            CredentialAttestationStatus.SUSPENDED,
            CredentialAttestationStatus.REVOKED,
        }
        if set(self.permitted_effects) != required:
            raise AdjudicatorCredentialRevocationError(
                "initial policy must permit active, suspended, and revoked effects"
            )
        if not all(
            (
                self.require_attestation_issuer,
                self.require_monotonic_effective_time,
                self.require_linear_supersession,
            )
        ):
            raise AdjudicatorCredentialRevocationError(
                "initial policy requires exact issuer and linear event history"
            )
        if not {
            CredentialAttestationStatus.SUSPENDED,
            CredentialAttestationStatus.REVOKED,
        }.issubset(self.abstain_on_statuses):
            raise AdjudicatorCredentialRevocationError(
                "policy must abstain on suspended and revoked states"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialRevocationError(
                "policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicatorCredentialRevocationPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "permitted_effects",
                "require_attestation_issuer",
                "require_monotonic_effective_time",
                "require_linear_supersession",
                "abstain_on_statuses",
                "created_at",
            },
            "adjudicator credential revocation policy",
        )
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=AdjudicatorCredentialRevocationPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            permitted_effects=_status_tuple(
                document.get("permitted_effects"),
                "permitted_effects",
            ),
            require_attestation_issuer=_boolean(
                document.get("require_attestation_issuer"),
                "require_attestation_issuer",
            ),
            require_monotonic_effective_time=_boolean(
                document.get("require_monotonic_effective_time"),
                "require_monotonic_effective_time",
            ),
            require_linear_supersession=_boolean(
                document.get("require_linear_supersession"),
                "require_linear_supersession",
            ),
            abstain_on_statuses=_status_tuple(
                document.get("abstain_on_statuses"),
                "abstain_on_statuses",
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
class AdjudicatorCredentialRevocationEventSnapshot:
    """One immutable issuer-authored adjudicator credential status event."""

    artifact_id: str
    event_id: str
    credential_attestation_ref: StoredArtifactRef
    adjudicator_id: str
    issuer_id: str
    issuer_revision: str
    effect: CredentialAttestationStatus
    effective_at: str
    recorded_at: str
    reason: str
    supersedes_event_id: str | None
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.event_id, "event_id"),
            (self.adjudicator_id, "adjudicator_id"),
            (self.issuer_id, "issuer_id"),
            (self.issuer_revision, "issuer_revision"),
            (self.reason, "reason"),
        ):
            _require_non_empty(value, field_name)
        if self.artifact_id != (
            f"adjudicator-credential-revocation-event:{self.event_id}"
        ):
            raise AdjudicatorCredentialRevocationError(
                "event artifact ID must derive from event_id"
            )
        _parse_timestamp(self.effective_at, "effective_at")
        _parse_timestamp(self.recorded_at, "recorded_at")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialRevocationError(
                "event hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicatorCredentialRevocationEventSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "event_id",
                "credential_attestation_ref",
                "adjudicator_id",
                "issuer_id",
                "issuer_revision",
                "effect",
                "effective_at",
                "recorded_at",
                "reason",
                "supersedes_event_id",
            },
            "adjudicator credential revocation event",
        )
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            event_id=_string(document.get("event_id"), "event_id"),
            credential_attestation_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("credential_attestation_ref"),
                    "credential_attestation_ref",
                )
            ),
            adjudicator_id=_string(
                document.get("adjudicator_id"),
                "adjudicator_id",
            ),
            issuer_id=_string(document.get("issuer_id"), "issuer_id"),
            issuer_revision=_string(
                document.get("issuer_revision"),
                "issuer_revision",
            ),
            effect=CredentialAttestationStatus(
                _string(document.get("effect"), "effect")
            ),
            effective_at=_string(document.get("effective_at"), "effective_at"),
            recorded_at=_string(document.get("recorded_at"), "recorded_at"),
            reason=_string(document.get("reason"), "reason"),
            supersedes_event_id=_optional_string(
                document.get("supersedes_event_id"),
                "supersedes_event_id",
            ),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> AdjudicatorCredentialRevocationEventSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdjudicatorCredentialRevocationError(
                "event artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "revocation event"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise AdjudicatorCredentialRevocationError(
                "stored event ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise AdjudicatorCredentialRevocationError(
                "stored event hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise AdjudicatorCredentialRevocationError(
                "stored event is not canonical"
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
class AdjudicatorCredentialRevocationLedgerSnapshot:
    """Frozen ordered event population for one credential-bound corpus."""

    ledger_id: str
    ledger_version: str
    status: AdjudicatorCredentialRevocationLedgerLifecycle
    credential_corpus_ref: VersionedArtifactRef
    issuer_registry_ref: VersionedArtifactRef
    revocation_policy_ref: VersionedArtifactRef
    event_refs: tuple[StoredArtifactRef, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.ledger_id, "ledger_id")
        _require_non_empty(self.ledger_version, "ledger_version")
        _parse_timestamp(self.created_at, "created_at")
        event_ids = tuple(item.artifact_id for item in self.event_refs)
        if len(event_ids) != len(set(event_ids)):
            raise AdjudicatorCredentialRevocationError(
                "ledger event references must be unique"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialRevocationError(
                "ledger hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicatorCredentialRevocationLedgerSnapshot:
        _reject_unknown(
            document,
            {
                "ledger_id",
                "ledger_version",
                "status",
                "credential_corpus_ref",
                "issuer_registry_ref",
                "revocation_policy_ref",
                "event_refs",
                "created_at",
            },
            "adjudicator credential revocation ledger",
        )
        refs_value = document.get("event_refs")
        if not isinstance(refs_value, list):
            raise AdjudicatorCredentialRevocationError(
                "event_refs must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            ledger_id=_string(document.get("ledger_id"), "ledger_id"),
            ledger_version=_string(
                document.get("ledger_version"),
                "ledger_version",
            ),
            status=AdjudicatorCredentialRevocationLedgerLifecycle(
                _string(document.get("status"), "status")
            ),
            credential_corpus_ref=_versioned_ref(
                document.get("credential_corpus_ref"),
                "credential_corpus_ref",
            ),
            issuer_registry_ref=_versioned_ref(
                document.get("issuer_registry_ref"),
                "issuer_registry_ref",
            ),
            revocation_policy_ref=_versioned_ref(
                document.get("revocation_policy_ref"),
                "revocation_policy_ref",
            ),
            event_refs=tuple(
                StoredArtifactRef.from_document(
                    _mapping(item, "revocation event ref")
                )
                for item in refs_value
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.ledger_id,
            artifact_version=self.ledger_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.ledger_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class RevocationBoundAdjudicatorCredentialCorpusSnapshot:
    """Adjudicator credential corpus plus exact revocation policy and ledger."""

    corpus: CredentialBoundAdjudicationCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    revocation_policy_ref: VersionedArtifactRef
    revocation_ledger_ref: VersionedArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> RevocationBoundAdjudicatorCredentialCorpusSnapshot:
        return cls(
            corpus=CredentialBoundAdjudicationCorpusSnapshot.from_document(document),
            predecessor_corpus_ref=_versioned_ref(
                document.get("adjudicator_credential_revocation_predecessor_corpus_ref"),
                "adjudicator_credential_revocation_predecessor_corpus_ref",
            ),
            revocation_policy_ref=_versioned_ref(
                document.get("adjudicator_credential_revocation_policy_ref"),
                "adjudicator_credential_revocation_policy_ref",
            ),
            revocation_ledger_ref=_versioned_ref(
                document.get("adjudicator_credential_revocation_ledger_ref"),
                "adjudicator_credential_revocation_ledger_ref",
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
class AdjudicatorCredentialRevocationSummary:
    """Effective adjudicator credential state at one declared timestamp."""

    adjudicator_id: str
    credential_attestation_ref: StoredArtifactRef
    base_status: CredentialAttestationStatus
    effective_status: CredentialAttestationStatus
    applied_event_ids: tuple[str, ...]
    effective_event_id: str | None
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class AdjudicatorCredentialRevocationDecisionReport:
    """Canonical as-of decision independent of adjudicator correctness."""

    experiment_id: str
    experiment_version: str
    revocation_corpus_ref: VersionedArtifactRef
    revocation_policy_ref: VersionedArtifactRef
    revocation_ledger_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef
    outcome: CredentialDecisionOutcome
    credentials: tuple[AdjudicatorCredentialRevocationSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if not self.credentials:
            raise AdjudicatorCredentialRevocationError(
                "decision requires credential summaries"
            )
        ids = tuple(item.adjudicator_id for item in self.credentials)
        if len(ids) != len(set(ids)):
            raise AdjudicatorCredentialRevocationError(
                "decision adjudicator IDs must be unique"
            )
        expected = (
            CredentialDecisionOutcome.ABSTAIN
            if any(item.abstention.triggered for item in self.credentials)
            else CredentialDecisionOutcome.EXECUTE
        )
        if self.outcome is not expected:
            raise AdjudicatorCredentialRevocationError(
                "decision outcome differs from summaries"
            )

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "adjudicator-credential-revocation-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredAdjudicatorCredentialRevocationEvidence:
    """Stored policy, ledger, and exact immutable event population."""

    corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    event_refs: tuple[StoredArtifactRef, ...]
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...]

    def __post_init__(self) -> None:
        if len(self.event_refs) != len(self.events):
            raise AdjudicatorCredentialRevocationError(
                "stored evidence requires one reference per event"
            )


def _load_event(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> AdjudicatorCredentialRevocationEventSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    event = AdjudicatorCredentialRevocationEventSnapshot.from_artifact(artifact)
    if event.reference() != reference:
        raise ArtifactIntegrityError(
            "stored event reference differs from ledger"
        )
    return event


def load_adjudicator_credential_revocation_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot,
    policy: AdjudicatorCredentialRevocationPolicySnapshot,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
) -> StoredAdjudicatorCredentialRevocationEvidence:
    """Load and reverify corpus, policy, ledger, and event population."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored adjudicator revocation corpus differs from expected"
        )
    policy_artifact = store.get(
        policy.policy_id,
        expected_hash=policy.artifact_hash,
    )
    if policy_artifact.payload != policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudicator revocation policy differs from expected"
        )
    ledger_artifact = store.get(
        ledger.ledger_id,
        expected_hash=ledger.artifact_hash,
    )
    if ledger_artifact.payload != ledger.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudicator revocation ledger differs from expected"
        )
    events = tuple(_load_event(store, reference) for reference in ledger.event_refs)
    return StoredAdjudicatorCredentialRevocationEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        revocation_policy_ref=store.reference(policy.policy_id),
        revocation_ledger_ref=store.reference(ledger.ledger_id),
        event_refs=tuple(item.reference() for item in events),
        events=events,
    )


def validate_adjudicator_credential_revocation_ledger(
    *,
    plan: ExperimentPlan,
    corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot,
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
    """Evaluate the exact append-only event history as of one timestamp."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise AdjudicatorCredentialRevocationError(
            "only a frozen experiment plan may pass revocation"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise AdjudicatorCredentialRevocationError(
            "experiment plan differs from revocation-bound corpus"
        )
    if corpus.revocation_policy_ref != revocation_policy.reference():
        raise AdjudicatorCredentialRevocationError(
            "revocation policy reference differs from corpus"
        )
    if corpus.revocation_ledger_ref != ledger.reference():
        raise AdjudicatorCredentialRevocationError(
            "revocation ledger reference differs from corpus"
        )
    if ledger.credential_corpus_ref != corpus.predecessor_corpus_ref:
        raise AdjudicatorCredentialRevocationError(
            "ledger credential corpus reference differs"
        )
    if ledger.issuer_registry_ref != issuer_registry.reference():
        raise AdjudicatorCredentialRevocationError(
            "ledger issuer registry reference differs"
        )
    if ledger.revocation_policy_ref != revocation_policy.reference():
        raise AdjudicatorCredentialRevocationError(
            "ledger policy reference differs"
        )
    if credential_policy.issuer_registry_ref != issuer_registry.reference():
        raise AdjudicatorCredentialRevocationError(
            "credential policy issuer registry differs"
        )
    if credential_policy.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCredentialRevocationError(
            "credential policy adjudicator registry differs"
        )
    if (
        adjudicator_registry.status
        is not WitnessConflictAdjudicatorRegistryLifecycle.ACCEPTED
    ):
        raise AdjudicatorCredentialRevocationError(
            "adjudicator registry must be accepted"
        )
    if issuer_registry.status is not CredentialIssuerRegistryLifecycle.ACCEPTED:
        raise AdjudicatorCredentialRevocationError(
            "credential issuer registry must be accepted"
        )
    if credential_policy.status is not CredentialPolicyLifecycle.ACCEPTED:
        raise AdjudicatorCredentialRevocationError(
            "credential policy must be accepted"
        )
    if (
        revocation_policy.status
        is not AdjudicatorCredentialRevocationPolicyLifecycle.ACCEPTED
    ):
        raise AdjudicatorCredentialRevocationError(
            "revocation policy must be accepted"
        )
    if (
        ledger.status
        is not AdjudicatorCredentialRevocationLedgerLifecycle.FROZEN
    ):
        raise AdjudicatorCredentialRevocationError(
            "revocation ledger must be frozen"
        )
    if tuple(item.reference() for item in events) != ledger.event_refs:
        raise AdjudicatorCredentialRevocationError(
            "revocation event population differs from ledger"
        )
    if len(attestations) != len(adjudicator_registry.adjudicators):
        raise AdjudicatorCredentialRevocationError(
            "attestation population differs from adjudicator registry"
        )

    attestation_by_ref = {item.reference(): item for item in attestations}
    attestation_by_adjudicator = {
        item.adjudicator_id: item for item in attestations
    }
    failures: list[str] = []
    events_by_adjudicator: dict[
        str,
        list[AdjudicatorCredentialRevocationEventSnapshot],
    ] = defaultdict(list)
    event_ids: set[str] = set()
    for event in events:
        if event.event_id in event_ids:
            failures.append(f"duplicate revocation event ID {event.event_id!r}")
            continue
        event_ids.add(event.event_id)
        attestation = attestation_by_ref.get(event.credential_attestation_ref)
        if attestation is None:
            failures.append(
                f"{event.event_id}: credential attestation reference is unknown"
            )
            continue
        if event.adjudicator_id != attestation.adjudicator_id:
            failures.append(
                f"{event.event_id}: adjudicator ID differs from attestation"
            )
            continue
        issuer = issuer_registry.issuer(event.issuer_id)
        if issuer is None or issuer.issuer_revision != event.issuer_revision:
            failures.append(
                f"{event.event_id}: issuer identity or revision differs"
            )
            continue
        if revocation_policy.require_attestation_issuer and (
            event.issuer_id,
            event.issuer_revision,
        ) != (attestation.issuer_id, attestation.issuer_revision):
            failures.append(
                f"{event.event_id}: event issuer differs from attestation issuer"
            )
            continue
        if event.effect not in revocation_policy.permitted_effects:
            failures.append(
                f"{event.event_id}: event effect is not policy-permitted"
            )
            continue
        events_by_adjudicator[event.adjudicator_id].append(event)

    summaries: list[AdjudicatorCredentialRevocationSummary] = []
    for record in adjudicator_registry.adjudicators:
        attestation = attestation_by_adjudicator.get(record.adjudicator_id)
        if attestation is None:
            failures.append(
                f"{record.adjudicator_id}: credential attestation absent"
            )
            continue
        adjudicator_events = events_by_adjudicator.get(record.adjudicator_id, [])
        previous: AdjudicatorCredentialRevocationEventSnapshot | None = None
        for event in adjudicator_events:
            if previous is None:
                if event.supersedes_event_id is not None:
                    failures.append(
                        f"{event.event_id}: first event may not supersede another event"
                    )
            else:
                if event.supersedes_event_id != previous.event_id:
                    failures.append(
                        f"{event.event_id}: event must supersede immediately prior event"
                    )
                if _parse_timestamp(event.effective_at, "effective_at") < (
                    _parse_timestamp(previous.effective_at, "effective_at")
                ):
                    failures.append(
                        f"{event.event_id}: effective time precedes prior event"
                    )
            previous = event

        effective_status = attestation.status
        applied: list[str] = []
        effective_event_id: str | None = None
        for event in adjudicator_events:
            if _parse_timestamp(event.effective_at, "effective_at") <= evaluated:
                effective_status = event.effect
                effective_event_id = event.event_id
                applied.append(event.event_id)
        reasons: list[str] = []
        if effective_status in revocation_policy.abstain_on_statuses:
            reasons.append(
                f"adjudicator-credential-ledger-status:{effective_status.value}"
            )
        summaries.append(
            AdjudicatorCredentialRevocationSummary(
                adjudicator_id=record.adjudicator_id,
                credential_attestation_ref=attestation.reference(),
                base_status=attestation.status,
                effective_status=effective_status,
                applied_event_ids=tuple(applied),
                effective_event_id=effective_event_id,
                abstention=SystemAbstention(
                    triggered=bool(reasons),
                    reasons=tuple(reasons),
                ),
            )
        )

    covered_ids = {item.adjudicator_id for item in summaries}
    if adjudication.adjudicator_id is not None and (
        adjudication.adjudicator_id not in covered_ids
    ):
        failures.append(
            "adjudication named an adjudicator without revocation status"
        )

    if failures:
        raise AdjudicatorCredentialRevocationError(
            "adjudicator credential revocation evidence failed: "
            + " | ".join(failures)
        )
    outcome = (
        CredentialDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in summaries)
        else CredentialDecisionOutcome.EXECUTE
    )
    return AdjudicatorCredentialRevocationDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        revocation_corpus_ref=corpus.reference(),
        revocation_policy_ref=revocation_policy.reference(),
        revocation_ledger_ref=ledger.reference(),
        adjudication_ref=adjudication.reference(),
        outcome=outcome,
        credentials=tuple(summaries),
        evaluated_at=evaluated_at,
    )


def persist_adjudicator_credential_revocation_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot,
    predecessor_corpus: CredentialBoundAdjudicationCorpusSnapshot,
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
    """Persist events, policy, ledger, then publish the successor corpus last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise AdjudicatorCredentialRevocationError(
            "predecessor credential corpus reference differs"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise AdjudicatorCredentialRevocationError(
            "revocation corpus content population differs"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored predecessor credential corpus differs"
        )
    validate_adjudicator_credential_revocation_ledger(
        plan=plan,
        corpus=corpus,
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
    if store.append(revocation_policy.artifact()).artifact_hash != (
        revocation_policy.artifact_hash
    ):
        raise ArtifactIntegrityError(
            "stored adjudicator revocation policy reference differs"
        )
    for event in events:
        if store.append(event.artifact()) != event.reference():
            raise ArtifactIntegrityError(
                "stored adjudicator revocation event reference differs"
            )
    if store.append(ledger.artifact()).artifact_hash != ledger.artifact_hash:
        raise ArtifactIntegrityError(
            "stored adjudicator revocation ledger reference differs"
        )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored adjudicator revocation corpus reference differs"
        )
    return load_adjudicator_credential_revocation_evidence(
        store,
        corpus=corpus,
        policy=revocation_policy,
        ledger=ledger,
    )
