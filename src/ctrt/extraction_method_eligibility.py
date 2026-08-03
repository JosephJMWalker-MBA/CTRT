"""Frozen extraction-method registries and exact eligibility validation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ctrt.contracts import SourceType
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_manifest import (
    CoordinateMappingKind,
    ExtractionCorpusManifestSnapshot,
    ExtractionManifestSnapshot,
)
from ctrt.serialization import CanonicalArtifact, canonical_json_bytes, serialize_artifact


class ExtractionMethodRegistryLifecycle(StrEnum):
    """Governance state of one extraction-method registry artifact."""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class ExtractionMethodDisposition(StrEnum):
    """Method lifecycle state relevant to extraction eligibility."""

    PROPOSED = "proposed"
    ELIGIBLE_FOR_EVALUATION = "eligible_for_evaluation"
    EVALUATED = "evaluated"
    SELECTED_FOR_DOMAIN = "selected_for_domain"
    DEFERRED = "deferred"
    REJECTED_BEFORE_EXECUTION = "rejected_before_execution"
    NOT_SELECTED = "not_selected"


class ExtractionLicenseStatus(StrEnum):
    """License-review state preserved independently from method disposition."""

    PENDING = "pending"
    PROVISIONALLY_VERIFIED = "provisionally_verified"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class ExtractionMethodEligibilityError(ValueError):
    """Raised when an extraction graph is not authorized by its frozen registry."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
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


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return result


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
class ExtractionMethodRecord:
    """Registry fields required to authorize one extraction method revision."""

    method_id: str
    status: ExtractionMethodDisposition
    license_status: ExtractionLicenseStatus
    pin_required: bool
    pinned_revision: str | None
    supported_source_types: tuple[SourceType, ...]
    permitted_mapping_kinds: tuple[CoordinateMappingKind, ...]
    authorized_configuration_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.method_id.strip():
            raise ValueError("method_id must not be empty")
        if not self.supported_source_types:
            raise ValueError("method must declare at least one supported source type")
        if len(self.supported_source_types) != len(set(self.supported_source_types)):
            raise ValueError("supported source types must not contain duplicates")
        if not self.permitted_mapping_kinds:
            raise ValueError("method must declare at least one permitted mapping kind")
        if len(self.permitted_mapping_kinds) != len(
            set(self.permitted_mapping_kinds)
        ):
            raise ValueError("permitted mapping kinds must not contain duplicates")
        if not self.authorized_configuration_hashes:
            raise ValueError(
                "method must declare at least one authorized configuration hash"
            )
        if len(self.authorized_configuration_hashes) != len(
            set(self.authorized_configuration_hashes)
        ):
            raise ValueError(
                "authorized configuration hashes must not contain duplicates"
            )
        for value in self.authorized_configuration_hashes:
            VersionedArtifactRef(
                artifact_id="configuration",
                artifact_version="0",
                artifact_hash=value,
            )


@dataclass(frozen=True, slots=True)
class ExtractionMethodRegistrySnapshot:
    """Parsed execution view plus canonical identity of a method registry."""

    registry_id: str
    registry_version: str
    status: ExtractionMethodRegistryLifecycle
    methods: tuple[ExtractionMethodRecord, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.registry_id.strip() or not self.registry_version.strip():
            raise ValueError("method registry identity fields must not be empty")
        if not self.created_at.strip():
            raise ValueError("method registry created_at must not be empty")
        method_ids = tuple(method.method_id for method in self.methods)
        if len(method_ids) != len(set(method_ids)):
            raise ValueError("method registry IDs must be unique")
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise ValueError("method registry hash must match canonical payload")

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> ExtractionMethodRegistrySnapshot:
        methods_value = document.get("methods")
        if not isinstance(methods_value, list):
            raise ValueError("methods must be an array")
        payload = canonical_json_bytes(document)
        return cls(
            registry_id=_string(document.get("registry_id"), "registry_id"),
            registry_version=_string(
                document.get("registry_version"),
                "registry_version",
            ),
            status=ExtractionMethodRegistryLifecycle(
                _string(document.get("status"), "status")
            ),
            methods=tuple(
                _method_from_document(_mapping(item, "method"))
                for item in methods_value
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

    def method(self, method_id: str) -> ExtractionMethodRecord | None:
        return next(
            (method for method in self.methods if method.method_id == method_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class MethodBoundExtractionCorpusSnapshot:
    """Frozen extraction corpus plus its exact method-registry binding."""

    corpus: ExtractionCorpusManifestSnapshot
    method_registry_ref: VersionedArtifactRef

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> MethodBoundExtractionCorpusSnapshot:
        return cls(
            corpus=ExtractionCorpusManifestSnapshot.from_document(document),
            method_registry_ref=_versioned_ref(
                document.get("method_registry_ref"),
                "method_registry_ref",
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
class AuthorizedExtractionMethod:
    """One extraction manifest authorized by the exact registry snapshot."""

    content_id: str
    extraction_artifact_id: str
    method_id: str
    method_revision: str
    configuration_hash: str
    source_type: SourceType
    mapping_kinds: tuple[CoordinateMappingKind, ...]


@dataclass(frozen=True, slots=True)
class ExtractionMethodEligibilityReport:
    """Canonical evidence that every extraction graph passed the method gate."""

    experiment_id: str
    experiment_version: str
    corpus_ref: VersionedArtifactRef
    method_registry_ref: VersionedArtifactRef
    authorized_extractions: tuple[AuthorizedExtractionMethod, ...]

    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or not self.experiment_version.strip():
            raise ValueError("eligibility report identity fields must not be empty")
        if not self.authorized_extractions:
            raise ValueError("eligibility report requires authorized extractions")
        content_ids = tuple(item.content_id for item in self.authorized_extractions)
        if len(content_ids) != len(set(content_ids)):
            raise ValueError(
                "eligibility report content IDs must not contain duplicates"
            )

    @property
    def artifact_id(self) -> str:
        return (
            f"{self.experiment_id}:{self.experiment_version}:"
            "extraction-method-eligibility"
        )

    def artifact(self) -> CanonicalArtifact:
        return serialize_artifact(self.artifact_id, self)


ELIGIBLE_METHOD_DISPOSITIONS = {
    ExtractionMethodDisposition.ELIGIBLE_FOR_EVALUATION,
    ExtractionMethodDisposition.EVALUATED,
    ExtractionMethodDisposition.SELECTED_FOR_DOMAIN,
}
EXECUTABLE_EXTRACTION_LICENSE_STATES = {
    ExtractionLicenseStatus.PROVISIONALLY_VERIFIED,
    ExtractionLicenseStatus.VERIFIED,
}


def _method_from_document(document: Mapping[str, object]) -> ExtractionMethodRecord:
    license_review = _mapping(document.get("license_review"), "license_review")
    revision_policy = _mapping(
        document.get("revision_policy"),
        "revision_policy",
    )
    return ExtractionMethodRecord(
        method_id=_string(document.get("method_id"), "method_id"),
        status=ExtractionMethodDisposition(
            _string(document.get("status"), "method status")
        ),
        license_status=ExtractionLicenseStatus(
            _string(license_review.get("status"), "license_review.status")
        ),
        pin_required=_boolean(
            revision_policy.get("pin_required"),
            "revision_policy.pin_required",
        ),
        pinned_revision=_optional_string(
            revision_policy.get("pinned_revision"),
            "revision_policy.pinned_revision",
        ),
        supported_source_types=tuple(
            SourceType(item)
            for item in _string_tuple(
                document.get("supported_source_types"),
                "supported_source_types",
            )
        ),
        permitted_mapping_kinds=tuple(
            CoordinateMappingKind(item)
            for item in _string_tuple(
                document.get("permitted_mapping_kinds"),
                "permitted_mapping_kinds",
            )
        ),
        authorized_configuration_hashes=_string_tuple(
            document.get("authorized_configuration_hashes"),
            "authorized_configuration_hashes",
        ),
    )


def _extraction_reasons(
    extraction: ExtractionManifestSnapshot,
    source_type: SourceType,
    method: ExtractionMethodRecord | None,
) -> tuple[str, ...]:
    if method is None:
        return (f"method {extraction.method_id!r} is absent from the registry",)

    reasons: list[str] = []
    if method.status not in ELIGIBLE_METHOD_DISPOSITIONS:
        reasons.append(f"method disposition {method.status.value!r} is not executable")
    if method.license_status is ExtractionLicenseStatus.BLOCKED:
        reasons.append("method license review is blocked")
    elif method.license_status not in EXECUTABLE_EXTRACTION_LICENSE_STATES:
        reasons.append("method license review is not provisionally verified")
    if not method.pin_required:
        reasons.append("method does not require immutable revision pinning")
    if method.pinned_revision is None:
        reasons.append("method has no pinned implementation revision")
    elif extraction.method_revision != method.pinned_revision:
        reasons.append("method revision differs from the registry pin")
    if source_type not in method.supported_source_types:
        reasons.append("source type is not supported by the method record")
    observed_mapping_kinds = {span.kind for span in extraction.coordinate_map}
    if not observed_mapping_kinds.issubset(set(method.permitted_mapping_kinds)):
        reasons.append("coordinate mapping kind is not permitted")
    if extraction.configuration_hash not in method.authorized_configuration_hashes:
        reasons.append("extraction configuration hash is not authorized")
    return tuple(reasons)


def validate_extraction_method_eligibility(
    *,
    plan: ExperimentPlan,
    corpus: MethodBoundExtractionCorpusSnapshot,
    registry: ExtractionMethodRegistrySnapshot,
    extractions: tuple[ExtractionManifestSnapshot, ...],
) -> ExtractionMethodEligibilityReport:
    """Authorize every extraction against one exact accepted registry."""

    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise ExtractionMethodEligibilityError(
            "only a frozen experiment plan may be authorized"
        )
    if plan.corpus_ref != corpus.reference():
        raise ExtractionMethodEligibilityError(
            "experiment plan corpus_ref does not match the extraction corpus"
        )
    if plan.content_ids != corpus.content_ids:
        raise ExtractionMethodEligibilityError(
            "experiment plan content order does not match the extraction corpus"
        )
    if corpus.method_registry_ref != registry.reference():
        raise ExtractionMethodEligibilityError(
            "extraction corpus method_registry_ref does not match the supplied registry"
        )
    if registry.status is not ExtractionMethodRegistryLifecycle.ACCEPTED:
        raise ExtractionMethodEligibilityError(
            "extraction method registry must be accepted before execution"
        )
    if len(extractions) != len(corpus.corpus.contents):
        raise ExtractionMethodEligibilityError(
            "extraction population does not match the frozen corpus"
        )

    failures: list[str] = []
    authorized: list[AuthorizedExtractionMethod] = []
    for entry, extraction in zip(corpus.corpus.contents, extractions, strict=True):
        if extraction.reference() != entry.extraction_artifact_ref:
            failures.append(
                f"{entry.content_id}: extraction reference differs from corpus"
            )
            continue
        if extraction.content_id != entry.content_id:
            failures.append(
                f"{entry.content_id}: extraction content ID differs from corpus"
            )
            continue
        reasons = _extraction_reasons(
            extraction,
            entry.source_type,
            registry.method(extraction.method_id),
        )
        if reasons:
            failures.append(f"{entry.content_id}: " + "; ".join(reasons))
            continue
        authorized.append(
            AuthorizedExtractionMethod(
                content_id=entry.content_id,
                extraction_artifact_id=extraction.artifact_id,
                method_id=extraction.method_id,
                method_revision=extraction.method_revision,
                configuration_hash=extraction.configuration_hash,
                source_type=entry.source_type,
                mapping_kinds=tuple(
                    dict.fromkeys(span.kind for span in extraction.coordinate_map)
                ),
            )
        )
    if failures:
        raise ExtractionMethodEligibilityError(
            "extraction method eligibility failed: " + " | ".join(failures)
        )

    return ExtractionMethodEligibilityReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        corpus_ref=corpus.reference(),
        method_registry_ref=registry.reference(),
        authorized_extractions=tuple(authorized),
    )
