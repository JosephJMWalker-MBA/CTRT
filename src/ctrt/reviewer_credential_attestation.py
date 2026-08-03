"""Reviewer credential issuer, attestation, validity, and revocation contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.confidence import SystemAbstention
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import (
    ReviewAdjudicationPolicySnapshot,
    ReviewAdjudicationSnapshot,
    ReviewBoundExtractionCorpusSnapshot,
    ReviewerRegistrySnapshot,
    ReviewerRole,
)
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes


class ReviewerCredentialError(ValueError):
    """Raised when credential provenance or policy binding is invalid."""


class CredentialIssuerRegistryLifecycle(StrEnum):
    """Governance state of one credential issuer registry."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class CredentialPolicyLifecycle(StrEnum):
    """Governance state of one reviewer-credential policy."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class CredentialAttestationStatus(StrEnum):
    """Immutable status declared by one credential attestation."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class CredentialDecisionOutcome(StrEnum):
    """Whether credential evidence permits review adjudication to proceed."""

    EXECUTE = "execute"
    ABSTAIN = "abstain"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ReviewerCredentialError(f"{field_name} must not be empty")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReviewerCredentialError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ReviewerCredentialError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReviewerCredentialError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ReviewerCredentialError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewerCredentialError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ReviewerCredentialError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ReviewerCredentialError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise ReviewerCredentialError(
            f"{field_name} must not contain duplicates"
        )
    return result


def _role_tuple(value: object, field_name: str) -> tuple[ReviewerRole, ...]:
    if not isinstance(value, list):
        raise ReviewerCredentialError(f"{field_name} must be an array")
    result = tuple(ReviewerRole(_string(item, field_name)) for item in value)
    if len(result) != len(set(result)):
        raise ReviewerCredentialError(
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
        raise ReviewerCredentialError(
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
class CredentialIssuerRecord:
    """One immutable issuer identity and its authorized credential types."""

    issuer_id: str
    issuer_revision: str
    credential_types: tuple[str, ...]
    active: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.issuer_id, "issuer_id")
        _require_non_empty(self.issuer_revision, "issuer_revision")
        if not self.credential_types:
            raise ReviewerCredentialError(
                "credential issuer requires credential types"
            )
        if len(self.credential_types) != len(set(self.credential_types)):
            raise ReviewerCredentialError(
                "issuer credential types must be unique"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialIssuerRecord:
        _reject_unknown(
            document,
            {"issuer_id", "issuer_revision", "credential_types", "active"},
            "credential issuer",
        )
        return cls(
            issuer_id=_string(document.get("issuer_id"), "issuer_id"),
            issuer_revision=_string(
                document.get("issuer_revision"),
                "issuer_revision",
            ),
            credential_types=_string_tuple(
                document.get("credential_types"),
                "credential_types",
            ),
            active=_boolean(document.get("active"), "active"),
        )


@dataclass(frozen=True, slots=True)
class CredentialIssuerRegistrySnapshot:
    """Frozen issuer identities accepted for reviewer attestations."""

    registry_id: str
    registry_version: str
    status: CredentialIssuerRegistryLifecycle
    issuers: tuple[CredentialIssuerRecord, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.registry_id, "registry_id")
        _require_non_empty(self.registry_version, "registry_version")
        _parse_timestamp(self.created_at, "created_at")
        issuer_ids = tuple(item.issuer_id for item in self.issuers)
        if not issuer_ids:
            raise ReviewerCredentialError(
                "credential issuer registry requires issuers"
            )
        if len(issuer_ids) != len(set(issuer_ids)):
            raise ReviewerCredentialError(
                "credential issuer IDs must be unique"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ReviewerCredentialError(
                "credential issuer registry hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialIssuerRegistrySnapshot:
        _reject_unknown(
            document,
            {
                "registry_id",
                "registry_version",
                "status",
                "issuers",
                "created_at",
            },
            "credential issuer registry",
        )
        issuers_value = document.get("issuers")
        if not isinstance(issuers_value, list):
            raise ReviewerCredentialError("issuers must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            registry_id=_string(document.get("registry_id"), "registry_id"),
            registry_version=_string(
                document.get("registry_version"),
                "registry_version",
            ),
            status=CredentialIssuerRegistryLifecycle(
                _string(document.get("status"), "status")
            ),
            issuers=tuple(
                CredentialIssuerRecord.from_document(
                    _mapping(item, "credential issuer")
                )
                for item in issuers_value
            ),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        return VersionedArtifactRef(
            artifact_id=self.registry_id,
            artifact_version=self.registry_version,
            artifact_hash=self.artifact_hash,
        )

    def artifact(self) -> CanonicalArtifact:
        return CanonicalArtifact(
            artifact_id=self.registry_id,
            payload=self.canonical_payload,
            artifact_hash=self.artifact_hash,
        )

    def issuer(self, issuer_id: str) -> CredentialIssuerRecord | None:
        return next(
            (item for item in self.issuers if item.issuer_id == issuer_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class ReviewerCredentialPolicySnapshot:
    """Frozen policy for validity, revocation, role binding, and abstention."""

    policy_id: str
    policy_version: str
    status: CredentialPolicyLifecycle
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
            raise ReviewerCredentialError(
                "initial credential policy requires exact role matching"
            )
        if not all(
            (
                self.abstain_on_not_yet_valid,
                self.abstain_on_expired,
                self.abstain_on_suspended,
                self.abstain_on_revoked,
            )
        ):
            raise ReviewerCredentialError(
                "credential policy must abstain on every invalidity state"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ReviewerCredentialError(
                "credential policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerCredentialPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "credential_type",
                "require_exact_role_match",
                "abstain_on_not_yet_valid",
                "abstain_on_expired",
                "abstain_on_suspended",
                "abstain_on_revoked",
                "created_at",
            },
            "reviewer credential policy",
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
class ReviewerCredentialAttestationSnapshot:
    """One immutable issuer attestation for one reviewer identity revision."""

    artifact_id: str
    attestation_id: str
    credential_type: str
    reviewer_id: str
    identity_revision: str
    subject_reference: str
    issuer_id: str
    issuer_revision: str
    authorized_roles: tuple[ReviewerRole, ...]
    status: CredentialAttestationStatus
    issued_at: str
    valid_from: str
    valid_until: str
    revoked_at: str | None
    revocation_reason: str | None
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.attestation_id, "attestation_id"),
            (self.credential_type, "credential_type"),
            (self.reviewer_id, "reviewer_id"),
            (self.identity_revision, "identity_revision"),
            (self.subject_reference, "subject_reference"),
            (self.issuer_id, "issuer_id"),
            (self.issuer_revision, "issuer_revision"),
        ):
            _require_non_empty(value, name)
        if self.artifact_id != f"reviewer-credential:{self.attestation_id}":
            raise ReviewerCredentialError(
                "credential artifact ID must derive from attestation_id"
            )
        expected_subject = f"reviewer:{self.reviewer_id}@{self.identity_revision}"
        if self.subject_reference != expected_subject:
            raise ReviewerCredentialError(
                "subject_reference must bind reviewer identity revision"
            )
        if not self.authorized_roles:
            raise ReviewerCredentialError(
                "credential attestation requires authorized roles"
            )
        if len(self.authorized_roles) != len(set(self.authorized_roles)):
            raise ReviewerCredentialError(
                "credential authorized roles must be unique"
            )
        issued = _parse_timestamp(self.issued_at, "issued_at")
        valid_from = _parse_timestamp(self.valid_from, "valid_from")
        valid_until = _parse_timestamp(self.valid_until, "valid_until")
        if issued > valid_from:
            raise ReviewerCredentialError(
                "credential issued_at may not be after valid_from"
            )
        if valid_from >= valid_until:
            raise ReviewerCredentialError(
                "credential validity window must be increasing"
            )
        if self.status is CredentialAttestationStatus.REVOKED:
            if self.revoked_at is None or self.revocation_reason is None:
                raise ReviewerCredentialError(
                    "revoked credential requires timestamp and reason"
                )
            revoked = _parse_timestamp(self.revoked_at, "revoked_at")
            if revoked < issued:
                raise ReviewerCredentialError(
                    "credential revocation may not precede issuance"
                )
        elif self.revoked_at is not None or self.revocation_reason is not None:
            raise ReviewerCredentialError(
                "non-revoked credential may not contain revocation state"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ReviewerCredentialError(
                "credential attestation hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerCredentialAttestationSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "attestation_id",
                "credential_type",
                "reviewer_id",
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
            "reviewer credential attestation",
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
            reviewer_id=_string(document.get("reviewer_id"), "reviewer_id"),
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
    ) -> ReviewerCredentialAttestationSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReviewerCredentialError(
                "credential attestation artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "credential attestation"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise ReviewerCredentialError(
                "stored credential attestation ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise ReviewerCredentialError(
                "stored credential attestation hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise ReviewerCredentialError(
                "stored credential attestation is not canonical"
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
class ReviewerCredentialEvidenceEntry:
    """One ordered credential reference for one reviewer identity revision."""

    reviewer_id: str
    identity_revision: str
    credential_attestation_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerCredentialEvidenceEntry:
        return cls(
            reviewer_id=_string(document.get("reviewer_id"), "reviewer_id"),
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
class CredentialBoundReviewCorpusSnapshot:
    """Review-bound corpus plus exact credential policy and attestation refs."""

    corpus: ReviewBoundExtractionCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    credential_issuer_registry_ref: VersionedArtifactRef
    reviewer_credential_policy_ref: VersionedArtifactRef
    credential_entries: tuple[ReviewerCredentialEvidenceEntry, ...]

    def __post_init__(self) -> None:
        reviewer_ids = tuple(item.reviewer_id for item in self.credential_entries)
        if not reviewer_ids:
            raise ReviewerCredentialError(
                "credential-bound corpus requires reviewer credentials"
            )
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ReviewerCredentialError(
                "credential entries must use unique reviewer IDs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialBoundReviewCorpusSnapshot:
        entries_value = document.get("reviewer_credentials")
        if not isinstance(entries_value, list):
            raise ReviewerCredentialError(
                "reviewer_credentials must be an array"
            )
        return cls(
            corpus=ReviewBoundExtractionCorpusSnapshot.from_document(document),
            predecessor_corpus_ref=_versioned_ref(
                document.get("predecessor_corpus_ref"),
                "predecessor_corpus_ref",
            ),
            credential_issuer_registry_ref=_versioned_ref(
                document.get("credential_issuer_registry_ref"),
                "credential_issuer_registry_ref",
            ),
            reviewer_credential_policy_ref=_versioned_ref(
                document.get("reviewer_credential_policy_ref"),
                "reviewer_credential_policy_ref",
            ),
            credential_entries=tuple(
                ReviewerCredentialEvidenceEntry.from_document(
                    _mapping(item, "reviewer credential entry")
                )
                for item in entries_value
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
class ReviewerCredentialSummary:
    """Decision-facing credential status without private identity attributes."""

    reviewer_id: str
    identity_revision: str
    issuer_id: str
    issuer_revision: str
    authorized_roles: tuple[ReviewerRole, ...]
    attestation_status: CredentialAttestationStatus
    valid_from: str
    valid_until: str
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class ReviewerCredentialDecisionReport:
    """Canonical credential decision separate from review correctness."""

    experiment_id: str
    experiment_version: str
    credential_corpus_ref: VersionedArtifactRef
    reviewer_registry_ref: VersionedArtifactRef
    credential_issuer_registry_ref: VersionedArtifactRef
    reviewer_credential_policy_ref: VersionedArtifactRef
    outcome: CredentialDecisionOutcome
    credentials: tuple[ReviewerCredentialSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if not self.credentials:
            raise ReviewerCredentialError(
                "credential decision requires credential summaries"
            )
        reviewer_ids = tuple(item.reviewer_id for item in self.credentials)
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ReviewerCredentialError(
                "credential decision reviewer IDs must be unique"
            )
        abstaining = any(item.abstention.triggered for item in self.credentials)
        expected = (
            CredentialDecisionOutcome.ABSTAIN
            if abstaining
            else CredentialDecisionOutcome.EXECUTE
        )
        if self.outcome is not expected:
            raise ReviewerCredentialError(
                "credential decision outcome must reflect abstention evidence"
            )

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "reviewer-credential-decision"
        )


@dataclass(frozen=True, slots=True)
class StoredReviewerCredentialEvidence:
    """Stored credential registry, policy, and exact attestation population."""

    corpus_ref: StoredArtifactRef
    reviewer_registry_ref: StoredArtifactRef
    credential_issuer_registry_ref: StoredArtifactRef
    reviewer_credential_policy_ref: StoredArtifactRef
    attestation_refs: tuple[StoredArtifactRef, ...]
    attestations: tuple[ReviewerCredentialAttestationSnapshot, ...]

    def __post_init__(self) -> None:
        if len(self.attestation_refs) != len(self.attestations):
            raise ReviewerCredentialError(
                "stored credential evidence requires one ref per attestation"
            )


def _load_attestation(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> ReviewerCredentialAttestationSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    attestation = ReviewerCredentialAttestationSnapshot.from_artifact(artifact)
    if attestation.reference() != reference:
        raise ArtifactIntegrityError(
            "stored credential attestation reference differs from corpus"
        )
    return attestation


def load_reviewer_credential_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CredentialBoundReviewCorpusSnapshot,
    reviewer_registry: ReviewerRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: ReviewerCredentialPolicySnapshot,
) -> StoredReviewerCredentialEvidence:
    """Load and reverify the credential-bound corpus and every attestation."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored credential-bound corpus differs from expected manifest"
        )
    reviewer_artifact = store.get(
        reviewer_registry.registry_id,
        expected_hash=reviewer_registry.artifact_hash,
    )
    if reviewer_artifact.payload != reviewer_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored reviewer registry differs from expected registry"
        )
    issuer_artifact = store.get(
        issuer_registry.registry_id,
        expected_hash=issuer_registry.artifact_hash,
    )
    if issuer_artifact.payload != issuer_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored credential issuer registry differs from expected registry"
        )
    policy_artifact = store.get(
        credential_policy.policy_id,
        expected_hash=credential_policy.artifact_hash,
    )
    if policy_artifact.payload != credential_policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored reviewer credential policy differs from expected policy"
        )
    attestations = tuple(
        _load_attestation(store, item.credential_attestation_ref)
        for item in corpus.credential_entries
    )
    return StoredReviewerCredentialEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        reviewer_registry_ref=store.reference(reviewer_registry.registry_id),
        credential_issuer_registry_ref=store.reference(
            issuer_registry.registry_id
        ),
        reviewer_credential_policy_ref=store.reference(
            credential_policy.policy_id
        ),
        attestation_refs=tuple(item.reference() for item in attestations),
        attestations=attestations,
    )


def validate_reviewer_credential_attestations(
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundReviewCorpusSnapshot,
    reviewer_registry: ReviewerRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: ReviewerCredentialPolicySnapshot,
    attestations: tuple[ReviewerCredentialAttestationSnapshot, ...],
    adjudications: tuple[ReviewAdjudicationSnapshot, ...],
    evaluated_at: str,
) -> ReviewerCredentialDecisionReport:
    """Evaluate credential provenance before review adjudication begins."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise ReviewerCredentialError(
            "only a frozen experiment plan may pass credential attestation"
        )
    if plan.corpus_ref != corpus.reference():
        raise ReviewerCredentialError(
            "experiment plan corpus_ref does not match credential-bound corpus"
        )
    if plan.content_ids != corpus.content_ids:
        raise ReviewerCredentialError(
            "experiment plan content order does not match credential-bound corpus"
        )
    if corpus.corpus.reviewer_registry_ref != reviewer_registry.reference():
        raise ReviewerCredentialError(
            "review corpus reviewer registry reference differs"
        )
    if corpus.credential_issuer_registry_ref != issuer_registry.reference():
        raise ReviewerCredentialError(
            "credential issuer registry reference differs"
        )
    if corpus.reviewer_credential_policy_ref != credential_policy.reference():
        raise ReviewerCredentialError(
            "reviewer credential policy reference differs"
        )
    if issuer_registry.status is not CredentialIssuerRegistryLifecycle.ACCEPTED:
        raise ReviewerCredentialError(
            "credential issuer registry must be accepted"
        )
    if credential_policy.status is not CredentialPolicyLifecycle.ACCEPTED:
        raise ReviewerCredentialError(
            "reviewer credential policy must be accepted"
        )
    if len(corpus.credential_entries) != len(reviewer_registry.reviewers):
        raise ReviewerCredentialError(
            "credential population must match reviewer registry"
        )
    if len(attestations) != len(corpus.credential_entries):
        raise ReviewerCredentialError(
            "credential attestation population differs from corpus"
        )

    failures: list[str] = []
    summaries: list[ReviewerCredentialSummary] = []
    attestation_by_reviewer: dict[str, ReviewerCredentialAttestationSnapshot] = {}
    for reviewer, entry, attestation in zip(
        reviewer_registry.reviewers,
        corpus.credential_entries,
        attestations,
        strict=True,
    ):
        if (entry.reviewer_id, entry.identity_revision) != (
            reviewer.reviewer_id,
            reviewer.identity_revision,
        ):
            failures.append(
                f"{reviewer.reviewer_id}: credential entry identity differs"
            )
            continue
        if attestation.reference() != entry.credential_attestation_ref:
            failures.append(
                f"{reviewer.reviewer_id}: credential attestation reference differs"
            )
            continue
        if (attestation.reviewer_id, attestation.identity_revision) != (
            reviewer.reviewer_id,
            reviewer.identity_revision,
        ):
            failures.append(
                f"{reviewer.reviewer_id}: attested identity revision differs"
            )
            continue
        if credential_policy.require_exact_role_match and (
            attestation.authorized_roles != reviewer.roles
        ):
            failures.append(
                f"{reviewer.reviewer_id}: attested roles differ from registry"
            )
            continue
        if attestation.credential_type != credential_policy.credential_type:
            failures.append(
                f"{reviewer.reviewer_id}: credential type differs from policy"
            )
            continue
        issuer = issuer_registry.issuer(attestation.issuer_id)
        if issuer is None:
            failures.append(
                f"{reviewer.reviewer_id}: attestation issuer is absent"
            )
            continue
        if issuer.issuer_revision != attestation.issuer_revision:
            failures.append(
                f"{reviewer.reviewer_id}: issuer revision differs"
            )
            continue
        if attestation.credential_type not in issuer.credential_types:
            failures.append(
                f"{reviewer.reviewer_id}: issuer may not issue credential type"
            )
            continue

        reasons: list[str] = []
        if not reviewer.active:
            reasons.append("reviewer-registry-inactive")
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
        summary = ReviewerCredentialSummary(
            reviewer_id=reviewer.reviewer_id,
            identity_revision=reviewer.identity_revision,
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
        summaries.append(summary)
        attestation_by_reviewer[reviewer.reviewer_id] = attestation

    for adjudication in adjudications:
        for observation in adjudication.observations:
            attestation = attestation_by_reviewer.get(observation.reviewer_id)
            if attestation is None:
                failures.append(
                    f"{adjudication.content_id}: reviewer credential absent"
                )
                continue
            if observation.reviewer_role not in attestation.authorized_roles:
                failures.append(
                    f"{adjudication.content_id}: observation role is not attested"
                )
        if adjudication.adjudicator_id is not None:
            attestation = attestation_by_reviewer.get(
                adjudication.adjudicator_id
            )
            if (
                attestation is None
                or ReviewerRole.ADJUDICATOR not in attestation.authorized_roles
            ):
                failures.append(
                    f"{adjudication.content_id}: adjudicator role is not attested"
                )
        for dissent in adjudication.dissent:
            if dissent.reviewer_id not in attestation_by_reviewer:
                failures.append(
                    f"{adjudication.content_id}: dissenting reviewer credential absent"
                )

    if failures:
        raise ReviewerCredentialError(
            "reviewer credential evidence failed: " + " | ".join(failures)
        )
    outcome = (
        CredentialDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in summaries)
        else CredentialDecisionOutcome.EXECUTE
    )
    return ReviewerCredentialDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        credential_corpus_ref=corpus.reference(),
        reviewer_registry_ref=reviewer_registry.reference(),
        credential_issuer_registry_ref=issuer_registry.reference(),
        reviewer_credential_policy_ref=credential_policy.reference(),
        outcome=outcome,
        credentials=tuple(summaries),
        evaluated_at=evaluated_at,
    )


def persist_credential_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundReviewCorpusSnapshot,
    predecessor_corpus: ReviewBoundExtractionCorpusSnapshot,
    reviewer_registry: ReviewerRegistrySnapshot,
    review_policy: ReviewAdjudicationPolicySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: ReviewerCredentialPolicySnapshot,
    attestations: tuple[ReviewerCredentialAttestationSnapshot, ...],
    adjudications: tuple[ReviewAdjudicationSnapshot, ...],
    evaluated_at: str,
) -> StoredReviewerCredentialEvidence:
    """Persist credential evidence and publish the new corpus manifest last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise ReviewerCredentialError(
            "predecessor corpus reference differs from credential-bound corpus"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise ReviewerCredentialError(
            "credential-bound corpus content population differs from predecessor"
        )
    if predecessor_corpus.reviewer_registry_ref != (
        corpus.corpus.reviewer_registry_ref
    ):
        raise ReviewerCredentialError(
            "credential-bound reviewer registry differs from predecessor"
        )
    if predecessor_corpus.review_policy_ref != corpus.corpus.review_policy_ref:
        raise ReviewerCredentialError(
            "credential-bound review policy differs from predecessor"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored predecessor review corpus differs from expected"
        )
    decision = validate_reviewer_credential_attestations(
        plan=plan,
        corpus=corpus,
        reviewer_registry=reviewer_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        attestations=attestations,
        adjudications=adjudications,
        evaluated_at=evaluated_at,
    )
    if decision.outcome is CredentialDecisionOutcome.ABSTAIN:
        raise ReviewerCredentialError(
            "credential-bound corpus publication requires currently eligible attestations"
        )
    if store.append(issuer_registry.artifact()).artifact_hash != (
        issuer_registry.artifact_hash
    ):
        raise ArtifactIntegrityError(
            "stored credential issuer registry reference differs"
        )
    if store.append(credential_policy.artifact()).artifact_hash != (
        credential_policy.artifact_hash
    ):
        raise ArtifactIntegrityError(
            "stored reviewer credential policy reference differs"
        )
    for attestation in attestations:
        if store.append(attestation.artifact()) != attestation.reference():
            raise ArtifactIntegrityError(
                "stored reviewer credential attestation reference differs"
            )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored credential-bound corpus reference differs"
        )
    return load_reviewer_credential_evidence(
        store,
        corpus=corpus,
        reviewer_registry=reviewer_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
    )
