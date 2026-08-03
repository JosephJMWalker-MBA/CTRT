"""Independent extraction-quality evidence and abstention contracts."""

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
from ctrt.confidence import ExtractionQualityStatus, SystemAbstention
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
)
from ctrt.extraction_method_eligibility import MethodBoundExtractionCorpusSnapshot
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes, serialize_artifact


class ExtractionQualityEvidenceError(ValueError):
    """Raised when extraction-quality evidence or policy binding is invalid."""


class ExtractionQualityPolicyLifecycle(StrEnum):
    """Governance state of one extraction-quality policy artifact."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class AutomatedCheckOutcome(StrEnum):
    """Outcome of one deterministic extraction-quality check."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ReviewerFinding(StrEnum):
    """Reviewer observation without forcing a binary quality verdict."""

    CONFIRMED = "confirmed"
    ISSUE = "issue"
    UNCERTAIN = "uncertain"


class QualityDecisionOutcome(StrEnum):
    """Whether governed analyzer execution may proceed."""

    EXECUTE = "execute"
    ABSTAIN = "abstain"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ExtractionQualityEvidenceError(f"{field_name} must not be empty")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExtractionQualityEvidenceError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ExtractionQualityEvidenceError(f"{field_name} must include a timezone")
    return parsed


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExtractionQualityEvidenceError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ExtractionQualityEvidenceError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtractionQualityEvidenceError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExtractionQualityEvidenceError(f"{field_name} must be an integer")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ExtractionQualityEvidenceError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise ExtractionQualityEvidenceError(
            f"{field_name} must not contain duplicates"
        )
    return result


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
class RequiredQualityCheck:
    """One exact automated check required by a quality policy."""

    check_id: str
    check_revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.check_id, "check_id")
        _require_non_empty(self.check_revision, "check_revision")

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> RequiredQualityCheck:
        return cls(
            check_id=_string(document.get("check_id"), "check_id"),
            check_revision=_string(
                document.get("check_revision"),
                "check_revision",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExtractionQualityPolicySnapshot:
    """Frozen requirements for extraction-quality evidence and abstention."""

    policy_id: str
    policy_version: str
    status: ExtractionQualityPolicyLifecycle
    required_checks: tuple[RequiredQualityCheck, ...]
    minimum_reviewer_observations: int
    abstain_on_statuses: tuple[ExtractionQualityStatus, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.policy_id, "policy_id")
        _require_non_empty(self.policy_version, "policy_version")
        _parse_timestamp(self.created_at, "created_at")
        if not self.required_checks:
            raise ExtractionQualityEvidenceError(
                "quality policy requires at least one automated check"
            )
        check_ids = tuple(item.check_id for item in self.required_checks)
        if len(check_ids) != len(set(check_ids)):
            raise ExtractionQualityEvidenceError(
                "quality policy check IDs must be unique"
            )
        if self.minimum_reviewer_observations < 0:
            raise ExtractionQualityEvidenceError(
                "minimum_reviewer_observations must be non-negative"
            )
        if len(self.abstain_on_statuses) != len(set(self.abstain_on_statuses)):
            raise ExtractionQualityEvidenceError(
                "abstain_on_statuses must not contain duplicates"
            )
        if ExtractionQualityStatus.FAILED not in self.abstain_on_statuses:
            raise ExtractionQualityEvidenceError(
                "quality policy must abstain on failed extraction quality"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ExtractionQualityEvidenceError(
                "quality policy hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractionQualityPolicySnapshot:
        checks_value = document.get("required_checks")
        if not isinstance(checks_value, list):
            raise ExtractionQualityEvidenceError(
                "required_checks must be an array"
            )
        statuses_value = document.get("abstain_on_statuses")
        if not isinstance(statuses_value, list):
            raise ExtractionQualityEvidenceError(
                "abstain_on_statuses must be an array"
            )
        payload = canonical_json_bytes(document)
        return cls(
            policy_id=_string(document.get("policy_id"), "policy_id"),
            policy_version=_string(
                document.get("policy_version"),
                "policy_version",
            ),
            status=ExtractionQualityPolicyLifecycle(
                _string(document.get("status"), "status")
            ),
            required_checks=tuple(
                RequiredQualityCheck.from_document(
                    _mapping(item, "required check")
                )
                for item in checks_value
            ),
            minimum_reviewer_observations=_integer(
                document.get("minimum_reviewer_observations"),
                "minimum_reviewer_observations",
            ),
            abstain_on_statuses=tuple(
                ExtractionQualityStatus(
                    _string(item, "abstain_on_statuses item")
                )
                for item in statuses_value
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
class AutomatedQualityCheck:
    """One inspectable automated extraction-quality check result."""

    check_id: str
    check_revision: str
    outcome: AutomatedCheckOutcome
    details: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.check_id, "check_id")
        _require_non_empty(self.check_revision, "check_revision")
        _require_non_empty(self.details, "details")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ExtractionQualityEvidenceError(
                "automated check evidence_refs must be unique"
            )
        if any(not item.strip() for item in self.evidence_refs):
            raise ExtractionQualityEvidenceError(
                "automated check evidence_refs must not be empty"
            )
        if self.outcome is AutomatedCheckOutcome.FAILED and not self.evidence_refs:
            raise ExtractionQualityEvidenceError(
                "failed automated check requires evidence references"
            )

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> AutomatedQualityCheck:
        return cls(
            check_id=_string(document.get("check_id"), "check_id"),
            check_revision=_string(
                document.get("check_revision"),
                "check_revision",
            ),
            outcome=AutomatedCheckOutcome(
                _string(document.get("outcome"), "outcome")
            ),
            details=_string(document.get("details"), "details"),
            evidence_refs=_string_tuple(
                document.get("evidence_refs"),
                "evidence_refs",
            ),
        )


@dataclass(frozen=True, slots=True)
class ReviewerQualityObservation:
    """One reviewer observation preserved separately from automated checks."""

    observation_id: str
    reviewer_role: str
    finding: ReviewerFinding
    notes: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.observation_id, "observation_id")
        _require_non_empty(self.reviewer_role, "reviewer_role")
        _require_non_empty(self.notes, "notes")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ExtractionQualityEvidenceError(
                "reviewer evidence_refs must be unique"
            )
        if any(not item.strip() for item in self.evidence_refs):
            raise ExtractionQualityEvidenceError(
                "reviewer evidence_refs must not be empty"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ReviewerQualityObservation:
        return cls(
            observation_id=_string(
                document.get("observation_id"),
                "observation_id",
            ),
            reviewer_role=_string(
                document.get("reviewer_role"),
                "reviewer_role",
            ),
            finding=ReviewerFinding(
                _string(document.get("finding"), "finding")
            ),
            notes=_string(document.get("notes"), "notes"),
            evidence_refs=_string_tuple(
                document.get("evidence_refs"),
                "evidence_refs",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExtractionUncertainty:
    """One unresolved uncertainty retained in the quality record."""

    uncertainty_id: str
    description: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.uncertainty_id, "uncertainty_id")
        _require_non_empty(self.description, "description")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ExtractionQualityEvidenceError(
                "uncertainty evidence_refs must be unique"
            )
        if any(not item.strip() for item in self.evidence_refs):
            raise ExtractionQualityEvidenceError(
                "uncertainty evidence_refs must not be empty"
            )

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> ExtractionUncertainty:
        return cls(
            uncertainty_id=_string(
                document.get("uncertainty_id"),
                "uncertainty_id",
            ),
            description=_string(document.get("description"), "description"),
            evidence_refs=_string_tuple(
                document.get("evidence_refs"),
                "evidence_refs",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExtractionQualityAssessmentSnapshot:
    """Independent evidence about one extraction's completeness and fidelity."""

    artifact_id: str
    assessment_id: str
    content_id: str
    source_artifact_ref: StoredArtifactRef
    extraction_artifact_ref: StoredArtifactRef
    content_artifact_ref: StoredArtifactRef
    quality_policy_ref: VersionedArtifactRef
    automated_checks: tuple[AutomatedQualityCheck, ...]
    reviewer_observations: tuple[ReviewerQualityObservation, ...]
    uncertainties: tuple[ExtractionUncertainty, ...]
    quality_status: ExtractionQualityStatus
    issues: tuple[str, ...]
    abstention: SystemAbstention
    assessed_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.assessment_id, "assessment_id")
        _require_non_empty(self.content_id, "content_id")
        _parse_timestamp(self.assessed_at, "assessed_at")
        if self.artifact_id != f"extraction-quality:{self.assessment_id}":
            raise ExtractionQualityEvidenceError(
                "quality artifact ID must derive from assessment_id"
            )
        if not self.extraction_artifact_ref.artifact_id.startswith(
            f"extraction:{self.content_id}:"
        ):
            raise ExtractionQualityEvidenceError(
                "quality assessment extraction reference must identify content_id"
            )
        check_ids = tuple(item.check_id for item in self.automated_checks)
        if len(check_ids) != len(set(check_ids)):
            raise ExtractionQualityEvidenceError(
                "quality assessment check IDs must be unique"
            )
        observation_ids = tuple(
            item.observation_id for item in self.reviewer_observations
        )
        if len(observation_ids) != len(set(observation_ids)):
            raise ExtractionQualityEvidenceError(
                "review observation IDs must be unique"
            )
        uncertainty_ids = tuple(item.uncertainty_id for item in self.uncertainties)
        if len(uncertainty_ids) != len(set(uncertainty_ids)):
            raise ExtractionQualityEvidenceError(
                "uncertainty IDs must be unique"
            )
        if len(self.issues) != len(set(self.issues)):
            raise ExtractionQualityEvidenceError(
                "quality issues must not contain duplicates"
            )
        if any(not issue.strip() for issue in self.issues):
            raise ExtractionQualityEvidenceError(
                "quality issues must not be empty"
            )
        has_failed_check = any(
            item.outcome is AutomatedCheckOutcome.FAILED
            for item in self.automated_checks
        )
        has_review_concern = any(
            item.finding is not ReviewerFinding.CONFIRMED
            for item in self.reviewer_observations
        )
        if self.quality_status is ExtractionQualityStatus.CLEAN:
            if (
                self.issues
                or self.uncertainties
                or self.abstention.triggered
                or has_failed_check
                or has_review_concern
            ):
                raise ExtractionQualityEvidenceError(
                    "clean quality may not contain issues, uncertainty, failures, "
                    "review concerns, or abstention"
                )
        elif not self.issues:
            raise ExtractionQualityEvidenceError(
                "non-clean extraction quality requires issues"
            )
        if self.quality_status is ExtractionQualityStatus.FAILED:
            if not self.abstention.triggered:
                raise ExtractionQualityEvidenceError(
                    "failed extraction quality must trigger abstention"
                )
            if "extraction-quality-failed" not in self.abstention.reasons:
                raise ExtractionQualityEvidenceError(
                    "failed extraction quality requires extraction-quality-failed"
                )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ExtractionQualityEvidenceError(
                "quality assessment hash must match canonical payload"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractionQualityAssessmentSnapshot:
        checks_value = document.get("automated_checks")
        observations_value = document.get("reviewer_observations")
        uncertainties_value = document.get("uncertainties")
        if not isinstance(checks_value, list):
            raise ExtractionQualityEvidenceError(
                "automated_checks must be an array"
            )
        if not isinstance(observations_value, list):
            raise ExtractionQualityEvidenceError(
                "reviewer_observations must be an array"
            )
        if not isinstance(uncertainties_value, list):
            raise ExtractionQualityEvidenceError(
                "uncertainties must be an array"
            )
        abstention_document = _mapping(
            document.get("abstention"),
            "abstention",
        )
        triggered = abstention_document.get("triggered")
        if not isinstance(triggered, bool):
            raise ExtractionQualityEvidenceError(
                "abstention.triggered must be a boolean"
            )
        payload = canonical_json_bytes(document)
        return cls(
            artifact_id=_string(document.get("artifact_id"), "artifact_id"),
            assessment_id=_string(
                document.get("assessment_id"),
                "assessment_id",
            ),
            content_id=_string(document.get("content_id"), "content_id"),
            source_artifact_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("source_artifact_ref"),
                    "source_artifact_ref",
                )
            ),
            extraction_artifact_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("extraction_artifact_ref"),
                    "extraction_artifact_ref",
                )
            ),
            content_artifact_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("content_artifact_ref"),
                    "content_artifact_ref",
                )
            ),
            quality_policy_ref=_versioned_ref(
                document.get("quality_policy_ref"),
                "quality_policy_ref",
            ),
            automated_checks=tuple(
                AutomatedQualityCheck.from_document(
                    _mapping(item, "automated check")
                )
                for item in checks_value
            ),
            reviewer_observations=tuple(
                ReviewerQualityObservation.from_document(
                    _mapping(item, "reviewer observation")
                )
                for item in observations_value
            ),
            uncertainties=tuple(
                ExtractionUncertainty.from_document(
                    _mapping(item, "uncertainty")
                )
                for item in uncertainties_value
            ),
            quality_status=ExtractionQualityStatus(
                _string(document.get("quality_status"), "quality_status")
            ),
            issues=_string_tuple(document.get("issues"), "issues"),
            abstention=SystemAbstention(
                triggered=triggered,
                reasons=_string_tuple(
                    abstention_document.get("reasons"),
                    "abstention.reasons",
                ),
            ),
            assessed_at=_string(document.get("assessed_at"), "assessed_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    @classmethod
    def from_artifact(
        cls,
        artifact: CanonicalArtifact,
    ) -> ExtractionQualityAssessmentSnapshot:
        try:
            document = cast(dict[str, Any], json.loads(artifact.text))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionQualityEvidenceError(
                "quality assessment artifact is not readable JSON"
            ) from exc
        snapshot = cls.from_document(_mapping(document, "quality assessment"))
        if snapshot.artifact_id != artifact.artifact_id:
            raise ExtractionQualityEvidenceError(
                "stored quality assessment ID differs from payload"
            )
        if snapshot.artifact_hash != artifact.artifact_hash:
            raise ExtractionQualityEvidenceError(
                "stored quality assessment hash differs from payload"
            )
        if snapshot.canonical_payload != artifact.payload:
            raise ExtractionQualityEvidenceError(
                "stored quality assessment is not canonical"
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
class QualityEvidenceEntry:
    """One ordered quality-assessment reference in a frozen corpus."""

    content_id: str
    quality_assessment_ref: StoredArtifactRef

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> QualityEvidenceEntry:
        return cls(
            content_id=_string(document.get("content_id"), "content_id"),
            quality_assessment_ref=StoredArtifactRef.from_document(
                _mapping(
                    document.get("quality_assessment_ref"),
                    "quality_assessment_ref",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class QualityBoundExtractionCorpusSnapshot:
    """Method-bound extraction corpus plus exact policy and evidence references."""

    corpus: MethodBoundExtractionCorpusSnapshot
    quality_policy_ref: VersionedArtifactRef
    quality_entries: tuple[QualityEvidenceEntry, ...]

    def __post_init__(self) -> None:
        if tuple(item.content_id for item in self.quality_entries) != self.content_ids:
            raise ExtractionQualityEvidenceError(
                "quality evidence order must match corpus content IDs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> QualityBoundExtractionCorpusSnapshot:
        contents_value = document.get("contents")
        if not isinstance(contents_value, list):
            raise ExtractionQualityEvidenceError("contents must be an array")
        return cls(
            corpus=MethodBoundExtractionCorpusSnapshot.from_document(document),
            quality_policy_ref=_versioned_ref(
                document.get("quality_policy_ref"),
                "quality_policy_ref",
            ),
            quality_entries=tuple(
                QualityEvidenceEntry.from_document(
                    _mapping(item, "quality corpus entry")
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
class QualityAssessmentSummary:
    """Decision-facing summary that preserves status, issues, and abstention."""

    content_id: str
    quality_status: ExtractionQualityStatus
    issues: tuple[str, ...]
    uncertainty_ids: tuple[str, ...]
    abstention: SystemAbstention


@dataclass(frozen=True, slots=True)
class ExtractionQualityDecisionReport:
    """Canonical quality gate decision distinct from method eligibility."""

    experiment_id: str
    experiment_version: str
    quality_corpus_ref: VersionedArtifactRef
    method_bound_corpus_ref: VersionedArtifactRef
    quality_policy_ref: VersionedArtifactRef
    outcome: QualityDecisionOutcome
    assessments: tuple[QualityAssessmentSummary, ...]
    evaluated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _parse_timestamp(self.evaluated_at, "evaluated_at")
        if not self.assessments:
            raise ExtractionQualityEvidenceError(
                "quality decision requires assessments"
            )
        content_ids = tuple(item.content_id for item in self.assessments)
        if len(content_ids) != len(set(content_ids)):
            raise ExtractionQualityEvidenceError(
                "quality decision content IDs must be unique"
            )
        abstaining = any(item.abstention.triggered for item in self.assessments)
        if self.outcome is QualityDecisionOutcome.ABSTAIN and not abstaining:
            raise ExtractionQualityEvidenceError(
                "abstain outcome requires at least one abstaining assessment"
            )
        if self.outcome is QualityDecisionOutcome.EXECUTE and abstaining:
            raise ExtractionQualityEvidenceError(
                "execute outcome may not contain abstaining assessments"
            )

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "extraction-quality-decision"
        )

    def artifact(self) -> CanonicalArtifact:
        return serialize_artifact(self.artifact_id, self)


@dataclass(frozen=True, slots=True)
class StoredQualityEvidence:
    """Verified policy and assessment artifacts loaded from storage."""

    corpus_ref: StoredArtifactRef
    policy_ref: StoredArtifactRef
    assessment_refs: tuple[StoredArtifactRef, ...]
    assessments: tuple[ExtractionQualityAssessmentSnapshot, ...]

    def __post_init__(self) -> None:
        if not self.assessments or len(self.assessment_refs) != len(self.assessments):
            raise ValueError(
                "stored quality evidence requires one reference per assessment"
            )


def _load_quality_assessment(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> ExtractionQualityAssessmentSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    assessment = ExtractionQualityAssessmentSnapshot.from_artifact(artifact)
    if assessment.reference() != reference:
        raise ArtifactIntegrityError(
            "stored quality assessment reference differs from corpus"
        )
    return assessment


def load_quality_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: QualityBoundExtractionCorpusSnapshot,
    policy: ExtractionQualityPolicySnapshot,
) -> StoredQualityEvidence:
    """Load and reverify the quality policy and every assessment artifact."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored quality-bound corpus differs from expected manifest"
        )
    policy_artifact = store.get(
        policy.policy_id,
        expected_hash=policy.artifact_hash,
    )
    if policy_artifact.payload != policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored extraction-quality policy differs from expected policy"
        )
    assessments = tuple(
        _load_quality_assessment(store, entry.quality_assessment_ref)
        for entry in corpus.quality_entries
    )
    return StoredQualityEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        policy_ref=store.reference(policy.policy_id),
        assessment_refs=tuple(item.reference() for item in assessments),
        assessments=assessments,
    )


def validate_extraction_quality_evidence(
    *,
    plan: ExperimentPlan,
    corpus: QualityBoundExtractionCorpusSnapshot,
    policy: ExtractionQualityPolicySnapshot,
    assessments: tuple[ExtractionQualityAssessmentSnapshot, ...],
    evaluated_at: str,
) -> ExtractionQualityDecisionReport:
    """Evaluate exact evidence before any analyzer execution begins."""

    _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise ExtractionQualityEvidenceError(
            "only a frozen experiment plan may pass the quality gate"
        )
    if plan.corpus_ref != corpus.reference():
        raise ExtractionQualityEvidenceError(
            "experiment plan corpus_ref does not match quality-bound corpus"
        )
    if plan.content_ids != corpus.content_ids:
        raise ExtractionQualityEvidenceError(
            "experiment plan content order does not match quality-bound corpus"
        )
    if corpus.quality_policy_ref != policy.reference():
        raise ExtractionQualityEvidenceError(
            "quality corpus policy reference does not match supplied policy"
        )
    if policy.status is not ExtractionQualityPolicyLifecycle.ACCEPTED:
        raise ExtractionQualityEvidenceError(
            "extraction-quality policy must be accepted before execution"
        )
    if len(assessments) != len(corpus.quality_entries):
        raise ExtractionQualityEvidenceError(
            "quality assessment population does not match frozen corpus"
        )

    required_checks = tuple(
        (item.check_id, item.check_revision)
        for item in policy.required_checks
    )
    summaries: list[QualityAssessmentSummary] = []
    failures: list[str] = []
    for base_entry, quality_entry, assessment in zip(
        corpus.corpus.corpus.contents,
        corpus.quality_entries,
        assessments,
        strict=True,
    ):
        if assessment.reference() != quality_entry.quality_assessment_ref:
            failures.append(
                f"{base_entry.content_id}: quality assessment reference differs"
            )
            continue
        expected_refs = (
            base_entry.source_artifact_ref,
            base_entry.extraction_artifact_ref,
            base_entry.content_artifact_ref,
        )
        observed_refs = (
            assessment.source_artifact_ref,
            assessment.extraction_artifact_ref,
            assessment.content_artifact_ref,
        )
        if observed_refs != expected_refs:
            failures.append(
                f"{base_entry.content_id}: quality evidence graph references differ"
            )
            continue
        if assessment.content_id != base_entry.content_id:
            failures.append(
                f"{base_entry.content_id}: quality assessment content ID differs"
            )
            continue
        if assessment.quality_policy_ref != policy.reference():
            failures.append(
                f"{base_entry.content_id}: assessment policy reference differs"
            )
            continue
        observed_checks = tuple(
            (item.check_id, item.check_revision)
            for item in assessment.automated_checks
        )
        if observed_checks != required_checks:
            failures.append(
                f"{base_entry.content_id}: required automated checks differ"
            )
            continue
        if len(assessment.reviewer_observations) < (
            policy.minimum_reviewer_observations
        ):
            failures.append(
                f"{base_entry.content_id}: reviewer observation minimum not met"
            )
            continue
        status_reason = f"quality-status:{assessment.quality_status.value}"
        if assessment.quality_status in policy.abstain_on_statuses:
            if not assessment.abstention.triggered:
                failures.append(
                    f"{base_entry.content_id}: policy-required abstention missing"
                )
                continue
            if status_reason not in assessment.abstention.reasons:
                failures.append(
                    f"{base_entry.content_id}: policy status reason missing"
                )
                continue
        summaries.append(
            QualityAssessmentSummary(
                content_id=assessment.content_id,
                quality_status=assessment.quality_status,
                issues=assessment.issues,
                uncertainty_ids=tuple(
                    item.uncertainty_id for item in assessment.uncertainties
                ),
                abstention=assessment.abstention,
            )
        )
    if failures:
        raise ExtractionQualityEvidenceError(
            "extraction quality evidence failed: " + " | ".join(failures)
        )

    outcome = (
        QualityDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in summaries)
        else QualityDecisionOutcome.EXECUTE
    )
    return ExtractionQualityDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        quality_corpus_ref=corpus.reference(),
        method_bound_corpus_ref=corpus.corpus.reference(),
        quality_policy_ref=policy.reference(),
        outcome=outcome,
        assessments=tuple(summaries),
        evaluated_at=evaluated_at,
    )


def persist_quality_bound_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: QualityBoundExtractionCorpusSnapshot,
    policy: ExtractionQualityPolicySnapshot,
    sources: tuple[SourceArtifactSnapshot, ...],
    extractions: tuple[ExtractionManifestSnapshot, ...],
    contents: tuple[ExtractedContentSnapshot, ...],
    assessments: tuple[ExtractionQualityAssessmentSnapshot, ...],
    evaluated_at: str,
) -> StoredQualityEvidence:
    """Persist graph, policy, and evidence first; publish quality corpus last."""

    validate_extraction_quality_evidence(
        plan=plan,
        corpus=corpus,
        policy=policy,
        assessments=assessments,
        evaluated_at=evaluated_at,
    )
    base_entries = corpus.corpus.corpus.contents
    if not (
        len(sources)
        == len(extractions)
        == len(contents)
        == len(assessments)
        == len(base_entries)
    ):
        raise ExtractionQualityEvidenceError(
            "source, extraction, content, assessment, and corpus populations must match"
        )
    for entry, source, extraction, content, assessment in zip(
        base_entries,
        sources,
        extractions,
        contents,
        assessments,
        strict=True,
    ):
        entry.verify(source, extraction, content)
        if assessment.source_artifact_ref != source.reference():
            raise ExtractionQualityEvidenceError(
                "quality assessment source reference differs"
            )
        if assessment.extraction_artifact_ref != extraction.reference():
            raise ExtractionQualityEvidenceError(
                "quality assessment extraction reference differs"
            )
        if assessment.content_artifact_ref != content.reference():
            raise ExtractionQualityEvidenceError(
                "quality assessment content reference differs"
            )
        if store.append(source.artifact()) != source.reference():
            raise ArtifactIntegrityError("stored source reference differs")
        if store.append(content.artifact()) != content.reference():
            raise ArtifactIntegrityError("stored content reference differs")
        if store.append(extraction.artifact()) != extraction.reference():
            raise ArtifactIntegrityError("stored extraction reference differs")
        if store.append(assessment.artifact()) != assessment.reference():
            raise ArtifactIntegrityError(
                "stored quality assessment reference differs"
            )
    policy_ref = store.append(policy.artifact())
    if policy_ref.artifact_hash != policy.artifact_hash:
        raise ArtifactIntegrityError("stored quality policy reference differs")
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError("stored quality corpus reference differs")
    return load_quality_evidence(store, corpus=corpus, policy=policy)
