"""Issuer-bound credentials for witness-conflict adjudicator identities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

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
    AdjudicationBoundWitnessCorpusSnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistryLifecycle,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictAdjudicatorRole,
)


class AdjudicatorCredentialError(ValueError):
    """Raised when adjudicator credential provenance or policy is invalid."""


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise AdjudicatorCredentialError(f"{field_name} must not be empty")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AdjudicatorCredentialError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise AdjudicatorCredentialError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCredentialError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise AdjudicatorCredentialError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicatorCredentialError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise AdjudicatorCredentialError(f"{field_name} must be a boolean")
    return value


def _reject_unknown(
    document: Mapping[str, object],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise AdjudicatorCredentialError(
            f"{field_name} contains unsupported fields: {', '.join(unknown)}"
        )


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


def _role_tuple(
    value: object,
    field_name: str,
) -> tuple[WitnessConflictAdjudicatorRole, ...]:
    if not isinstance(value, list):
        raise AdjudicatorCredentialError(f"{field_name} must be an array")
    result = tuple(
        WitnessConflictAdjudicatorRole(_string(item, field_name)) for item in value
    )
    if not result:
        raise AdjudicatorCredentialError(f"{field_name} must not be empty")
    if len(result) != len(set(result)):
        raise AdjudicatorCredentialError(f"{field_name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class AdjudicatorCredentialPolicySnapshot:
    """Frozen validity and exact-role policy for adjudicator credentials."""

    policy_id: str
    policy_version: str
    status: CredentialPolicyLifecycle
    issuer_registry_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    credential_type: str
    require_exact_role_match: bool
    abstain_on_not_yet_valid: bool
    abstain_on_expired: bool
    abstain_on_suspended: bool
    abstain_on_revoked: bool
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        _require_non_empty(self.credential_type, "credential_type")
        _parse_timestamp(self.created_at, "created_at")
        if not self.require_exact_role_match:
            raise AdjudicatorCredentialError(
                "initial adjudicator credential policy requires exact role matching"
            )
        if not all(
            (
                self.abstain_on_not_yet_valid,
                self.abstain_on_expired,
                self.abstain_on_suspended,
                self.abstain_on_revoked,
            )
        ):
            raise AdjudicatorCredentialError(
                "adjudicator credential policy must abstain on every invalidity state"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialError(
                "adjudicator credential policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicatorCredentialPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "issuer_registry_ref",
                "adjudicator_registry_ref",
                "credential_type",
                "require_exact_role_match",
                "abstain_on_not_yet_valid",
                "abstain_on_expired",
                "abstain_on_suspended",
                "abstain_on_revoked",
                "created_at",
            },
            "adjudicator credential policy",
        )
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=CredentialPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            issuer_registry_ref=_versioned_ref(
                document.get("issuer_registry_ref"),
                "issuer_registry_ref",
            ),
            adjudicator_registry_ref=_versioned_ref(
                document.get("adjudicator_registry_ref"),
                "adjudicator_registry_ref",
            ),
            credential_type=_string(
                document.get("credential_type"),
                "credential_type",
            ),
            require_exact_role_match=_boolean(
                document.get("require_exact_role_match"),
                "require_exact_role_match",
            ),
            abstain_on_not_yet_valid=_boolean(
                document.get("abstain_on_not_yet_valid"),
                "abstain_on_not_yet_valid",
            ),
            abstain_on_expired=_boolean(
                document.get("abstain_on_expired"),
                "abstain_on_expired",
            ),
            abstain_on_suspended=_boolean(
                document.get("abstain_on_suspended"),
                "abstain_on_suspended",
            ),
            abstain_on_revoked=_boolean(
                document.get("abstain_on_revoked"),
                "abstain_on_revoked",
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
class AdjudicatorCredentialAttestationSnapshot:
    """Immutable issuer attestation for one adjudicator identity revision."""

    artifact_id: str
    attestation_id: str
    credential_type: str
    adjudicator_id: str
    identity_revision: str
    subject_reference: str
    issuer_id: str
    issuer_revision: str
    authorized_roles: tuple[WitnessConflictAdjudicatorRole, ...]
    status: CredentialAttestationStatus
    issued_at: str
    valid_from: str
    valid_until: str
    revoked_at: str | None
    revocation_reason: str | None
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.attestation_id, "attestation_id"),
            (self.credential_type, "credential_type"),
            (self.adjudicator_id, "adjudicator_id"),
            (self.identity_revision, "identity_revision"),
            (self.subject_reference, "subject_reference"),
            (self.issuer_id, "issuer_id"),
            (self.issuer_revision, "issuer_revision"),
        ):
            _require_non_empty(value, field_name)
        if self.artifact_id != f"adjudicator-credential:{self.attestation_id}":
            raise AdjudicatorCredentialError(
                "adjudicator credential artifact ID must derive from attestation_id"
            )
        expected_subject = (
            f"witness-conflict-adjudicator:{self.adjudicator_id}@"
            f"{self.identity_revision}"
        )
        if self.subject_reference != expected_subject:
            raise AdjudicatorCredentialError(
                "subject_reference must bind adjudicator identity revision"
            )
        if len(self.authorized_roles) != len(set(self.authorized_roles)):
            raise AdjudicatorCredentialError(
                "adjudicator credential roles must be unique"
            )
        issued = _parse_timestamp(self.issued_at, "issued_at")
        valid_from = _parse_timestamp(self.valid_from, "valid_from")
        valid_until = _parse_timestamp(self.valid_until, "valid_until")
        if issued > valid_from:
            raise AdjudicatorCredentialError(
                "credential issued_at may not be after valid_from"
            )
        if valid_from >= valid_until:
            raise AdjudicatorCredentialError(
                "credential validity window must be increasing"
            )
        if self.status is CredentialAttestationStatus.REVOKED:
            if self.revoked_at is None or self.revocation_reason is None:
                raise AdjudicatorCredentialError(
                    "revoked credential requires timestamp and reason"
                )
            if _parse_timestamp(self.revoked_at, "revoked_at") < issued:
                raise AdjudicatorCredentialError(
                    "credential revocation may not precede issuance"
                )
        elif self.revoked_at is not None or self.revocation_reason is not None:
            raise AdjudicatorCredentialError(
                "non-revoked credential may not contain revocation state"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise AdjudicatorCredentialError(
                "adjudicator credential hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicatorCredentialAttestationSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "attestation_id",
                "credential_type",
                "adjudicator_id",
                "identity_revision",
                "subject_reference",
                "issuer_id",
                "issuer_revision",
                "authorized_roles",
                "status",
                "issued_at",
                "valid_from",
                "valid_until",
                "revoked_at",
                "revocation_reason",
            },
            "adjudicator credential attestation",
        )
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            attestation_id=_string(
                document.get("attestation_id"),
                "attestation_id",
            ),
            credential_type=_string(
                document.get("credential_type"),
                "credential_type",
            ),
            adjudicator_id=_string(
                document.get("adjudicator_id"),
                "adjudicator_id",
            ),
            identity_revision=_string(
                document.get("identity_revision"),
                "identity_revision",
            ),
            subject_reference=_string(
                document.get("subject_reference"),
                "subject_reference",
            ),
            issuer_id=_string(document.get("issuer_id"), "issuer_id"),
            issuer_revision=_string(
                document.get("issuer_revision"),
                "issuer_revision",
            ),
            authorized_roles=_role_tuple(
                document.get("authorized_roles"),
                "authorized_roles",
            ),
            status=CredentialAttestationStatus(
                _string(document.get("status"), "status")
            ),
            issued_at=_string(document.get("issued_at"), "issued_at"),
            valid_from=_string(document.get("valid_from"), "valid_from"),
            valid_until=_string(document.get("valid_until"), "valid_until"),
            revoked_at=_optional_string(
                document.get("revoked_at"),
                "revoked_at",
            ),
            revocation_reason=_optional_string(
                document.get("revocation_reason"),
                "revocation_reason",
            ),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> AdjudicatorCredentialAttestationSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdjudicatorCredentialError(
                "adjudicator credential artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "adjudicator credential"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise AdjudicatorCredentialError(
                "stored adjudicator credential ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise AdjudicatorCredentialError(
                "stored adjudicator credential hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise AdjudicatorCredentialError(
                "stored adjudicator credential is not canonical"
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
class AdjudicatorCredentialEvidenceEntry:
    """Exact credential reference for one adjudicator identity revision."""

    adjudicator_id: str
    identity_revision: str
    credential_attestation_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> AdjudicatorCredentialEvidenceEntry:
        _reject_unknown(
            document,
            {"adjudicator_id", "identity_revision", "credential_attestation_ref"},
            "adjudicator credential entry",
        )
        return cls(
            adjudicator_id=_string(
                document.get("adjudicator_id"),
                "adjudicator_id",
            ),
            identity_revision=_string(
                document.get("identity_revision"),
                "identity_revision",
            ),
            credential_attestation_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("credential_attestation_ref"),
                    "credential_attestation_ref",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class CredentialBoundAdjudicationCorpusSnapshot:
    """Adjudication-bound corpus plus exact credential evidence references."""

    corpus: AdjudicationBoundWitnessCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    issuer_registry_ref: VersionedArtifactRef
    credential_policy_ref: VersionedArtifactRef
    credential_entries: tuple[AdjudicatorCredentialEvidenceEntry, ...]

    def __post_init__(self) -> None:
        ids = tuple(item.adjudicator_id for item in self.credential_entries)
        if not ids:
            raise AdjudicatorCredentialError(
                "credential-bound adjudication corpus requires credentials"
            )
        if len(ids) != len(set(ids)):
            raise AdjudicatorCredentialError(
                "adjudicator credential entries must use unique IDs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialBoundAdjudicationCorpusSnapshot:
        values = document.get("witness_conflict_adjudicator_credentials")
        if not isinstance(values, list):
            raise AdjudicatorCredentialError(
                "witness_conflict_adjudicator_credentials must be an array"
            )
        return cls(
            corpus=AdjudicationBoundWitnessCorpusSnapshot.from_document(document),
            predecessor_corpus_ref=_versioned_ref(
                document.get("adjudicator_credential_predecessor_corpus_ref"),
                "adjudicator_credential_predecessor_corpus_ref",
            ),
            issuer_registry_ref=_versioned_ref(
                document.get("adjudicator_credential_issuer_registry_ref"),
                "adjudicator_credential_issuer_registry_ref",
            ),
            credential_policy_ref=_versioned_ref(
                document.get("adjudicator_credential_policy_ref"),
                "adjudicator_credential_policy_ref",
            ),
            credential_entries=tuple(
                AdjudicatorCredentialEvidenceEntry.from_document(
                    _mapping(item, "adjudicator credential entry")
                )
                for item in values
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
class AdjudicatorCredentialSummary:
    """Decision-facing eligibility without private identity attributes."""

    adjudicator_id: str
    identity_revision: str
    issuer_id: str
    issuer_revision: str
    authorized_roles: tuple[WitnessConflictAdjudicatorRole, ...]
    attestation_status: CredentialAttestationStatus
    valid_from: str
    valid_until: str
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class AdjudicatorCredentialDecisionReport:
    """Canonical credential decision separate from adjudication correctness."""

    experiment_id: str
    experiment_version: str
    credential_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: VersionedArtifactRef
    issuer_registry_ref: VersionedArtifactRef
    credential_policy_ref: VersionedArtifactRef
    adjudication_ref: StoredArtifactRef
    outcome: CredentialDecisionOutcome
    credentials: tuple[AdjudicatorCredentialSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if not self.credentials:
            raise AdjudicatorCredentialError(
                "adjudicator credential decision requires summaries"
            )
        ids = tuple(item.adjudicator_id for item in self.credentials)
        if len(ids) != len(set(ids)):
            raise AdjudicatorCredentialError(
                "adjudicator credential decision IDs must be unique"
            )
        abstaining = any(item.abstention.triggered for item in self.credentials)
        expected = (
            CredentialDecisionOutcome.ABSTAIN
            if abstaining
            else CredentialDecisionOutcome.EXECUTE
        )
        if self.outcome is not expected:
            raise AdjudicatorCredentialError(
                "adjudicator credential outcome must reflect abstention evidence"
            )

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "adjudicator-credential-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredAdjudicatorCredentialEvidence:
    """Stored issuer, policy, credential, and predecessor adjudication evidence."""

    corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    attestation_refs: tuple[StoredArtifactRef, ...]
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...]


def _load_attestation(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> AdjudicatorCredentialAttestationSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    attestation = AdjudicatorCredentialAttestationSnapshot.from_artifact(artifact)
    if attestation.reference() != reference:
        raise ArtifactIntegrityError(
            "stored adjudicator credential reference differs from corpus"
        )
    return attestation


def load_adjudicator_credential_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CredentialBoundAdjudicationCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredAdjudicatorCredentialEvidence:
    """Load and reverify the credential-bound adjudication graph."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored adjudicator-credential corpus differs from expected"
        )
    registry_artifact = store.get(
        adjudicator_registry.registry_id,
        expected_hash=adjudicator_registry.artifact_hash,
    )
    if registry_artifact.payload != adjudicator_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudicator registry differs from expected"
        )
    issuer_artifact = store.get(
        issuer_registry.registry_id,
        expected_hash=issuer_registry.artifact_hash,
    )
    if issuer_artifact.payload != issuer_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudicator credential issuer registry differs"
        )
    policy_artifact = store.get(
        credential_policy.policy_id,
        expected_hash=credential_policy.artifact_hash,
    )
    if policy_artifact.payload != credential_policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored adjudicator credential policy differs"
        )
    adjudication_artifact = store.get(
        adjudication.artifact_id,
        expected_hash=adjudication.artifact_hash,
    )
    if adjudication_artifact.payload != adjudication.canonical_payload:
        raise ArtifactIntegrityError("stored adjudication differs from expected")
    attestations = tuple(
        _load_attestation(store, item.credential_attestation_ref)
        for item in corpus.credential_entries
    )
    return StoredAdjudicatorCredentialEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        adjudicator_registry_ref=store.reference(adjudicator_registry.registry_id),
        issuer_registry_ref=store.reference(issuer_registry.registry_id),
        credential_policy_ref=store.reference(credential_policy.policy_id),
        adjudication_ref=store.reference(adjudication.artifact_id),
        attestation_refs=tuple(item.reference() for item in attestations),
        attestations=attestations,
    )


def validate_adjudicator_credential_attestations(
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundAdjudicationCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> AdjudicatorCredentialDecisionReport:
    """Evaluate adjudicator credentials without altering adjudication evidence."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise AdjudicatorCredentialError(
            "only a frozen experiment plan may pass adjudicator credentials"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise AdjudicatorCredentialError(
            "experiment plan differs from credential-bound adjudication corpus"
        )
    if corpus.corpus.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCredentialError(
            "adjudicator registry reference differs from predecessor corpus"
        )
    if corpus.issuer_registry_ref != issuer_registry.reference():
        raise AdjudicatorCredentialError("credential issuer registry reference differs")
    if corpus.credential_policy_ref != credential_policy.reference():
        raise AdjudicatorCredentialError("adjudicator credential policy reference differs")
    if corpus.corpus.adjudication_ref != adjudication.reference():
        raise AdjudicatorCredentialError("adjudication reference differs from corpus")
    if adjudicator_registry.status is not (
        WitnessConflictAdjudicatorRegistryLifecycle.ACCEPTED
    ):
        raise AdjudicatorCredentialError("adjudicator registry must be accepted")
    if issuer_registry.status is not CredentialIssuerRegistryLifecycle.ACCEPTED:
        raise AdjudicatorCredentialError("credential issuer registry must be accepted")
    if credential_policy.status is not CredentialPolicyLifecycle.ACCEPTED:
        raise AdjudicatorCredentialError("adjudicator credential policy must be accepted")
    if credential_policy.issuer_registry_ref != issuer_registry.reference():
        raise AdjudicatorCredentialError("credential policy issuer registry differs")
    if credential_policy.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCredentialError("credential policy adjudicator registry differs")
    if len(corpus.credential_entries) != len(adjudicator_registry.adjudicators):
        raise AdjudicatorCredentialError(
            "credential population must match adjudicator registry"
        )
    if len(attestations) != len(corpus.credential_entries):
        raise AdjudicatorCredentialError(
            "adjudicator credential population differs from corpus"
        )

    failures: list[str] = []
    summaries: list[AdjudicatorCredentialSummary] = []
    by_id: dict[str, AdjudicatorCredentialAttestationSnapshot] = {}
    for adjudicator, entry, attestation in zip(
        adjudicator_registry.adjudicators,
        corpus.credential_entries,
        attestations,
        strict=True,
    ):
        if (entry.adjudicator_id, entry.identity_revision) != (
            adjudicator.adjudicator_id,
            adjudicator.identity_revision,
        ):
            failures.append(
                f"{adjudicator.adjudicator_id}: credential entry identity differs"
            )
            continue
        if attestation.reference() != entry.credential_attestation_ref:
            failures.append(
                f"{adjudicator.adjudicator_id}: credential reference differs"
            )
            continue
        if (attestation.adjudicator_id, attestation.identity_revision) != (
            adjudicator.adjudicator_id,
            adjudicator.identity_revision,
        ):
            failures.append(
                f"{adjudicator.adjudicator_id}: attested identity revision differs"
            )
            continue
        expected_roles = (adjudicator.role,)
        if credential_policy.require_exact_role_match and (
            attestation.authorized_roles != expected_roles
        ):
            failures.append(
                f"{adjudicator.adjudicator_id}: attested role differs from registry"
            )
            continue
        if attestation.credential_type != credential_policy.credential_type:
            failures.append(
                f"{adjudicator.adjudicator_id}: credential type differs from policy"
            )
            continue
        issuer = issuer_registry.issuer(attestation.issuer_id)
        if issuer is None:
            failures.append(
                f"{adjudicator.adjudicator_id}: attestation issuer is absent"
            )
            continue
        if issuer.issuer_revision != attestation.issuer_revision:
            failures.append(
                f"{adjudicator.adjudicator_id}: issuer revision differs"
            )
            continue
        if attestation.credential_type not in issuer.credential_types:
            failures.append(
                f"{adjudicator.adjudicator_id}: issuer may not issue credential type"
            )
            continue

        reasons: list[str] = []
        if not issuer.active:
            reasons.append("credential-issuer-inactive")
        if attestation.status is CredentialAttestationStatus.SUSPENDED:
            reasons.append("credential-status:suspended")
        elif attestation.status is CredentialAttestationStatus.REVOKED:
            reasons.append("credential-status:revoked")
        valid_from = _parse_timestamp(attestation.valid_from, "valid_from")
        valid_until = _parse_timestamp(attestation.valid_until, "valid_until")
        if evaluated < valid_from:
            reasons.append("credential-not-yet-valid")
        if evaluated >= valid_until:
            reasons.append("credential-expired")
        summaries.append(
            AdjudicatorCredentialSummary(
                adjudicator_id=adjudicator.adjudicator_id,
                identity_revision=adjudicator.identity_revision,
                issuer_id=attestation.issuer_id,
                issuer_revision=attestation.issuer_revision,
                authorized_roles=attestation.authorized_roles,
                attestation_status=attestation.status,
                valid_from=attestation.valid_from,
                valid_until=attestation.valid_until,
                abstention=SystemAbstention(
                    triggered=bool(reasons),
                    reasons=tuple(reasons),
                ),
            )
        )
        by_id[adjudicator.adjudicator_id] = attestation

    if adjudication.adjudicator_id is not None:
        attestation = by_id.get(adjudication.adjudicator_id)
        if attestation is None:
            failures.append("adjudication credential is absent")
        elif (
            adjudication.adjudicator_identity_revision
            != attestation.identity_revision
        ):
            failures.append("adjudication identity revision differs from credential")
        elif WitnessConflictAdjudicatorRole.WITNESS_CONFLICT_ADJUDICATOR not in (
            attestation.authorized_roles
        ):
            failures.append("adjudication role is not attested")

    if failures:
        raise AdjudicatorCredentialError(
            "adjudicator credential evidence failed: " + " | ".join(failures)
        )
    outcome = (
        CredentialDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in summaries)
        else CredentialDecisionOutcome.EXECUTE
    )
    return AdjudicatorCredentialDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        credential_corpus_ref=corpus.reference(),
        adjudicator_registry_ref=adjudicator_registry.reference(),
        issuer_registry_ref=issuer_registry.reference(),
        credential_policy_ref=credential_policy.reference(),
        adjudication_ref=adjudication.reference(),
        outcome=outcome,
        credentials=tuple(summaries),
        evaluated_at=evaluated_at,
    )


def persist_credential_bound_adjudication_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundAdjudicationCorpusSnapshot,
    predecessor_corpus: AdjudicationBoundWitnessCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredAdjudicatorCredentialEvidence:
    """Persist credential graph members before publishing the manifest last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise AdjudicatorCredentialError(
            "predecessor corpus reference differs from credential-bound corpus"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise AdjudicatorCredentialError(
            "credential-bound corpus content population differs from predecessor"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored predecessor adjudication corpus differs from expected"
        )
    decision = validate_adjudicator_credential_attestations(
        plan=plan,
        corpus=corpus,
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        attestations=attestations,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )
    if decision.outcome is CredentialDecisionOutcome.ABSTAIN:
        raise AdjudicatorCredentialError(
            "credential-bound corpus publication requires eligible attestations"
        )
    if store.append(issuer_registry.artifact()).artifact_hash != (
        issuer_registry.artifact_hash
    ):
        raise ArtifactIntegrityError("stored credential issuer registry differs")
    if store.append(credential_policy.artifact()).artifact_hash != (
        credential_policy.artifact_hash
    ):
        raise ArtifactIntegrityError("stored adjudicator credential policy differs")
    for attestation in attestations:
        if store.append(attestation.artifact()) != attestation.reference():
            raise ArtifactIntegrityError(
                "stored adjudicator credential attestation differs"
            )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored adjudicator-credential corpus reference differs"
        )
    return load_adjudicator_credential_evidence(
        store,
        corpus=corpus,
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        adjudication=adjudication,
    )
