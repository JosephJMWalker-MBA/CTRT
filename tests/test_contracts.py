from dataclasses import FrozenInstanceError

import pytest

from ctrt.contracts import (
    Analyzer,
    AnalyzerIdentity,
    ContentItem,
    ModelResult,
    NormalizedScore,
    ResultStatus,
    SourceType,
)


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


def content() -> ContentItem:
    return ContentItem(
        content_id="content-001",
        text="A bounded synthetic example.",
        source_type=SourceType.RAW_TEXT,
        content_hash="sha256:synthetic",
        language="en",
    )


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
                raw_output={"negative": 0.1, "neutral": 0.8, "positive": 0.1},
                normalized_scores=(
                    NormalizedScore(
                        key="valence",
                        value=0.0,
                        lower_bound=-1.0,
                        upper_bound=1.0,
                        confidence=0.8,
                    ),
                ),
            )

    analyzer = SyntheticAnalyzer()

    assert isinstance(analyzer, Analyzer)
    assert analyzer.analyze(content()).status is ResultStatus.SUCCESS
