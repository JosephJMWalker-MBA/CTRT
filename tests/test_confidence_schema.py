import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "confidence-vector.schema.json"


def validator() -> Draft202012Validator:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def confidence_vector() -> dict[str, Any]:
    return {
        "instrument_probability": {
            "value": None,
            "source": None,
            "notes": "No probability was available.",
        },
        "calibration": {
            "status": "unknown",
            "method": None,
            "domain": None,
            "evidence_ref": None,
        },
        "applicability": {
            "status": "unknown",
            "reasons": ["Applicability has not been evaluated."],
            "evidence_ref": None,
        },
        "extraction_quality": {
            "status": "clean",
            "issues": [],
            "evidence_ref": "content-item:content-001",
        },
        "inter_instrument_agreement": {
            "status": "single-instrument",
            "participants": ["synthetic.analyzer"],
            "metric": None,
            "value": None,
            "notes": "Only one analyzer participated.",
        },
        "system_abstention": {"triggered": False, "reasons": []},
        "ambiguity_budget": {
            "status": "unassessed",
            "preserved_uncertainties": [],
            "forced_resolutions": [],
            "notes": "Ambiguity has not been assessed.",
        },
    }


@pytest.mark.parametrize(
    "signal",
    [
        "instrument_probability",
        "calibration",
        "applicability",
        "extraction_quality",
        "inter_instrument_agreement",
        "system_abstention",
        "ambiguity_budget",
    ],
)
def test_every_confidence_signal_is_required(signal: str) -> None:
    vector = confidence_vector()
    del vector[signal]

    with pytest.raises(ValidationError):
        validator().validate(vector)


def test_scalar_confidence_cannot_be_added_to_vector() -> None:
    vector = confidence_vector()
    vector["confidence"] = 0.9

    with pytest.raises(ValidationError):
        validator().validate(vector)
