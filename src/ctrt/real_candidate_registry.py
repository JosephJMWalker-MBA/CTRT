"""Binding facts a real packaged candidate must declare beyond the base record.

This module adds no second eligibility path. :func:`ctrt.candidate_eligibility.
validate_candidate_eligibility` remains the only execution gate. These fields
record the package, taxonomy, configuration, evidence-localization, and
execution-boundary facts a real distribution must pin, and they are covered by
the registry artifact hash because that hash spans the whole document.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class EvidenceLocalization(StrEnum):
    """Whether a candidate can attribute its outputs to exact input spans."""

    NATIVE = "native"
    POST_HOC = "post-hoc"
    UNAVAILABLE = "unavailable"


class RealCandidateRegistryError(ValueError):
    """Raised when a real-candidate record omits a required binding fact."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RealCandidateRegistryError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise RealCandidateRegistryError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RealCandidateRegistryError(f"{field_name} must be a non-empty string")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise RealCandidateRegistryError(f"{field_name} must be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class PackageBinding:
    """The exact installable distribution a candidate is pinned to."""

    distribution: str
    version: str
    import_name: str
    dependency_extra: str

    def __post_init__(self) -> None:
        values = (
            self.distribution,
            self.version,
            self.import_name,
            self.dependency_extra,
        )
        if any(not value.strip() for value in values):
            raise RealCandidateRegistryError(
                "package binding fields must not be empty"
            )

    @property
    def requirement(self) -> str:
        """Return the exact pinned requirement specifier."""

        return f"{self.distribution}=={self.version}"


@dataclass(frozen=True, slots=True)
class ExecutionBoundary:
    """Explicit prohibition on user-facing execution before a selection record."""

    user_facing_execution_permitted: bool
    requires_selection_record: bool
    notes: str

    def __post_init__(self) -> None:
        if not self.notes.strip():
            raise RealCandidateRegistryError("execution boundary notes must not be empty")
        if self.user_facing_execution_permitted:
            raise RealCandidateRegistryError(
                "an admitted candidate may not permit user-facing execution"
            )
        if not self.requires_selection_record:
            raise RealCandidateRegistryError(
                "an admitted candidate must require a later selection record"
            )


@dataclass(frozen=True, slots=True)
class RealCandidateBinding:
    """Package, taxonomy, configuration, and boundary facts for one candidate."""

    candidate_id: str
    package: PackageBinding
    taxonomy_id: str
    taxonomy_version: str
    configuration_hash: str
    evidence_localization: EvidenceLocalization
    evidence_localization_notes: str
    execution_boundary: ExecutionBoundary

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise RealCandidateRegistryError("candidate_id must not be empty")
        if any(not value.strip() for value in (self.taxonomy_id, self.taxonomy_version)):
            raise RealCandidateRegistryError("taxonomy identity must not be empty")
        if not self.configuration_hash.startswith("sha256:"):
            raise RealCandidateRegistryError(
                "configuration_hash must use sha256 identity"
            )
        if not self.evidence_localization_notes.strip():
            raise RealCandidateRegistryError(
                "evidence localization notes must not be empty"
            )


def parse_real_candidate_binding(
    document: Mapping[str, object],
) -> RealCandidateBinding:
    """Parse the real-candidate binding block of one candidate record."""

    package = _mapping(document.get("package_binding"), "package_binding")
    taxonomy = _mapping(document.get("taxonomy"), "taxonomy")
    localization = _mapping(document.get("evidence_localization"), "evidence_localization")
    boundary = _mapping(document.get("execution_boundary"), "execution_boundary")
    return RealCandidateBinding(
        candidate_id=_string(document.get("candidate_id"), "candidate_id"),
        package=PackageBinding(
            distribution=_string(
                package.get("distribution"), "package_binding.distribution"
            ),
            version=_string(package.get("version"), "package_binding.version"),
            import_name=_string(
                package.get("import_name"), "package_binding.import_name"
            ),
            dependency_extra=_string(
                package.get("dependency_extra"), "package_binding.dependency_extra"
            ),
        ),
        taxonomy_id=_string(taxonomy.get("taxonomy_id"), "taxonomy.taxonomy_id"),
        taxonomy_version=_string(
            taxonomy.get("taxonomy_version"), "taxonomy.taxonomy_version"
        ),
        configuration_hash=_string(
            document.get("configuration_hash"), "configuration_hash"
        ),
        evidence_localization=EvidenceLocalization(
            _string(localization.get("status"), "evidence_localization.status")
        ),
        evidence_localization_notes=_string(
            localization.get("notes"), "evidence_localization.notes"
        ),
        execution_boundary=ExecutionBoundary(
            user_facing_execution_permitted=_bool(
                boundary.get("user_facing_execution_permitted"),
                "execution_boundary.user_facing_execution_permitted",
            ),
            requires_selection_record=_bool(
                boundary.get("requires_selection_record"),
                "execution_boundary.requires_selection_record",
            ),
            notes=_string(boundary.get("notes"), "execution_boundary.notes"),
        ),
    )


def real_candidate_binding(
    document: Mapping[str, object],
    candidate_id: str,
) -> RealCandidateBinding:
    """Return the binding for one candidate ID within a registry document."""

    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        raise RealCandidateRegistryError("registry candidates must be an array")
    for item in candidates:
        record = _mapping(item, "candidate")
        if record.get("candidate_id") == candidate_id:
            return parse_real_candidate_binding(record)
    raise RealCandidateRegistryError(
        f"candidate {candidate_id!r} is absent from the registry document"
    )


__all__ = [
    "EvidenceLocalization",
    "ExecutionBoundary",
    "PackageBinding",
    "RealCandidateBinding",
    "RealCandidateRegistryError",
    "parse_real_candidate_binding",
    "real_candidate_binding",
]
