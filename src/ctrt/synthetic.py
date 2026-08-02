"""Deterministic fixture analyzers for validating workbench orchestration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

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
    InterInstrumentAgreement,
    SystemAbstention,
)
from ctrt.contracts import (
    AnalyzerIdentity,
    ContentItem,
    EvidenceSpan,
    ModelResult,
    NormalizedScore,
    ResultStatus,
)
from ctrt.measurement import AnalysisTarget, EvidenceSupport, EvidenceSupportStatus


class SignalSelection(StrEnum):
    """Which matching fixture signal determines the synthetic output."""

    FIRST = "first"
    LAST = "last"


@dataclass(frozen=True, slots=True)
class PositionalSentimentFixture:
    """Choose the first or last exact fixture token as a synthetic measurement."""

    analyzer_id: str
    selection: SignalSelection
    dimension_id: str = "sentiment_valence"
    dimension_version: str = "0.1.0"

    def __post_init__(self) -> None:
        if not self.analyzer_id.strip():
            raise ValueError("synthetic analyzer_id must not be empty")

    @property
    def implementation_revision(self) -> str:
        """Return the immutable fixture implementation revision."""

        return f"ctrt-fixture-{self.selection.value}@0.1.0"

    @property
    def execution_configuration(self) -> Mapping[str, object]:
        """Return the complete deterministic fixture configuration."""

        return {
            "selection": self.selection.value,
            "positive_token": "good",
            "negative_token": "bad",
            "case_sensitive": False,
        }

    @property
    def identity(self) -> AnalyzerIdentity:
        """Return a complete immutable fixture identity."""

        return AnalyzerIdentity(
            analyzer_id=self.analyzer_id,
            provider="ctrt.synthetic",
            model_id=f"positional-sentiment-{self.selection.value}",
            model_version="0.1.0",
            adapter_version="0.1.0",
            taxonomy_id="sentiment.synthetic.three-class",
            taxonomy_version="0.1.0",
        )

    def analyze(self, content: ContentItem) -> ModelResult:
        """Return a deterministic result without machine-learning dependencies."""

        target = AnalysisTarget.for_content_item(
            content_id=content.content_id,
            content_length=len(content.text),
            extraction_ref=f"content-item:{content.content_id}",
        )
        matches = tuple(re.finditer(r"\b(good|bad)\b", content.text, flags=re.IGNORECASE))
        if content.language not in {None, "en"}:
            return self._abstained_result(
                content=content,
                target=target,
                reason="out-of-domain",
                applicability=Applicability(
                    status=ApplicabilityStatus.OUT_OF_DOMAIN,
                    reasons=("Synthetic fixture is declared only for English text.",),
                    evidence_ref="synthetic-workbench:fixture-domain-v1",
                ),
                raw_output={"matches": [], "selection": self.selection.value},
            )
        if not matches:
            return self._abstained_result(
                content=content,
                target=target,
                reason="no-fixture-signal",
                applicability=Applicability(
                    status=ApplicabilityStatus.UNKNOWN,
                    reasons=("No exact 'good' or 'bad' fixture token was present.",),
                    evidence_ref="synthetic-workbench:fixture-domain-v1",
                ),
                raw_output={"matches": [], "selection": self.selection.value},
            )

        selected = matches[0] if self.selection is SignalSelection.FIRST else matches[-1]
        token = selected.group(1).lower()
        valence = 1.0 if token == "good" else -1.0
        return ModelResult(
            result_id=f"{content.content_id}:{self.analyzer_id}:0.1.0",
            content_id=content.content_id,
            dimension_id=self.dimension_id,
            dimension_version=self.dimension_version,
            status=ResultStatus.SUCCESS,
            analyzer=self.identity,
            analysis_target=target,
            evidence_support=EvidenceSupport(
                status=EvidenceSupportStatus.PROVIDED_DETERMINISTIC,
                method_id="ctrt.synthetic.positional-token-selection",
                method_version="0.1.0",
                notes="The selected exact token directly determines the fixture output.",
            ),
            confidence=self._confidence(
                analyzer_id=self.analyzer_id,
                target=target,
                applicability=Applicability(
                    status=ApplicabilityStatus.IN_DOMAIN,
                    evidence_ref="synthetic-workbench:fixture-domain-v1",
                ),
                abstention=SystemAbstention(triggered=False),
            ),
            raw_output={
                "selection": self.selection.value,
                "selected_token": token,
                "selected_start": selected.start(),
                "selected_end": selected.end(),
                "match_count": len(matches),
            },
            normalized_scores=(
                NormalizedScore(
                    key="valence",
                    value=valence,
                    lower_bound=-1.0,
                    upper_bound=1.0,
                ),
            ),
            evidence_spans=(
                EvidenceSpan(
                    start=selected.start(),
                    end=selected.end(),
                    label=token,
                    score=1.0,
                ),
            ),
            warnings=(
                "Synthetic fixture ignores all content except exact 'good' and 'bad' tokens.",
            ),
            duration_ms=0.0,
            configuration=self.execution_configuration,
        )

    def _abstained_result(
        self,
        *,
        content: ContentItem,
        target: AnalysisTarget,
        reason: str,
        applicability: Applicability,
        raw_output: dict[str, object],
    ) -> ModelResult:
        abstention = SystemAbstention(triggered=True, reasons=(reason,))
        return ModelResult(
            result_id=f"{content.content_id}:{self.analyzer_id}:0.1.0",
            content_id=content.content_id,
            dimension_id=self.dimension_id,
            dimension_version=self.dimension_version,
            status=ResultStatus.ABSTAINED,
            analyzer=self.identity,
            analysis_target=target,
            evidence_support=EvidenceSupport(
                status=EvidenceSupportStatus.UNAVAILABLE,
                notes="No fixture measurement was emitted.",
            ),
            confidence=self._confidence(
                analyzer_id=self.analyzer_id,
                target=target,
                applicability=applicability,
                abstention=abstention,
            ),
            raw_output=raw_output,
            warnings=("Synthetic analyzer abstained without inventing a score.",),
            duration_ms=0.0,
            configuration=self.execution_configuration,
        )

    @staticmethod
    def _confidence(
        *,
        analyzer_id: str,
        target: AnalysisTarget,
        applicability: Applicability,
        abstention: SystemAbstention,
    ) -> ConfidenceVector:
        return ConfidenceVector(
            instrument_probability=InstrumentProbability(
                value=None,
                source=None,
                notes="This deterministic fixture emits no probability-like value.",
            ),
            calibration=Calibration(status=CalibrationStatus.UNKNOWN),
            applicability=applicability,
            extraction_quality=ExtractionQuality(
                status=ExtractionQualityStatus.CLEAN,
                evidence_ref=target.extraction_ref,
            ),
            inter_instrument_agreement=InterInstrumentAgreement(
                status=AgreementStatus.SINGLE_INSTRUMENT,
                participants=(analyzer_id,),
                notes="Agreement is computed only in a separate comparison record.",
            ),
            system_abstention=abstention,
            ambiguity_budget=AmbiguityBudget(
                status=AmbiguityBudgetStatus.PRESERVED,
                preserved_uncertainties=(
                    "Fixture output has no demonstrated relationship to human sentiment judgment.",
                ),
                notes="The fixture exists only to exercise CTRT contracts.",
            ),
        )


def first_signal_fixture() -> PositionalSentimentFixture:
    """Create the canonical first-match fixture analyzer."""

    return PositionalSentimentFixture(
        analyzer_id="synthetic.sentiment.first-signal",
        selection=SignalSelection.FIRST,
    )


def last_signal_fixture() -> PositionalSentimentFixture:
    """Create the canonical last-match fixture analyzer."""

    return PositionalSentimentFixture(
        analyzer_id="synthetic.sentiment.last-signal",
        selection=SignalSelection.LAST,
    )
