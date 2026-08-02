from dataclasses import FrozenInstanceError

import pytest

from ctrt.confidence import (
    AgreementStatus,
    AmbiguityBudget,
    AmbiguityBudgetStatus,
    Applicability,
    ApplicabilityStatus,
    Calibration,
    CalibrationStatus,
    ConfidenceVector,
    ExtractionQuality,
    ExtractionQualityStatus,
    InstrumentProbability,
    InstrumentProbabilitySource,
    InterInstrumentAgreement,
    SystemAbstention,
)
from ctrt.contracts import (
    Analyzer,
    AnalyzerIdentity,
    ContentItem,
    EvidenceSpan,
    ModelResult,
    NormalizedScore,
    ResultStatus,
    SourceType,
)
from ctrt.measurement import AnalysisTarget, EvidenceSupport, EvidenceSupportStatus

EXTRACTION_REF = "content-item:content-001"


def identity() -> AnalyzerIdentity:
    return AnalyzerIdentity(
        analyzer_id="synthetic.sentiment.a",
        provider="synthetic",
        model_id="fixture-model",
        model_version="1.0.0",
        adapter_version="1.0.0",
        taxonomy_id="sentiment.three-class",
        taxonomy_version="1.0.0",
    )


def confidence(
    *,
    out_of_domain: bool = False,
    extraction_ref: str = EXTRACTION_REF,
) -> ConfidenceVector:
    reasons = ("out-of-domain",) if out_of_domain else ()
    return ConfidenceVector(
        instrument_probability=InstrumentProbability(
            value=0.8,
            source=InstrumentProbabilitySource.MODEL_REPORTED,
            notes="Synthetic class probability.",
        ),
        calibration=Calibration(status=CalibrationStatus.UNKNOWN),
        applicability=Applicability(
            status=(
                ApplicabilityStatus.OUT_OF_DOMAIN
                if out_of_domain
                else ApplicabilityStatus.IN_DOMAIN
            ),
            reasons=("Synthetic content is outside the declared domain.",)
            if out_of_domain
            else (),
        ),
        extraction_quality=ExtractionQuality(
            status=ExtractionQualityStatus.CLEAN,
            evidence_ref=extraction_ref,
        ),
        inter_instrument_agreement=InterInstrumentAgreement(
            status=AgreementStatus.SINGLE_INSTRUMENT,
            participants=("synthetic.sentiment.a",),
            notes="Only one instrument has run.",
        ),
        system_abstention=SystemAbstention(
            triggered=out_of_domain,
            reasons=reasons,
        ),
        ambiguity_budget=AmbiguityBudget(
            status=AmbiguityBudgetStatus.PRESERVED,
            preserved_uncertainties=("Calibration is unknown.",),
        ),
    )


def content() -> ContentItem:
    return ContentItem(
        content_id="content-001",
        text="A bounded synthetic example.",
        source_type=SourceType.RAW_TEXT,
        content_hash="sha256:synthetic",
        language="en",
    )


def target(*, extraction_ref: str = EXTRACTION_REF) -> AnalysisTarget:
    item = content()
    return AnalysisTarget.for_content_item(
        content_id=item.content_id,
        content_length=len(item.text),
        extraction_ref=extraction_ref,
    )


def unavailable_evidence() -> EvidenceSupport:
    return EvidenceSupport(status=EvidenceSupportStatus.UNAVAILABLE)


def test_content_item_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="text must not be empty"):
        ContentItem(
            content_id="content-001",
            text="  ",
            source_type=SourceType.RAW_TEXT,
            content_hash="sha256:synthetic",
        )


def test_normalized_score_enforces_declared_bounds() -> None:
    with pytest.raises(ValueError, match="declared bounds"):
        NormalizedScore(
            key="valence",
            value=1.2,
            lower_bound=-1.0,
            upper_bound=1.0,
        )


def test_failed_result_requires_an_error() -> None:
    with pytest.raises(ValueError, match="at least one error"):
        ModelResult(
            result_id="result-001",
            content_id="content-001",
            dimension_id="sentiment.valence",
            dimension_version="0.1.0",
            status=ResultStatus.FAILED,
            analyzer=identity(),
            analysis_target=target(),
            evidence_support=unavailable_evidence(),
            confidence=confidence(),
            raw_output={},
        )


def test_abstained_result_cannot_contain_normalized_scores() -> None:
    with pytest.raises(ValueError, match="may not contain normalized scores"):
        ModelResult(
            result_id="result-001",
            content_id="content-001",
            dimension_id="sentiment.valence",
            dimension_version="0.1.0",
            status=ResultStatus.ABSTAINED,
            analyzer=identity(),
            analysis_target=target(),
            evidence_support=unavailable_evidence(),
            confidence=confidence(out_of_domain=True),
            raw_output={"reason": "outside evaluated domain"},
            normalized_scores=(
                NormalizedScore(
                    key="valence",
                    value=0.0,
                    lower_bound=-1.0,
                    upper_bound=1.0,
                ),
            ),
        )


def test_triggered_abstention_rejects_success_status() -> None:
    with pytest.raises(ValueError, match="requires abstained or failed"):
        ModelResult(
            result_id="result-001",
            content_id="content-001",
            dimension_id="sentiment.valence",
            dimension_version="0.1.0",
            status=ResultStatus.SUCCESS,
            analyzer=identity(),
            analysis_target=target(),
            evidence_support=unavailable_evidence(),
            confidence=confidence(out_of_domain=True),
            raw_output={},
        )


def test_result_requires_matching_extraction_reference() -> None:
    with pytest.raises(ValueError, match="extraction evidence_ref must match"):
        ModelResult(
            result_id="result-001",
            content_id="content-001",
            dimension_id="sentiment.valence",
            dimension_version="0.1.0",
            status=ResultStatus.SUCCESS,
            analyzer=identity(),
            analysis_target=target(extraction_ref="extraction:source-a"),
            evidence_support=unavailable_evidence(),
            confidence=confidence(extraction_ref="extraction:source-b"),
            raw_output={},
        )


def test_unavailable_evidence_rejects_spans() -> None:
    with pytest.raises(ValueError, match="unavailable evidence"):
        ModelResult(
            result_id="result-001",
            content_id="content-001",
            dimension_id="sentiment.valence",
            dimension_version="0.1.0",
            status=ResultStatus.SUCCESS,
            analyzer=identity(),
            analysis_target=target(),
            evidence_support=unavailable_evidence(),
            confidence=confidence(),
            raw_output={},
            evidence_spans=(EvidenceSpan(start=0, end=1),),
        )


def test_evidence_span_must_fall_within_target() -> None:
    with pytest.raises(ValueError, match="within the analysis target"):
        ModelResult(
            result_id="result-001",
            content_id="content-001",
            dimension_id="sentiment.valence",
            dimension_version="0.1.0",
            status=ResultStatus.SUCCESS,
            analyzer=identity(),
            analysis_target=target(),
            evidence_support=EvidenceSupport(
                status=EvidenceSupportStatus.PROVIDED_NATIVE
            ),
            confidence=confidence(),
            raw_output={},
            evidence_spans=(EvidenceSpan(start=0, end=100),),
        )


def test_contract_records_are_immutable() -> None:
    item = content()

    with pytest.raises(FrozenInstanceError):
        item.text = "changed"  # type: ignore[misc]


def test_runtime_protocol_accepts_conforming_analyzer() -> None:
    class SyntheticAnalyzer:
        @property
        def dimension_id(self) -> str:
            return "sentiment.valence"

        @property
        def implementation_revision(self) -> str:
            return "synthetic-analyzer@1.0.0"

        @property
        def execution_configuration(self) -> dict[str, object]:
            return {"mode": "synthetic"}

        @property
        def identity(self) -> AnalyzerIdentity:
            return identity()

        def analyze(self, item: ContentItem) -> ModelResult:
            return ModelResult(
                result_id="result-001",
                content_id=item.content_id,
                dimension_id=self.dimension_id,
                dimension_version="0.1.0",
                status=ResultStatus.SUCCESS,
                analyzer=self.identity,
                analysis_target=AnalysisTarget.for_content_item(
                    content_id=item.content_id,
                    content_length=len(item.text),
                    extraction_ref=EXTRACTION_REF,
                ),
                evidence_support=unavailable_evidence(),
                confidence=confidence(),
                raw_output={"negative": 0.1, "neutral": 0.8, "positive": 0.1},
                normalized_scores=(
                    NormalizedScore(
                        key="valence",
                        value=0.0,
                        lower_bound=-1.0,
                        upper_bound=1.0,
                    ),
                ),
                configuration=self.execution_configuration,
            )

    analyzer = SyntheticAnalyzer()

    assert isinstance(analyzer, Analyzer)
    assert analyzer.analyze(content()).status is ResultStatus.SUCCESS
