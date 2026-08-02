import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).parents[1] / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def schema_registry() -> Registry:
    resources = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=schema_registry())


def confidence_vector() -> dict[str, Any]:
    return {
        "instrument_probability": {
            "value": 0.8,
            "source": "model-reported",
            "notes": "Synthetic probability; calibration is unknown.",
        },
        "calibration": {
            "status": "unknown",
            "method": None,
            "domain": None,
            "evidence_ref": None,
        },
        "applicability": {
            "status": "in-domain",
            "reasons": [],
            "evidence_ref": "dimension:sentiment_valence:0.1.0",
        },
        "extraction_quality": {
            "status": "clean",
            "issues": [],
            "evidence_ref": "content-item:content-001",
        },
        "inter_instrument_agreement": {
            "status": "single-instrument",
            "participants": ["synthetic.sentiment.a"],
            "metric": None,
            "value": None,
            "notes": "Only one analyzer has run.",
        },
        "system_abstention": {"triggered": False, "reasons": []},
        "ambiguity_budget": {
            "status": "preserved",
            "preserved_uncertainties": ["Calibration is unknown."],
            "forced_resolutions": [],
            "notes": "No scalar confidence was generated.",
        },
    }


def analysis_target() -> dict[str, Any]:
    return {
        "kind": "content-item",
        "content_id": "content-001",
        "start": 0,
        "end": 28,
        "extraction_ref": "content-item:content-001",
        "segmentation_id": None,
        "segment_id": None,
        "coordinate_system": "unicode_codepoint_half_open",
    }


def evidence_support() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method_id": None,
        "method_version": None,
        "notes": "Synthetic analyzer provides item-level output only.",
    }


def model_result() -> dict[str, Any]:
    return {
        "result_id": "result-001",
        "content_id": "content-001",
        "dimension_id": "sentiment_valence",
        "dimension_version": "0.1.0",
        "status": "success",
        "analyzer": {
            "analyzer_id": "synthetic.sentiment.a",
            "provider": "synthetic",
            "model_id": "fixture-model",
            "model_version": "1.0.0",
            "adapter_version": "1.0.0",
            "taxonomy_id": "sentiment.three-class",
            "taxonomy_version": "1.0.0",
        },
        "analysis_target": analysis_target(),
        "evidence_support": evidence_support(),
        "confidence": confidence_vector(),
        "raw_output": {"negative": 0.1, "neutral": 0.8, "positive": 0.1},
        "normalized_scores": [
            {
                "key": "valence",
                "value": 0.0,
                "lower_bound": -1.0,
                "upper_bound": 1.0,
            }
        ],
        "evidence_spans": [],
        "warnings": [],
        "errors": [],
        "duration_ms": 1.0,
        "configuration": {},
    }


def taxonomy_comparison() -> dict[str, Any]:
    return {
        "comparison_id": "taxonomy-comparison-001",
        "comparison_version": "0.1.0",
        "left": {
            "taxonomy_id": "sentiment.three-class",
            "taxonomy_version": "1.0.0",
        },
        "right": {
            "taxonomy_id": "sentiment.binary",
            "taxonomy_version": "1.0.0",
        },
        "relation": "partial-overlap",
        "display_mode": "side-by-side",
        "score_combination_permitted": False,
        "mapping_method_id": "mapping.sentiment-taxonomies",
        "mapping_method_version": "0.1.0",
        "evidence_ref": "protocol:taxonomy-mapping-001",
        "information_loss": ["Binary taxonomy has no native neutral class."],
        "notes": "Comparison preserves both native outputs.",
    }


def test_all_schemas_are_valid_draft_2020_12() -> None:
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        Draft202012Validator.check_schema(
            json.loads(path.read_text(encoding="utf-8"))
        )


def test_model_result_requires_structured_confidence() -> None:
    validator("model-result.schema.json").validate(model_result())


def test_model_result_requires_analysis_target() -> None:
    result = model_result()
    del result["analysis_target"]

    with pytest.raises(ValidationError):
        validator("model-result.schema.json").validate(result)


def test_model_result_requires_evidence_support() -> None:
    result = model_result()
    del result["evidence_support"]

    with pytest.raises(ValidationError):
        validator("model-result.schema.json").validate(result)


def test_unavailable_evidence_rejects_spans() -> None:
    result = model_result()
    result["evidence_spans"] = [{"start": 0, "end": 5}]

    with pytest.raises(ValidationError):
        validator("model-result.schema.json").validate(result)


def test_per_score_scalar_confidence_is_rejected() -> None:
    result = model_result()
    result["normalized_scores"][0]["confidence"] = 0.8

    with pytest.raises(ValidationError):
        validator("model-result.schema.json").validate(result)


def test_out_of_domain_requires_system_abstention() -> None:
    vector = confidence_vector()
    vector["applicability"] = {
        "status": "out-of-domain",
        "reasons": ["Unsupported domain."],
        "evidence_ref": None,
    }

    with pytest.raises(ValidationError):
        validator("confidence-vector.schema.json").validate(vector)


def test_taxonomy_comparison_forbids_score_combination() -> None:
    comparison = taxonomy_comparison()
    comparison["score_combination_permitted"] = True

    with pytest.raises(ValidationError):
        validator("taxonomy-comparison.schema.json").validate(comparison)


def test_partial_taxonomy_overlap_requires_information_loss() -> None:
    comparison = taxonomy_comparison()
    comparison["information_loss"] = []

    with pytest.raises(ValidationError):
        validator("taxonomy-comparison.schema.json").validate(comparison)


def test_report_surfaces_vector_and_forbids_scalar_explanation() -> None:
    report = {
        "report_id": "report-001",
        "specification_version": "0.1.0",
        "content_id": "content-001",
        "status": "complete",
        "model_results": [model_result()],
        "dimension_summaries": [
            {
                "dimension_id": "sentiment_valence",
                "dimension_version": "0.1.0",
                "status": "available",
                "included_result_ids": ["result-001"],
                "excluded_results": [],
                "scores": {"valence": 0.0},
                "agreement": confidence_vector()["inter_instrument_agreement"],
                "taxonomy_comparison_ids": ["taxonomy-comparison-001"],
            }
        ],
        "taxonomy_comparisons": [taxonomy_comparison()],
        "confidence": confidence_vector(),
        "aggregation_policy": {
            "policy_id": "phase-zero.report",
            "policy_version": "0.1.0",
            "allowed_confidence_signals": [
                "calibration",
                "applicability",
                "extraction-quality",
                "inter-instrument-agreement",
                "system-abstention",
                "ambiguity-budget",
            ],
            "abstention_trigger_signals": [
                "applicability",
                "extraction-quality",
                "inter-instrument-agreement",
            ],
            "forbidden_outputs": [
                "scalar-confidence",
                "invented-calibration",
                "suppressed-disagreement",
            ],
            "notes": "Instrument probabilities are not aggregated.",
        },
        "disagreement": [],
        "explanations": [],
        "confidence_explanation": {
            "method": "rule-based",
            "method_version": "0.1.0",
            "text": "Calibration is unknown; one analyzer participated.",
            "source_signals": ["calibration", "inter-instrument-agreement"],
            "scalar_confidence_generated": False,
        },
        "limitations": ["Calibration is unknown."],
        "created_at": "2026-08-02T18:00:00Z",
    }

    report_validator = validator("ctrt-report.schema.json")
    report_validator.validate(report)

    report["confidence_explanation"]["scalar_confidence_generated"] = True
    with pytest.raises(ValidationError):
        report_validator.validate(report)
