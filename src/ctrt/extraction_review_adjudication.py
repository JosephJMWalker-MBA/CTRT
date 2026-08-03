"""Reviewer identity, contradiction, dissent, and adjudication contracts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
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
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
)
from ctrt.extraction_quality import (
    ExtractionQualityAssessmentSnapshot,
    ExtractionQualityPolicySnapshot,
    QualityBoundExtractionCorpusSnapshot,
    ReviewerFinding,
    validate_extraction_quality_evidence,
)
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes, serialize_artifact


class ReviewAdjudicationError(ValueError):
    """Raised when reviewer identity or adjudication evidence is invalid."""


class ReviewerRegistryLifecycle(StrEnum):
    """Governance state of one reviewer registry."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class ReviewPolicyLifecycle(StrEnum):
    """Governance state of one review-adjudication policy."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class ReviewerRole(StrEnum):
    """Roles permitted by the initial synthetic review workflow."""

    PRIMARY_REVIEWER = "primary_reviewer"
    SECONDARY_REVIEWER = "secondary_reviewer"
    ADJUDICATOR = "adjudicator"


class AdjudicationStatus(StrEnum):
    """Lifecycle state of contradictory reviewer observations."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class ReviewConflictKind(StrEnum):
    """Declared reason observations are treated as conflicting."""

    CONTRADICTORY_FINDINGS = "contradictory_findings"
    EVIDENCE_DISPUTE = "evidence_dispute"
    SCOPE_DISPUTE = "scope_dispute"


class ReviewDecisionOutcome(StrEnum):
    """Whether the review layer permits the quality gate to proceed."""

    EXECUTE = "execute"
    ABSTAIN = "abstain"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ReviewAdjudicationError(f"{field_name} must not be empty")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReviewAdjudicationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ReviewAdjudicationError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ReviewAdjudicationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ReviewAdjudicationError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewAdjudicationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReviewAdjudicationError(f"{field_name} must be an integer")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ReviewAdjudicationError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ReviewAdjudicationError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise ReviewAdjudicationError(
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
        raise ReviewAdjudicationError(
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
class ReviewerIdentityRecord:
    """One stable reviewer identity and its authorized roles."""

    reviewer_id: str
    identity_revision: str
    roles: tuple[ReviewerRole, ...]
    active: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.reviewer_id, "reviewer_id")
        _require_non_empty(self.identity_revision, "identity_revision")
        if not self.roles:
            raise ReviewAdjudicationError(
                "reviewer identity requires at least one role"
            )
        if len(self.roles) != len(set(self.roles)):
            raise ReviewAdjudicationError(
                "reviewer roles must not contain duplicates"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerIdentityRecord:
        _reject_unknown(
            document,
            {"reviewer_id", "identity_revision", "roles", "active"},
            "reviewer identity",
        )
        roles_value = document.get("roles")
        if not isinstance(roles_value, list):
            raise ReviewAdjudicationError("reviewer roles must be an array")
        return cls(
            reviewer_id=_string(document.get("reviewer_id"), "reviewer_id"),
            identity_revision=_string(
                document.get("identity_revision"),
                "identity_revision",
            ),
            roles=tuple(
                ReviewerRole(_string(item, "reviewer role"))
                for item in roles_value
            ),
            active=_boolean(document.get("active"), "active"),
        )


@dataclass(frozen=True, slots=True)
class ReviewerRegistrySnapshot:
    """Accepted reviewer identities used by one review corpus."""

    registry_id: str
    registry_version: str
    status: ReviewerRegistryLifecycle
    reviewers: tuple[ReviewerIdentityRecord, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.registry_id, "registry_id")
        _require_non_empty(self.registry_version, "registry_version")
        _parse_timestamp(self.created_at, "created_at")
        reviewer_ids = tuple(item.reviewer_id for item in self.reviewers)
        if not reviewer_ids:
            raise ReviewAdjudicationError(
                "reviewer registry requires reviewer identities"
            )
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ReviewAdjudicationError(
                "reviewer registry IDs must be unique"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ReviewAdjudicationError(
                "reviewer registry hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerRegistrySnapshot:
        _reject_unknown(
            document,
            {
                "registry_id",
                "registry_version",
                "status",
                "reviewers",
                "created_at",
            },
            "reviewer registry",
        )
        reviewers_value = document.get("reviewers")
        if not isinstance(reviewers_value, list):
            raise ReviewAdjudicationError("reviewers must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            registry_id=_string(document.get("registry_id"), "registry_id"),
            registry_version=_string(
                document.get("registry_version"),
                "registry_version",
            ),
            status=ReviewerRegistryLifecycle(
                _string(document.get("status"), "status")
            ),
            reviewers=tuple(
                ReviewerIdentityRecord.from_document(
                    _mapping(item, "reviewer identity")
                )
                for item in reviewers_value
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

    def reviewer(self, reviewer_id: str) -> ReviewerIdentityRecord | None:
        return next(
            (
                reviewer
                for reviewer in self.reviewers
                if reviewer.reviewer_id == reviewer_id
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class ReviewAdjudicationPolicySnapshot:
    """Frozen rules for reviewer identity, conflict, dissent, and abstention."""

    policy_id: str
    policy_version: str
    status: ReviewPolicyLifecycle
    minimum_distinct_reviewers: int
    required_roles: tuple[ReviewerRole, ...]
    adjudicator_role: ReviewerRole
    abstain_on_statuses: tuple[AdjudicationStatus, ...]
    preserve_dissent: bool
    majority_vote_forbidden: bool
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        _parse_timestamp(self.created_at, "created_at")
        if self.minimum_distinct_reviewers < 2:
            raise ReviewAdjudicationError(
                "review policy requires at least two distinct reviewers"
            )
        if not self.required_roles:
            raise ReviewAdjudicationError(
                "review policy requires explicit reviewer roles"
            )
        if len(self.required_roles) != len(set(self.required_roles)):
            raise ReviewAdjudicationError(
                "required reviewer roles must not contain duplicates"
            )
        if self.adjudicator_role is not ReviewerRole.ADJUDICATOR:
            raise ReviewAdjudicationError(
                "initial review policy requires the adjudicator role"
            )
        required_abstentions = {
            AdjudicationStatus.PENDING,
            AdjudicationStatus.UNRESOLVED,
        }
        if not required_abstentions.issubset(self.abstain_on_statuses):
            raise ReviewAdjudicationError(
                "review policy must abstain on pending and unresolved status"
            )
        if not self.preserve_dissent:
            raise ReviewAdjudicationError(
                "review policy must preserve dissent"
            )
        if not self.majority_vote_forbidden:
            raise ReviewAdjudicationError(
                "review policy must forbid majority-vote adjudication"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ReviewAdjudicationError(
                "review policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewAdjudicationPolicySnapshot:
        _reject_unknown(
            document,
            {
                "policy_id",
                "policy_version",
                "status",
                "minimum_distinct_reviewers",
                "required_roles",
                "adjudicator_role",
                "abstain_on_statuses",
                "preserve_dissent",
                "majority_vote_forbidden",
                "created_at",
            },
            "review policy",
        )
        roles_value = document.get("required_roles")
        statuses_value = document.get("abstain_on_statuses")
        if not isinstance(roles_value, list):
            raise ReviewAdjudicationError("required_roles must be an array")
        if not isinstance(statuses_value, list):
            raise ReviewAdjudicationError(
                "abstain_on_statuses must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=ReviewPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            minimum_distinct_reviewers=_integer(
                document.get("minimum_distinct_reviewers"),
                "minimum_distinct_reviewers",
            ),
            required_roles=tuple(
                ReviewerRole(_string(item, "required reviewer role"))
                for item in roles_value
            ),
            adjudicator_role=ReviewerRole(
                _string(document.get("adjudicator_role"), "adjudicator_role")
            ),
            abstain_on_statuses=tuple(
                AdjudicationStatus(_string(item, "abstain status"))
                for item in statuses_value
            ),
            preserve_dissent=_boolean(
                document.get("preserve_dissent"),
                "preserve_dissent",
            ),
            majority_vote_forbidden=_boolean(
                document.get("majority_vote_forbidden"),
                "majority_vote_forbidden",
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
class ReviewerObservationRecord:
    """One reviewer position with stable identity, role, question, and evidence."""

    observation_id: str
    reviewer_id: str
    reviewer_role: ReviewerRole
    review_question_id: str
    finding: ReviewerFinding
    notes: str
    evidence_refs: tuple[str, ...]
    observed_at: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.observation_id, "observation_id"),
            (self.reviewer_id, "reviewer_id"),
            (self.review_question_id, "review_question_id"),
            (self.notes, "notes"),
        ):
            _require_non_empty(value, name)
        _parse_timestamp(self.observed_at, "observed_at")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ReviewAdjudicationError(
                "review observation evidence_refs must be unique"
            )
        if any(not item.strip() for item in self.evidence_refs):
            raise ReviewAdjudicationError(
                "review observation evidence_refs must not be empty"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerObservationRecord:
        _reject_unknown(
            document,
            {
                "observation_id",
                "reviewer_id",
                "reviewer_role",
                "review_question_id",
                "finding",
                "notes",
                "evidence_refs",
                "observed_at",
            },
            "review observation",
        )
        return cls(
            observation_id=_string(
                document.get("observation_id"),
                "observation_id",
            ),
            reviewer_id=_string(document.get("reviewer_id"), "reviewer_id"),
            reviewer_role=ReviewerRole(
                _string(document.get("reviewer_role"), "reviewer_role")
            ),
            review_question_id=_string(
                document.get("review_question_id"),
                "review_question_id",
            ),
            finding=ReviewerFinding(
                _string(document.get("finding"), "finding")
            ),
            notes=_string(document.get("notes"), "notes"),
            evidence_refs=_string_tuple(
                document.get("evidence_refs"),
                "evidence_refs",
            ),
            observed_at=_string(document.get("observed_at"), "observed_at"),
        )


@dataclass(frozen=True, slots=True)
class ReviewConflictRecord:
    """One explicitly declared conflict among reviewer observations."""

    conflict_id: str
    kind: ReviewConflictKind
    observation_ids: tuple[str, ...]
    description: str

    def __post_init__(self) -> None:
        _require_non_empty(self.conflict_id, "conflict_id")
        _require_non_empty(self.description, "description")
        if len(self.observation_ids) < 2:
            raise ReviewAdjudicationError(
                "review conflict requires at least two observations"
            )
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ReviewAdjudicationError(
                "review conflict observation IDs must be unique"
            )
        if any(not item.strip() for item in self.observation_ids):
            raise ReviewAdjudicationError(
                "review conflict observation IDs must not be empty"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewConflictRecord:
        _reject_unknown(
            document,
            {"conflict_id", "kind", "observation_ids", "description"},
            "review conflict",
        )
        return cls(
            conflict_id=_string(document.get("conflict_id"), "conflict_id"),
            kind=ReviewConflictKind(
                _string(document.get("kind"), "kind")
            ),
            observation_ids=_string_tuple(
                document.get("observation_ids"),
                "observation_ids",
            ),
            description=_string(
                document.get("description"),
                "description",
            ),
        )


@dataclass(frozen=True, slots=True)
class PreservedDissent:
    """A dissenting position retained after or during adjudication."""

    dissent_id: str
    reviewer_id: str
    observation_ids: tuple[str, ...]
    position: str
    rationale: str
    preserved: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.dissent_id, "dissent_id"),
            (self.reviewer_id, "reviewer_id"),
            (self.position, "position"),
            (self.rationale, "rationale"),
        ):
            _require_non_empty(value, name)
        if not self.observation_ids:
            raise ReviewAdjudicationError(
                "preserved dissent requires observation IDs"
            )
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ReviewAdjudicationError(
                "dissent observation IDs must be unique"
            )
        if not self.preserved:
            raise ReviewAdjudicationError(
                "dissent records must remain explicitly preserved"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> PreservedDissent:
        _reject_unknown(
            document,
            {
                "dissent_id",
                "reviewer_id",
                "observation_ids",
                "position",
                "rationale",
                "preserved",
            },
            "preserved dissent",
        )
        return cls(
            dissent_id=_string(document.get("dissent_id"), "dissent_id"),
            reviewer_id=_string(document.get("reviewer_id"), "reviewer_id"),
            observation_ids=_string_tuple(
                document.get("observation_ids"),
                "observation_ids",
            ),
            position=_string(document.get("position"), "position"),
            rationale=_string(document.get("rationale"), "rationale"),
            preserved=_boolean(document.get("preserved"), "preserved"),
        )


@dataclass(frozen=True, slots=True)
class ReviewAdjudicationSnapshot:
    """Reviewer observations, conflicts, dissent, and adjudication state."""

    artifact_id: str
    adjudication_id: str
    content_id: str
    quality_assessment_ref: StoredArtifactRef
    reviewer_registry_ref: VersionedArtifactRef
    review_policy_ref: VersionedArtifactRef
    observations: tuple[ReviewerObservationRecord, ...]
    conflicts: tuple[ReviewConflictRecord, ...]
    adjudication_status: AdjudicationStatus
    adjudicator_id: str | None
    resolution_notes: str | None
    dissent: tuple[PreservedDissent, ...]
    unresolved_conflict_ids: tuple[str, ...]
    abstention: SystemAbstention
    adjudicated_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.adjudication_id, "adjudication_id")
        _require_non_empty(self.content_id, "content_id")
        _parse_timestamp(self.adjudicated_at, "adjudicated_at")
        if self.artifact_id != f"review-adjudication:{self.adjudication_id}":
            raise ReviewAdjudicationError(
                "review artifact ID must derive from adjudication_id"
            )
        if not self.observations:
            raise ReviewAdjudicationError(
                "review adjudication requires observations"
            )
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ReviewAdjudicationError(
                "review observation IDs must be unique"
            )
        conflict_ids = tuple(item.conflict_id for item in self.conflicts)
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ReviewAdjudicationError("review conflict IDs must be unique")
        dissent_ids = tuple(item.dissent_id for item in self.dissent)
        if len(dissent_ids) != len(set(dissent_ids)):
            raise ReviewAdjudicationError("dissent IDs must be unique")
        if len(self.unresolved_conflict_ids) != len(
            set(self.unresolved_conflict_ids)
        ):
            raise ReviewAdjudicationError(
                "unresolved conflict IDs must be unique"
            )
        observation_id_set = set(observation_ids)
        observation_by_id = {
            item.observation_id: item for item in self.observations
        }
        for conflict in self.conflicts:
            if not set(conflict.observation_ids).issubset(observation_id_set):
                raise ReviewAdjudicationError(
                    "review conflict references unknown observations"
                )
            conflict_observations = tuple(
                observation_by_id[item] for item in conflict.observation_ids
            )
            questions = {
                item.review_question_id for item in conflict_observations
            }
            if len(questions) != 1:
                raise ReviewAdjudicationError(
                    "conflict observations must address one review question"
                )
            if len({item.finding for item in conflict_observations}) < 2:
                raise ReviewAdjudicationError(
                    "declared conflict must preserve differing findings"
                )
        if not set(self.unresolved_conflict_ids).issubset(set(conflict_ids)):
            raise ReviewAdjudicationError(
                "unresolved conflict IDs must reference declared conflicts"
            )
        for item in self.dissent:
            if not set(item.observation_ids).issubset(observation_id_set):
                raise ReviewAdjudicationError(
                    "dissent references unknown observations"
                )
            reviewer_observation_ids = {
                observation.observation_id
                for observation in self.observations
                if observation.reviewer_id == item.reviewer_id
            }
            if not set(item.observation_ids).issubset(
                reviewer_observation_ids
            ):
                raise ReviewAdjudicationError(
                    "dissent observations must belong to dissenting reviewer"
                )

        if self.adjudication_status is AdjudicationStatus.NOT_REQUIRED:
            if (
                self.conflicts
                or self.unresolved_conflict_ids
                or self.adjudicator_id is not None
                or self.resolution_notes is not None
                or self.dissent
                or self.abstention.triggered
            ):
                raise ReviewAdjudicationError(
                    "not-required adjudication may not contain conflict state"
                )
        elif self.adjudication_status is AdjudicationStatus.RESOLVED:
            if not self.conflicts:
                raise ReviewAdjudicationError(
                    "resolved adjudication requires declared conflicts"
                )
            if self.unresolved_conflict_ids:
                raise ReviewAdjudicationError(
                    "resolved adjudication may not retain unresolved conflicts"
                )
            if self.adjudicator_id is None or self.resolution_notes is None:
                raise ReviewAdjudicationError(
                    "resolved adjudication requires adjudicator and resolution"
                )
            if self.abstention.triggered:
                raise ReviewAdjudicationError(
                    "resolved adjudication may not trigger review abstention"
                )
        else:
            if not self.conflicts or not self.unresolved_conflict_ids:
                raise ReviewAdjudicationError(
                    "pending or unresolved adjudication requires unresolved conflicts"
                )
            if not self.abstention.triggered:
                raise ReviewAdjudicationError(
                    "pending or unresolved adjudication must abstain"
                )
            required_reason = (
                f"review-status:{self.adjudication_status.value}"
            )
            if required_reason not in self.abstention.reasons:
                raise ReviewAdjudicationError(
                    "review abstention must preserve adjudication status reason"
                )

        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ReviewAdjudicationError(
                "review adjudication hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewAdjudicationSnapshot:
        _reject_unknown(
            document,
            {
                "artifact_id",
                "adjudication_id",
                "content_id",
                "quality_assessment_ref",
                "reviewer_registry_ref",
                "review_policy_ref",
                "observations",
                "conflicts",
                "adjudication_status",
                "adjudicator_id",
                "resolution_notes",
                "dissent",
                "unresolved_conflict_ids",
                "abstention",
                "adjudicated_at",
            },
            "review adjudication",
        )
        observations_value = document.get("observations")
        conflicts_value = document.get("conflicts")
        dissent_value = document.get("dissent")
        if not isinstance(observations_value, list):
            raise ReviewAdjudicationError("observations must be an array")
        if not isinstance(conflicts_value, list):
            raise ReviewAdjudicationError("conflicts must be an array")
        if not isinstance(dissent_value, list):
            raise ReviewAdjudicationError("dissent must be an array")
        abstention_document = _mapping(
            document.get("abstention"),
            "abstention",
        )
        _reject_unknown(
            abstention_document,
            {"triggered", "reasons"},
            "abstention",
        )
        triggered = abstention_document.get("triggered")
        if not isinstance(triggered, bool):
            raise ReviewAdjudicationError(
                "abstention.triggered must be a boolean"
            )
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            adjudication_id=_string(
                document.get("adjudication_id"),
                "adjudication_id",
            ),
            content_id=_string(document.get("content_id"), "content_id"),
            quality_assessment_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("quality_assessment_ref"),
                    "quality_assessment_ref",
                )
            ),
            reviewer_registry_ref=_versioned_ref(
                document.get("reviewer_registry_ref"),
                "reviewer_registry_ref",
            ),
            review_policy_ref=_versioned_ref(
                document.get("review_policy_ref"),
                "review_policy_ref",
            ),
            observations=tuple(
                ReviewerObservationRecord.from_document(
                    _mapping(item, "review observation")
                )
                for item in observations_value
            ),
            conflicts=tuple(
                ReviewConflictRecord.from_document(
                    _mapping(item, "review conflict")
                )
                for item in conflicts_value
            ),
            adjudication_status=AdjudicationStatus(
                _string(
                    document.get("adjudication_status"),
                    "adjudication_status",
                )
            ),
            adjudicator_id=_optional_string(
                document.get("adjudicator_id"),
                "adjudicator_id",
            ),
            resolution_notes=_optional_string(
                document.get("resolution_notes"),
                "resolution_notes",
            ),
            dissent=tuple(
                PreservedDissent.from_document(
                    _mapping(item, "preserved dissent")
                )
                for item in dissent_value
            ),
            unresolved_conflict_ids=_string_tuple(
                document.get("unresolved_conflict_ids"),
                "unresolved_conflict_ids",
            ),
            abstention=SystemAbstention(
                triggered=triggered,
                reasons=_string_tuple(
                    abstention_document.get("reasons"),
                    "abstention.reasons",
                ),
            ),
            adjudicated_at=_string(
                document.get("adjudicated_at"),
                "adjudicated_at",
            ),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> ReviewAdjudicationSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReviewAdjudicationError(
                "review adjudication artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "review adjudication"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise ReviewAdjudicationError(
                "stored review adjudication ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise ReviewAdjudicationError(
                "stored review adjudication hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise ReviewAdjudicationError(
                "stored review adjudication is not canonical"
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
class ReviewEvidenceEntry:
    """One ordered adjudication reference in a frozen corpus."""

    content_id: str
    review_adjudication_ref: StoredArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewEvidenceEntry:
        return cls(
            content_id=_string(document.get("content_id"), "content_id"),
            review_adjudication_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("review_adjudication_ref"),
                    "review_adjudication_ref",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ReviewBoundExtractionCorpusSnapshot:
    """Quality-bound corpus plus reviewer registry, policy, and adjudication refs."""

    corpus: QualityBoundExtractionCorpusSnapshot
    reviewer_registry_ref: VersionedArtifactRef
    review_policy_ref: VersionedArtifactRef
    review_entries: tuple[ReviewEvidenceEntry, ...]

    def __post_init__(self) -> None:
        if tuple(item.content_id for item in self.review_entries) != self.content_ids:
            raise ReviewAdjudicationError(
                "review evidence order must match corpus content IDs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewBoundExtractionCorpusSnapshot:
        contents_value = document.get("contents")
        if not isinstance(contents_value, list):
            raise ReviewAdjudicationError("contents must be an array")
        return cls(
            corpus=QualityBoundExtractionCorpusSnapshot.from_document(document),
            reviewer_registry_ref=_versioned_ref(
                document.get("reviewer_registry_ref"),
                "reviewer_registry_ref",
            ),
            review_policy_ref=_versioned_ref(
                document.get("review_adjudication_policy_ref"),
                "review_adjudication_policy_ref",
            ),
            review_entries=tuple(
                ReviewEvidenceEntry.from_document(
                    _mapping(item, "review corpus entry")
                )
                for item in contents_value
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
class ReviewAdjudicationSummary:
    """Decision-facing summary preserving identity, conflict, and dissent."""

    content_id: str
    adjudication_status: AdjudicationStatus
    reviewer_ids: tuple[str, ...]
    reviewer_roles: tuple[ReviewerRole, ...]
    conflict_ids: tuple[str, ...]
    unresolved_conflict_ids: tuple[str, ...]
    dissent_ids: tuple[str, ...]
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class ReviewAdjudicationDecisionReport:
    """Canonical review decision without vote totals or majority scoring."""

    experiment_id: str
    experiment_version: str
    review_corpus_ref: VersionedArtifactRef
    reviewer_registry_ref: VersionedArtifactRef
    review_policy_ref: VersionedArtifactRef
    outcome: ReviewDecisionOutcome
    adjudications: tuple[ReviewAdjudicationSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if not self.adjudications:
            raise ReviewAdjudicationError(
                "review decision requires adjudications"
            )
        content_ids = tuple(item.content_id for item in self.adjudications)
        if len(content_ids) != len(set(content_ids)):
            raise ReviewAdjudicationError(
                "review decision content IDs must be unique"
            )
        abstaining = any(
            item.abstention.triggered for item in self.adjudications
        )
        expected = (
            ReviewDecisionOutcome.ABSTAIN
            if abstaining
            else ReviewDecisionOutcome.EXECUTE
        )
        if self.outcome is not expected:
            raise ReviewAdjudicationError(
                "review decision outcome must follow explicit abstention"
            )

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "review-adjudication-decision"
        )

    def artifact(self) -> CanonicalArtifact:
        return serialize_artifact(self.artifact_id, self)


@dataclass(frozen=True, slots=True)
class StoredReviewAdjudicationEvidence:
    """Verified reviewer registry, policy, and adjudication records."""

    corpus_ref: StoredArtifactRef
    reviewer_registry_ref: StoredArtifactRef
    review_policy_ref: StoredArtifactRef
    adjudication_refs: tuple[StoredArtifactRef, ...]
    adjudications: tuple[ReviewAdjudicationSnapshot, ...]

    def __post_init__(self) -> None:
        if not self.adjudications or len(self.adjudication_refs) != len(
            self.adjudications
        ):
            raise ValueError(
                "stored review evidence requires one reference per adjudication"
            )


def _load_adjudication(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> ReviewAdjudicationSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    adjudication = ReviewAdjudicationSnapshot.from_artifact(artifact)
    if adjudication.reference() != reference:
        raise ArtifactIntegrityError(
            "stored review adjudication reference differs from corpus"
        )
    return adjudication


def load_review_adjudication_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: ReviewBoundExtractionCorpusSnapshot,
    reviewer_registry: ReviewerRegistrySnapshot,
    review_policy: ReviewAdjudicationPolicySnapshot,
) -> StoredReviewAdjudicationEvidence:
    """Load and reverify reviewer registry, policy, and adjudications."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored review-bound corpus differs from expected manifest"
        )
    registry_artifact = store.get(
        reviewer_registry.registry_id,
        expected_hash=reviewer_registry.artifact_hash,
    )
    if registry_artifact.payload != reviewer_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored reviewer registry differs from expected registry"
        )
    policy_artifact = store.get(
        review_policy.policy_id,
        expected_hash=review_policy.artifact_hash,
    )
    if policy_artifact.payload != review_policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored review policy differs from expected policy"
        )
    adjudications = tuple(
        _load_adjudication(store, entry.review_adjudication_ref)
        for entry in corpus.review_entries
    )
    return StoredReviewAdjudicationEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        reviewer_registry_ref=store.reference(reviewer_registry.registry_id),
        review_policy_ref=store.reference(review_policy.policy_id),
        adjudication_refs=tuple(item.reference() for item in adjudications),
        adjudications=adjudications,
    )


def _validate_declared_conflicts(
    adjudication: ReviewAdjudicationSnapshot,
) -> tuple[str, ...]:
    observations_by_question: dict[str, list[ReviewerObservationRecord]] = (
        defaultdict(list)
    )
    for observation in adjudication.observations:
        observations_by_question[observation.review_question_id].append(
            observation
        )
    failures: list[str] = []
    for question_id, observations in observations_by_question.items():
        if len({item.finding for item in observations}) < 2:
            continue
        observation_ids = {item.observation_id for item in observations}
        represented = any(
            observation_ids.issubset(set(conflict.observation_ids))
            for conflict in adjudication.conflicts
        )
        if not represented:
            failures.append(
                f"contradictory question {question_id!r} lacks conflict record"
            )
    return tuple(failures)


def validate_review_adjudication_evidence(
    *,
    plan: ExperimentPlan,
    corpus: ReviewBoundExtractionCorpusSnapshot,
    reviewer_registry: ReviewerRegistrySnapshot,
    review_policy: ReviewAdjudicationPolicySnapshot,
    adjudications: tuple[ReviewAdjudicationSnapshot, ...],
    evaluated_at: str,
) -> ReviewAdjudicationDecisionReport:
    """Evaluate reviewer identity, contradiction, dissent, and adjudication."""

    _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise ReviewAdjudicationError(
            "only a frozen experiment plan may pass review adjudication"
        )
    if plan.corpus_ref != corpus.reference():
        raise ReviewAdjudicationError(
            "experiment plan corpus_ref does not match review-bound corpus"
        )
    if plan.content_ids != corpus.content_ids:
        raise ReviewAdjudicationError(
            "experiment plan content order does not match review-bound corpus"
        )
    if corpus.reviewer_registry_ref != reviewer_registry.reference():
        raise ReviewAdjudicationError(
            "review corpus reviewer registry reference differs"
        )
    if corpus.review_policy_ref != review_policy.reference():
        raise ReviewAdjudicationError(
            "review corpus adjudication policy reference differs"
        )
    if reviewer_registry.status is not ReviewerRegistryLifecycle.ACCEPTED:
        raise ReviewAdjudicationError(
            "reviewer registry must be accepted before execution"
        )
    if review_policy.status is not ReviewPolicyLifecycle.ACCEPTED:
        raise ReviewAdjudicationError(
            "review adjudication policy must be accepted before execution"
        )
    if len(adjudications) != len(corpus.review_entries):
        raise ReviewAdjudicationError(
            "review adjudication population does not match frozen corpus"
        )

    failures: list[str] = []
    summaries: list[ReviewAdjudicationSummary] = []
    for quality_entry, review_entry, adjudication in zip(
        corpus.corpus.quality_entries,
        corpus.review_entries,
        adjudications,
        strict=True,
    ):
        content_id = quality_entry.content_id
        if adjudication.reference() != review_entry.review_adjudication_ref:
            failures.append(
                f"{content_id}: review adjudication reference differs"
            )
            continue
        if adjudication.content_id != content_id:
            failures.append(
                f"{content_id}: adjudication content ID differs"
            )
            continue
        if adjudication.quality_assessment_ref != (
            quality_entry.quality_assessment_ref
        ):
            failures.append(
                f"{content_id}: quality assessment reference differs"
            )
            continue
        if adjudication.reviewer_registry_ref != reviewer_registry.reference():
            failures.append(
                f"{content_id}: reviewer registry reference differs"
            )
            continue
        if adjudication.review_policy_ref != review_policy.reference():
            failures.append(
                f"{content_id}: review policy reference differs"
            )
            continue

        observed_reviewer_ids: list[str] = []
        observed_roles: list[ReviewerRole] = []
        for observation in adjudication.observations:
            reviewer = reviewer_registry.reviewer(observation.reviewer_id)
            if reviewer is None:
                failures.append(
                    f"{content_id}: reviewer {observation.reviewer_id!r} absent"
                )
                continue
            if not reviewer.active:
                failures.append(
                    f"{content_id}: reviewer {observation.reviewer_id!r} inactive"
                )
            if observation.reviewer_role not in reviewer.roles:
                failures.append(
                    f"{content_id}: reviewer role is not registry-authorized"
                )
            observed_reviewer_ids.append(observation.reviewer_id)
            observed_roles.append(observation.reviewer_role)

        distinct_reviewers = tuple(dict.fromkeys(observed_reviewer_ids))
        distinct_roles = tuple(dict.fromkeys(observed_roles))
        if len(distinct_reviewers) < review_policy.minimum_distinct_reviewers:
            failures.append(
                f"{content_id}: minimum distinct reviewers not met"
            )
        if not set(review_policy.required_roles).issubset(distinct_roles):
            failures.append(
                f"{content_id}: required reviewer roles not present"
            )
        failures.extend(
            f"{content_id}: {item}"
            for item in _validate_declared_conflicts(adjudication)
        )

        if adjudication.adjudicator_id is not None:
            adjudicator = reviewer_registry.reviewer(
                adjudication.adjudicator_id
            )
            if adjudicator is None or not adjudicator.active:
                failures.append(
                    f"{content_id}: adjudicator is absent or inactive"
                )
            elif review_policy.adjudicator_role not in adjudicator.roles:
                failures.append(
                    f"{content_id}: adjudicator lacks authorized role"
                )
        if adjudication.adjudication_status is AdjudicationStatus.RESOLVED:
            if adjudication.adjudicator_id is None:
                failures.append(
                    f"{content_id}: resolved conflict lacks adjudicator"
                )
            if not review_policy.preserve_dissent and adjudication.dissent:
                failures.append(
                    f"{content_id}: policy does not preserve recorded dissent"
                )
        if adjudication.adjudication_status in (
            review_policy.abstain_on_statuses
        ):
            required_reason = (
                f"review-status:{adjudication.adjudication_status.value}"
            )
            if not adjudication.abstention.triggered:
                failures.append(
                    f"{content_id}: policy-required review abstention missing"
                )
            elif required_reason not in adjudication.abstention.reasons:
                failures.append(
                    f"{content_id}: review status abstention reason missing"
                )

        summaries.append(
            ReviewAdjudicationSummary(
                content_id=content_id,
                adjudication_status=adjudication.adjudication_status,
                reviewer_ids=distinct_reviewers,
                reviewer_roles=distinct_roles,
                conflict_ids=tuple(
                    item.conflict_id for item in adjudication.conflicts
                ),
                unresolved_conflict_ids=(
                    adjudication.unresolved_conflict_ids
                ),
                dissent_ids=tuple(item.dissent_id for item in adjudication.dissent),
                abstention=adjudication.abstention,
            )
        )

    if failures:
        raise ReviewAdjudicationError(
            "review adjudication evidence failed: " + " | ".join(failures)
        )

    outcome = (
        ReviewDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in summaries)
        else ReviewDecisionOutcome.EXECUTE
    )
    return ReviewAdjudicationDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        review_corpus_ref=corpus.reference(),
        reviewer_registry_ref=reviewer_registry.reference(),
        review_policy_ref=review_policy.reference(),
        outcome=outcome,
        adjudications=tuple(summaries),
        evaluated_at=evaluated_at,
    )


def persist_review_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: ReviewBoundExtractionCorpusSnapshot,
    quality_policy: ExtractionQualityPolicySnapshot,
    reviewer_registry: ReviewerRegistrySnapshot,
    review_policy: ReviewAdjudicationPolicySnapshot,
    sources: tuple[SourceArtifactSnapshot, ...],
    extractions: tuple[ExtractionManifestSnapshot, ...],
    contents: tuple[ExtractedContentSnapshot, ...],
    assessments: tuple[ExtractionQualityAssessmentSnapshot, ...],
    adjudications: tuple[ReviewAdjudicationSnapshot, ...],
    evaluated_at: str,
) -> StoredReviewAdjudicationEvidence:
    """Persist all evidence members before publishing the review corpus last."""

    validate_extraction_quality_evidence(
        plan=plan,
        corpus=corpus.corpus,
        policy=quality_policy,
        assessments=assessments,
        evaluated_at=evaluated_at,
    )
    validate_review_adjudication_evidence(
        plan=plan,
        corpus=corpus,
        reviewer_registry=reviewer_registry,
        review_policy=review_policy,
        adjudications=adjudications,
        evaluated_at=evaluated_at,
    )
    base_entries = corpus.corpus.corpus.corpus.contents
    if not (
        len(sources)
        == len(extractions)
        == len(contents)
        == len(assessments)
        == len(adjudications)
        == len(base_entries)
    ):
        raise ReviewAdjudicationError(
            "source, extraction, quality, review, and corpus populations must match"
        )
    for (
        base_entry,
        quality_entry,
        review_entry,
        source,
        extraction,
        content,
        assessment,
        adjudication,
    ) in zip(
        base_entries,
        corpus.corpus.quality_entries,
        corpus.review_entries,
        sources,
        extractions,
        contents,
        assessments,
        adjudications,
        strict=True,
    ):
        base_entry.verify(source, extraction, content)
        if assessment.reference() != quality_entry.quality_assessment_ref:
            raise ReviewAdjudicationError(
                "quality assessment reference differs from corpus"
            )
        if adjudication.reference() != review_entry.review_adjudication_ref:
            raise ReviewAdjudicationError(
                "review adjudication reference differs from corpus"
            )
        if adjudication.quality_assessment_ref != assessment.reference():
            raise ReviewAdjudicationError(
                "review adjudication quality assessment reference differs"
            )
        for artifact, reference, label in (
            (source.artifact(), source.reference(), "source"),
            (content.artifact(), content.reference(), "content"),
            (extraction.artifact(), extraction.reference(), "extraction"),
            (assessment.artifact(), assessment.reference(), "quality assessment"),
            (adjudication.artifact(), adjudication.reference(), "review adjudication"),
        ):
            if store.append(artifact) != reference:
                raise ArtifactIntegrityError(
                    f"stored {label} reference differs"
                )
    if store.append(quality_policy.artifact()).artifact_hash != (
        quality_policy.artifact_hash
    ):
        raise ArtifactIntegrityError("stored quality policy reference differs")
    if store.append(reviewer_registry.artifact()).artifact_hash != (
        reviewer_registry.artifact_hash
    ):
        raise ArtifactIntegrityError("stored reviewer registry reference differs")
    if store.append(review_policy.artifact()).artifact_hash != (
        review_policy.artifact_hash
    ):
        raise ArtifactIntegrityError("stored review policy reference differs")
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError("stored review corpus reference differs")
    return load_review_adjudication_evidence(
        store,
        corpus=corpus,
        reviewer_registry=reviewer_registry,
        review_policy=review_policy,
    )
