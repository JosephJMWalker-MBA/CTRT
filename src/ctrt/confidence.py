"""Structured confidence, abstention, and aggregation policy contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InstrumentProbabilitySource(StrEnum):
    """Origin of a probability-like value."""

    MODEL_REPORTED = "model-reported"
    DERIVED = "derived"


class CalibrationStatus(StrEnum):
    """Evidence state for probability calibration."""

    UNKNOWN = "unknown"
    ESTIMATED = "estimated"
    VALIDATED = "validated"


class ApplicabilityStatus(StrEnum):
    """Fit between content and an instrument's evaluated boundary."""

    IN_DOMAIN = "in-domain"
    BORDERLINE = "borderline"
    OUT_OF_DOMAIN = "out-of-domain"
    UNKNOWN = "unknown"


class ExtractionQualityStatus(StrEnum):
    """Quality of the canonical text supplied to analysis."""

    CLEAN = "clean"
    PARTIAL = "partial"
    DEGRADED = "degraded"
    FAILED = "failed"


class AgreementStatus(StrEnum):
    """State of comparison among compatible instruments."""

    SINGLE_INSTRUMENT = "single-instrument"
    AGREEMENT = "agreement"
    PARTIAL_DISAGREEMENT = "partial-disagreement"
    STRONG_DISAGREEMENT = "strong-disagreement"
    ABSTAIN = "abstain"


class AmbiguityBudgetStatus(StrEnum):
    """How unresolved uncertainty is preserved by a method."""

    UNASSESSED = "unassessed"
    PRESERVED = "preserved"
    CONSTRAINED = "constrained"
    EXCEEDED = "exceeded"


class ConfidenceSignal(StrEnum):
    """Signals an aggregation policy may explicitly read."""

    INSTRUMENT_PROBABILITY = "instrument-probability"
    CALIBRATION = "calibration"
    APPLICABILITY = "applicability"
    EXTRACTION_QUALITY = "extraction-quality"
    INTER_INSTRUMENT_AGREEMENT = "inter-instrument-agreement"
    SYSTEM_ABSTENTION = "system-abstention"
    AMBIGUITY_BUDGET = "ambiguity-budget"


class ForbiddenConfidenceOutput(StrEnum):
    """Outputs an aggregation component may not invent."""

    SCALAR_CONFIDENCE = "scalar-confidence"
    INVENTED_CALIBRATION = "invented-calibration"
    SUPPRESSED_DISAGREEMENT = "suppressed-disagreement"
    UNTRACEABLE_CONFIDENCE_SUMMARY = "untraceable-confidence-summary"


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class InstrumentProbability:
    """Probability-like output without a claim of calibration."""

    value: float | None
    source: InstrumentProbabilitySource | None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError("instrument probability must be between 0.0 and 1.0")
        if self.value is not None and self.source is None:
            raise ValueError("instrument probability source is required when value is present")
        if self.source is InstrumentProbabilitySource.DERIVED and not self.notes.strip():
            raise ValueError("derived instrument probability requires explanatory notes")


@dataclass(frozen=True, slots=True)
class Calibration:
    """Calibration evidence bounded to a declared domain."""

    status: CalibrationStatus
    method: str | None = None
    domain: str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_optional_text(self.method, "calibration method")
        _require_optional_text(self.domain, "calibration domain")
        _require_optional_text(self.evidence_ref, "calibration evidence_ref")
        if self.status is CalibrationStatus.UNKNOWN:
            if self.method is not None or self.domain is not None:
                raise ValueError("unknown calibration may not name a method or domain")
            return
        if self.method is None or self.domain is None or self.evidence_ref is None:
            raise ValueError(
                "estimated or validated calibration requires method, domain, and evidence_ref"
            )


@dataclass(frozen=True, slots=True)
class Applicability:
    """Applicability of an instrument or report to the analyzed content."""

    status: ApplicabilityStatus
    reasons: tuple[str, ...] = ()
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_unique(self.reasons, "applicability reasons")
        _require_optional_text(self.evidence_ref, "applicability evidence_ref")
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("applicability reasons must not be empty")
        if self.status is not ApplicabilityStatus.IN_DOMAIN and not self.reasons:
            raise ValueError("non-in-domain applicability requires at least one reason")


@dataclass(frozen=True, slots=True)
class ExtractionQuality:
    """Upstream extraction quality inherited by downstream measurements."""

    status: ExtractionQualityStatus
    issues: tuple[str, ...] = ()
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _require_unique(self.issues, "extraction issues")
        _require_optional_text(self.evidence_ref, "extraction evidence_ref")
        if any(not issue.strip() for issue in self.issues):
            raise ValueError("extraction issues must not be empty")
        if self.status is ExtractionQualityStatus.CLEAN and self.issues:
            raise ValueError("clean extraction may not contain issues")
        if self.status is not ExtractionQualityStatus.CLEAN and not self.issues:
            raise ValueError("non-clean extraction requires at least one issue")


@dataclass(frozen=True, slots=True)
class InterInstrumentAgreement:
    """Agreement state without inventing comparison evidence."""

    status: AgreementStatus
    participants: tuple[str, ...]
    metric: str | None = None
    value: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        _require_unique(self.participants, "agreement participants")
        if any(not participant.strip() for participant in self.participants):
            raise ValueError("agreement participants must not be empty")
        _require_optional_text(self.metric, "agreement metric")
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError("agreement value must be between 0.0 and 1.0")
        if self.status is AgreementStatus.SINGLE_INSTRUMENT:
            if len(self.participants) != 1:
                raise ValueError("single-instrument agreement requires one participant")
            if self.metric is not None or self.value is not None:
                raise ValueError("single-instrument agreement may not invent metric or value")
            return
        if len(self.participants) < 2:
            raise ValueError("multi-instrument agreement requires at least two participants")


@dataclass(frozen=True, slots=True)
class SystemAbstention:
    """Independent decision to withhold a measurement or report."""

    triggered: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_unique(self.reasons, "abstention reasons")
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("abstention reasons must not be empty")
        if self.triggered and not self.reasons:
            raise ValueError("triggered abstention requires at least one reason")
        if not self.triggered and self.reasons:
            raise ValueError("untriggered abstention may not contain reasons")


@dataclass(frozen=True, slots=True)
class AmbiguityBudget:
    """Descriptive preservation of unresolved uncertainty."""

    status: AmbiguityBudgetStatus
    preserved_uncertainties: tuple[str, ...] = ()
    forced_resolutions: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        _require_unique(self.preserved_uncertainties, "preserved uncertainties")
        _require_unique(self.forced_resolutions, "forced resolutions")
        if any(not item.strip() for item in self.preserved_uncertainties):
            raise ValueError("preserved uncertainties must not be empty")
        if any(not item.strip() for item in self.forced_resolutions):
            raise ValueError("forced resolutions must not be empty")
        if self.status is AmbiguityBudgetStatus.CONSTRAINED and not self.forced_resolutions:
            raise ValueError("constrained ambiguity requires at least one forced resolution")
        if self.status is AmbiguityBudgetStatus.EXCEEDED and not self.preserved_uncertainties:
            raise ValueError("exceeded ambiguity requires preserved uncertainty")


def required_abstention_reasons(
    applicability: ApplicabilityStatus,
    extraction_quality: ExtractionQualityStatus,
    agreement: AgreementStatus,
) -> tuple[str, ...]:
    """Return mandatory Phase 0 abstention reason codes."""

    reasons: list[str] = []
    if applicability is ApplicabilityStatus.OUT_OF_DOMAIN:
        reasons.append("out-of-domain")
    if extraction_quality is ExtractionQualityStatus.FAILED:
        reasons.append("extraction-failure")
    if agreement is AgreementStatus.STRONG_DISAGREEMENT:
        reasons.append("strong-disagreement")
    if agreement is AgreementStatus.ABSTAIN:
        reasons.append("agreement-abstain")
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class ConfidenceVector:
    """Canonical non-scalar confidence representation."""

    instrument_probability: InstrumentProbability
    calibration: Calibration
    applicability: Applicability
    extraction_quality: ExtractionQuality
    inter_instrument_agreement: InterInstrumentAgreement
    system_abstention: SystemAbstention
    ambiguity_budget: AmbiguityBudget

    def __post_init__(self) -> None:
        required = required_abstention_reasons(
            self.applicability.status,
            self.extraction_quality.status,
            self.inter_instrument_agreement.status,
        )
        missing = tuple(
            reason for reason in required if reason not in self.system_abstention.reasons
        )
        if missing:
            raise ValueError(
                "critical confidence state requires system abstention reasons: "
                + ", ".join(missing)
            )
        if required and not self.system_abstention.triggered:
            raise ValueError("critical confidence state must trigger system abstention")


@dataclass(frozen=True, slots=True)
class AggregationPolicy:
    """Explicit permissions and prohibitions for confidence aggregation."""

    policy_id: str
    policy_version: str
    allowed_confidence_signals: tuple[ConfidenceSignal, ...]
    abstention_trigger_signals: tuple[ConfidenceSignal, ...]
    forbidden_outputs: tuple[ForbiddenConfidenceOutput, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("aggregation policy identity fields must not be empty")
        if len(self.allowed_confidence_signals) != len(set(self.allowed_confidence_signals)):
            raise ValueError("allowed confidence signals must not contain duplicates")
        if len(self.abstention_trigger_signals) != len(set(self.abstention_trigger_signals)):
            raise ValueError("abstention trigger signals must not contain duplicates")
        if len(self.forbidden_outputs) != len(set(self.forbidden_outputs)):
            raise ValueError("forbidden outputs must not contain duplicates")
        if not set(self.abstention_trigger_signals).issubset(
            self.allowed_confidence_signals
        ):
            raise ValueError("abstention trigger signals must also be allowed inputs")
        if ForbiddenConfidenceOutput.SCALAR_CONFIDENCE not in self.forbidden_outputs:
            raise ValueError("Phase 0 aggregation policy must forbid scalar-confidence")
