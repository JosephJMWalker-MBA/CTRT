import pytest

from ctrt.confidence import (
    AggregationPolicy,
    AgreementStatus,
    AmbiguityBudget,
    AmbiguityBudgetStatus,
    Applicability,
    ApplicabilityStatus,
    Calibration,
    CalibrationStatus,
    ConfidenceSignal,
    ConfidenceVector,
    ExtractionQuality,
    ExtractionQualityStatus,
    ForbiddenConfidenceOutput,
    InstrumentProbability,
    InstrumentProbabilitySource,
    InterInstrumentAgreement,
    SystemAbstention,
    required_abstention_reasons,
)


def base_vector(
    *,
    applicability: ApplicabilityStatus = ApplicabilityStatus.IN_DOMAIN,
    extraction: ExtractionQualityStatus = ExtractionQualityStatus.CLEAN,
    agreement: AgreementStatus = AgreementStatus.SINGLE_INSTRUMENT,
    abstention_reasons: tuple[str, ...] = (),
) -> ConfidenceVector:
    participants = (
        ("analyzer-a",)
        if agreement is AgreementStatus.SINGLE_INSTRUMENT
        else ("analyzer-a", "analyzer-b")
    )
    applicability_reasons = (
        ()
        if applicability is ApplicabilityStatus.IN_DOMAIN
        else ("Content does not fit the declared domain boundary.",)
    )
    extraction_issues = (
        () if extraction is ExtractionQualityStatus.CLEAN else ("truncated",)
    )
    return ConfidenceVector(
        instrument_probability=InstrumentProbability(
            value=0.97,
            source=InstrumentProbabilitySource.MODEL_REPORTED,
            notes="Probability is not treated as calibrated.",
        ),
        calibration=Calibration(status=CalibrationStatus.UNKNOWN),
        applicability=Applicability(
            status=applicability,
            reasons=applicability_reasons,
        ),
        extraction_quality=ExtractionQuality(
            status=extraction,
            issues=extraction_issues,
        ),
        inter_instrument_agreement=InterInstrumentAgreement(
            status=agreement,
            participants=participants,
        ),
        system_abstention=SystemAbstention(
            triggered=bool(abstention_reasons),
            reasons=abstention_reasons,
        ),
        ambiguity_budget=AmbiguityBudget(
            status=AmbiguityBudgetStatus.PRESERVED,
            preserved_uncertainties=("Calibration is unknown.",),
        ),
    )


def test_high_probability_does_not_override_out_of_domain_abstention() -> None:
    with pytest.raises(ValueError, match="out-of-domain"):
        base_vector(applicability=ApplicabilityStatus.OUT_OF_DOMAIN)

    vector = base_vector(
        applicability=ApplicabilityStatus.OUT_OF_DOMAIN,
        abstention_reasons=("out-of-domain",),
    )

    assert vector.instrument_probability.value == 0.97
    assert vector.system_abstention.triggered


def test_failed_extraction_forces_abstention() -> None:
    reasons = required_abstention_reasons(
        ApplicabilityStatus.IN_DOMAIN,
        ExtractionQualityStatus.FAILED,
        AgreementStatus.SINGLE_INSTRUMENT,
    )

    assert reasons == ("extraction-failure",)
    vector = base_vector(
        extraction=ExtractionQualityStatus.FAILED,
        abstention_reasons=reasons,
    )
    assert vector.system_abstention.triggered


def test_strong_disagreement_forces_abstention() -> None:
    vector = base_vector(
        agreement=AgreementStatus.STRONG_DISAGREEMENT,
        abstention_reasons=("strong-disagreement",),
    )

    assert vector.inter_instrument_agreement.value is None
    assert vector.system_abstention.triggered


def test_single_instrument_cannot_invent_agreement_value() -> None:
    with pytest.raises(ValueError, match="may not invent"):
        InterInstrumentAgreement(
            status=AgreementStatus.SINGLE_INSTRUMENT,
            participants=("analyzer-a",),
            metric="cosine-similarity",
            value=0.99,
        )


def test_derived_probability_requires_notes() -> None:
    with pytest.raises(ValueError, match="requires explanatory notes"):
        InstrumentProbability(
            value=0.5,
            source=InstrumentProbabilitySource.DERIVED,
        )


def test_unknown_calibration_cannot_imply_a_domain_method() -> None:
    with pytest.raises(ValueError, match="may not name"):
        Calibration(
            status=CalibrationStatus.UNKNOWN,
            method="temperature-scaling",
            domain="news",
        )


def test_report_level_probability_may_remain_null() -> None:
    probability = InstrumentProbability(
        value=None,
        source=None,
        notes="No report-level probability was derived.",
    )

    assert probability.value is None
    assert probability.source is None


def test_constrained_ambiguity_requires_forced_resolution_record() -> None:
    with pytest.raises(ValueError, match="forced resolution"):
        AmbiguityBudget(status=AmbiguityBudgetStatus.CONSTRAINED)


def test_phase_zero_policy_must_forbid_scalar_confidence() -> None:
    with pytest.raises(ValueError, match="forbid scalar-confidence"):
        AggregationPolicy(
            policy_id="phase-zero.report",
            policy_version="0.1.0",
            allowed_confidence_signals=(ConfidenceSignal.APPLICABILITY,),
            abstention_trigger_signals=(ConfidenceSignal.APPLICABILITY,),
            forbidden_outputs=(ForbiddenConfidenceOutput.INVENTED_CALIBRATION,),
        )


def test_abstention_trigger_must_be_an_allowed_input() -> None:
    with pytest.raises(ValueError, match="allowed inputs"):
        AggregationPolicy(
            policy_id="phase-zero.report",
            policy_version="0.1.0",
            allowed_confidence_signals=(ConfidenceSignal.APPLICABILITY,),
            abstention_trigger_signals=(ConfidenceSignal.EXTRACTION_QUALITY,),
            forbidden_outputs=(ForbiddenConfidenceOutput.SCALAR_CONFIDENCE,),
        )
