from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ctrt.eligibility import evaluate_dimension_eligibility

DIMENSION_DIR = Path(__file__).parents[1] / "docs" / "dimensions"


def _load_records() -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for path in sorted(DIMENSION_DIR.glob("*.json")):
        record = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        dimension_id = record["dimension_id"]
        assert isinstance(dimension_id, str)
        assert dimension_id not in records
        records[dimension_id] = record
    return records


def test_initial_profile_has_expected_dimensions() -> None:
    records = _load_records()

    assert set(records) == {
        "sentiment_valence",
        "emotion_profile",
        "toxicity_indicators",
        "emotional_intensity",
    }


def test_three_dimensions_pass_experimental_eligibility_gate() -> None:
    records = _load_records()

    for dimension_id in (
        "sentiment_valence",
        "emotion_profile",
        "toxicity_indicators",
    ):
        decision = evaluate_dimension_eligibility(
            records[dimension_id],
            analyzer_dimension_id=dimension_id,
        )
        assert decision.allowed, decision.reasons


def test_emotional_intensity_is_explicitly_blocked() -> None:
    record = _load_records()["emotional_intensity"]
    decision = evaluate_dimension_eligibility(
        record,
        analyzer_dimension_id="emotional_intensity",
    )

    assert not decision.allowed
    assert "dimension is not eligible for an experimental report" in decision.reasons
    assert "dimension output structure is undetermined" in decision.reasons


def test_mismatched_analyzer_cannot_borrow_another_dimensions_record() -> None:
    record = _load_records()["sentiment_valence"]
    decision = evaluate_dimension_eligibility(
        record,
        analyzer_dimension_id="toxicity_indicators",
    )

    assert not decision.allowed
    assert any("does not match" in reason for reason in decision.reasons)


def test_no_phase_zero_dimension_can_feed_an_overall_rating() -> None:
    for record in _load_records().values():
        aggregation = record["aggregation"]
        assert isinstance(aggregation, dict)
        assert aggregation["may_contribute_to_overall_rating"] is False
