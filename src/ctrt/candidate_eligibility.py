"""Candidate-registry parsing and exact execution-eligibility validation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ctrt.experiments import (
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    VersionedArtifactRef,
)
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes, serialize_artifact


class RegistryLifecycle(StrEnum):
    """Governance state of one candidate-registry artifact."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class CandidateCapability(StrEnum):
    """Capability family declared by a candidate record."""

    ANALYZER = "analyzer"
    EXTRACTOR = "extractor"
    TRANSCRIPT_ACQUISITION = "transcript_acquisition"


class CandidateDisposition(StrEnum):
    """Candidate lifecycle state relevant to execution eligibility."""

    PROPOSED = "proposed"
    ELIGIBLE_FOR_EVALUATION = "eligible_for_evaluation"
    DEFERRED = "deferred"
    REJECTED_BEFORE_EXECUTION = "rejected_before_execution"
    EVALUATED = "evaluated"
    SELECTED_FOR_DOMAIN = "selected_for_domain"
    NOT_SELECTED = "not_selected"


class LicenseReviewStatus(StrEnum):
    """License-review state preserved independently from candidate disposition."""

    PENDING = "pending"
    PROVISIONALLY_VERIFIED = "provisionally_verified"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class CandidateEligibilityError(ValueError):
    """Raised when a frozen plan is not authorized by its exact registry artifact."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class CandidateExecutionRecord:
    """Registry fields required to authorize one concrete instrument execution."""

    candidate_id: str
    capability_type: CandidateCapability
    status: CandidateDisposition
    dimensions: tuple[str, ...]
    authorized_analyzer_ids: tuple[str, ...]
    license_status: LicenseReviewStatus
    pin_required: bool
    pinned_revision: str | None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("candidate dimensions must not contain duplicates")
        if len(self.authorized_analyzer_ids) != len(set(self.authorized_analyzer_ids)):
            raise ValueError("authorized analyzer IDs must not contain duplicates")


@dataclass(frozen=True, slots=True)
class CandidateRegistrySnapshot:
    """Parsed execution view plus canonical identity of a registry document."""

    registry_id: str
    registry_version: str
    status: RegistryLifecycle
    candidates: tuple[CandidateExecutionRecord, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.registry_id.strip() or not self.registry_version.strip():
            raise ValueError("registry identity fields must not be empty")
        if not self.created_at.strip():
            raise ValueError("registry created_at must not be empty")
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("registry candidate IDs must be unique")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ValueError("registry artifact_hash must match canonical payload")

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> CandidateRegistrySnapshot:
        """Parse the execution-relevant fields and canonically identify the full document."""

        candidates_value = document.get("candidates")
        if not isinstance(candidates_value, list):
            raise ValueError("candidates must be an array")
        candidates = tuple(
            _candidate_from_document(_mapping(item, "candidate"))
            for item in candidates_value
        )
        payload = canonical_json_bytes(document)
        return cls(
            registry_id=_string(document.get("registry_id"), "registry_id"),
            registry_version=_string(document.get("registry_version"), "registry_version"),
            status=RegistryLifecycle(_string(document.get("status"), "status")),
            candidates=candidates,
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )

    def reference(self) -> VersionedArtifactRef:
        """Return the exact artifact reference a frozen plan must contain."""

        return VersionedArtifactRef(
            artifact_id=self.registry_id,
            artifact_version=self.registry_version,
            artifact_hash=self.artifact_hash,
        )

    def candidate(self, candidate_id: str) -> CandidateExecutionRecord | None:
        """Return one candidate by stable ID."""

        return next(
            (candidate for candidate in self.candidates if candidate.candidate_id == candidate_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class CandidateEligibilityReport:
    """Evidence that every planned instrument passed the exact registry gate."""

    experiment_id: str
    experiment_version: str
    candidate_registry_ref: VersionedArtifactRef
    authorized_candidate_ids: tuple[str, ...]
    authorized_analyzer_ids: tuple[str, ...]

    def artifact(self) -> CanonicalArtifact:
        """Serialize the authorization decision as an immutable canonical artifact."""

        return serialize_artifact(
            f"{self.experiment_id}:candidate-eligibility",
            self,
        )

    def reference(self) -> VersionedArtifactRef:
        """Return the plan-version-specific reference stored by execution records."""

        artifact = self.artifact()
        return VersionedArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_version=self.experiment_version,
            artifact_hash=artifact.artifact_hash,
        )


ELIGIBLE_DISPOSITIONS = {
    CandidateDisposition.ELIGIBLE_FOR_EVALUATION,
    CandidateDisposition.EVALUATED,
    CandidateDisposition.SELECTED_FOR_DOMAIN,
}


def _candidate_from_document(document: Mapping[str, object]) -> CandidateExecutionRecord:
    license_review = _mapping(document.get("license_review"), "license_review")
    revision_policy = _mapping(document.get("revision_policy"), "revision_policy")
    pin_required = revision_policy.get("pin_required")
    if not isinstance(pin_required, bool):
        raise ValueError("revision_policy.pin_required must be a boolean")
    authorized = document.get("authorized_analyzer_ids", [])
    return CandidateExecutionRecord(
        candidate_id=_string(document.get("candidate_id"), "candidate_id"),
        capability_type=CandidateCapability(
            _string(document.get("capability_type"), "capability_type")
        ),
        status=CandidateDisposition(_string(document.get("status"), "candidate status")),
        dimensions=_string_tuple(document.get("dimensions"), "dimensions"),
        authorized_analyzer_ids=_string_tuple(authorized, "authorized_analyzer_ids"),
        license_status=LicenseReviewStatus(
            _string(license_review.get("status"), "license_review.status")
        ),
        pin_required=pin_required,
        pinned_revision=_optional_string(
            revision_policy.get("pinned_revision"),
            "revision_policy.pinned_revision",
        ),
    )


def _instrument_reasons(
    instrument: InstrumentRevision,
    candidate: CandidateExecutionRecord | None,
    plan: ExperimentPlan,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if instrument.dimension_id not in plan.dimension_ids:
        reasons.append(f"dimension {instrument.dimension_id!r} is not declared by the plan")
    if candidate is None:
        return (f"candidate {instrument.candidate_id!r} is absent from the registry", *reasons)
    if candidate.capability_type is not CandidateCapability.ANALYZER:
        reasons.append("candidate capability is not analyzer")
    if candidate.status not in ELIGIBLE_DISPOSITIONS:
        reasons.append(f"candidate disposition {candidate.status.value!r} is not executable")
    if candidate.license_status is LicenseReviewStatus.BLOCKED:
        reasons.append("candidate license review is blocked")
    if instrument.analyzer_id not in candidate.authorized_analyzer_ids:
        reasons.append("analyzer identity is not explicitly authorized by the candidate record")
    if instrument.dimension_id not in candidate.dimensions:
        reasons.append("instrument dimension is not declared by the candidate record")
    if not candidate.pin_required:
        reasons.append("candidate does not require immutable revision pinning")
    if candidate.pinned_revision is None:
        reasons.append("candidate has no pinned implementation revision")
    elif instrument.implementation_revision != candidate.pinned_revision:
        reasons.append("instrument implementation revision differs from the registry pin")
    return tuple(reasons)


def validate_candidate_eligibility(
    plan: ExperimentPlan,
    registry: CandidateRegistrySnapshot,
) -> CandidateEligibilityReport:
    """Authorize all planned instruments against one exact accepted registry snapshot."""

    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise CandidateEligibilityError("only a frozen experiment plan may be authorized")
    if plan.candidate_registry_ref != registry.reference():
        raise CandidateEligibilityError(
            "experiment plan candidate_registry_ref does not match the supplied canonical registry"
        )
    if registry.status is not RegistryLifecycle.ACCEPTED:
        raise CandidateEligibilityError("candidate registry must be accepted before execution")

    failures: list[str] = []
    for instrument in plan.instrument_revisions:
        reasons = _instrument_reasons(instrument, registry.candidate(instrument.candidate_id), plan)
        if reasons:
            failures.append(f"{instrument.analyzer_id}: " + "; ".join(reasons))
    if failures:
        raise CandidateEligibilityError("candidate eligibility failed: " + " | ".join(failures))

    return CandidateEligibilityReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        candidate_registry_ref=registry.reference(),
        authorized_candidate_ids=tuple(
            instrument.candidate_id for instrument in plan.instrument_revisions
        ),
        authorized_analyzer_ids=tuple(
            instrument.analyzer_id for instrument in plan.instrument_revisions
        ),
    )
