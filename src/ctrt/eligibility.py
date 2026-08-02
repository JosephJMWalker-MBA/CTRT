"""Dependency-free governance gate for CTRT dimension eligibility records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class DimensionStatus(StrEnum):
    """Maturity of one versioned CTRT construct."""

    PROPOSED = "proposed"
    DEFINED = "defined"
    INSTRUMENTED = "instrumented"
    EVALUATED = "evaluated"
    VALIDATED_FOR_DOMAIN = "validated_for_domain"
    DEFERRED = "deferred"
    REJECTED = "rejected"


class ReportEligibility(StrEnum):
    """Whether a dimension may appear in an experimental CTRT report."""

    ELIGIBLE_EXPERIMENTAL = "eligible_experimental"
    INELIGIBLE = "ineligible"
    PENDING = "pending"


_ELIGIBLE_STATUSES = frozenset(
    {
        DimensionStatus.DEFINED,
        DimensionStatus.INSTRUMENTED,
        DimensionStatus.EVALUATED,
        DimensionStatus.VALIDATED_FOR_DOMAIN,
    }
)


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """Result of applying the constitutional eligibility gate."""

    dimension_id: str
    allowed: bool
    reasons: tuple[str, ...]


def _required_string(record: Mapping[str, object], key: str, reasons: list[str]) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{key} must be a non-empty string")
        return ""
    return value


def _nested_bool(
    record: Mapping[str, object],
    object_key: str,
    value_key: str,
    reasons: list[str],
) -> bool | None:
    nested = record.get(object_key)
    if not isinstance(nested, Mapping):
        reasons.append(f"{object_key} must be an object")
        return None
    value = nested.get(value_key)
    if not isinstance(value, bool):
        reasons.append(f"{object_key}.{value_key} must be a boolean")
        return None
    return value


def _nested_string(
    record: Mapping[str, object],
    object_key: str,
    value_key: str,
    reasons: list[str],
) -> str:
    nested = record.get(object_key)
    if not isinstance(nested, Mapping):
        reasons.append(f"{object_key} must be an object")
        return ""
    value = nested.get(value_key)
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{object_key}.{value_key} must be a non-empty string")
        return ""
    return value


def evaluate_dimension_eligibility(
    record: Mapping[str, object],
    *,
    analyzer_dimension_id: str | None = None,
) -> EligibilityDecision:
    """Determine whether a candidate analyzer may enter an experimental report.

    This gate validates only constitutional readiness. It does not imply that an
    analyzer has passed benchmarking, calibration, or domain validation.
    """

    reasons: list[str] = []
    dimension_id = _required_string(record, "dimension_id", reasons)
    status_value = _required_string(record, "status", reasons)
    eligibility_value = _required_string(record, "report_eligibility", reasons)

    try:
        status = DimensionStatus(status_value)
    except ValueError:
        reasons.append(f"unknown dimension status: {status_value!r}")
        status = None

    try:
        report_eligibility = ReportEligibility(eligibility_value)
    except ValueError:
        reasons.append(f"unknown report eligibility: {eligibility_value!r}")
        report_eligibility = None

    profile_component = _nested_bool(
        record,
        "aggregation",
        "may_appear_as_profile_component",
        reasons,
    )
    overall_rating = _nested_bool(
        record,
        "aggregation",
        "may_contribute_to_overall_rating",
        reasons,
    )
    output_kind = _nested_string(record, "expected_output", "kind", reasons)

    if analyzer_dimension_id is not None and analyzer_dimension_id != dimension_id:
        reasons.append(
            "analyzer dimension does not match the eligibility record: "
            f"{analyzer_dimension_id!r} != {dimension_id!r}"
        )

    if report_eligibility is not ReportEligibility.ELIGIBLE_EXPERIMENTAL:
        reasons.append("dimension is not eligible for an experimental report")

    if status is not None and status not in _ELIGIBLE_STATUSES:
        reasons.append(f"dimension status {status.value!r} is not eligible for reporting")

    if profile_component is not True:
        reasons.append("dimension is not permitted as a profile component")

    if output_kind == "undetermined":
        reasons.append("dimension output structure is undetermined")

    if overall_rating is True:
        reasons.append("Phase 0 dimensions may not contribute to an overall rating")

    return EligibilityDecision(
        dimension_id=dimension_id,
        allowed=not reasons,
        reasons=tuple(reasons),
    )
