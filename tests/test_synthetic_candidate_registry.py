import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "schemas" / "candidate-registry.schema.json"
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"


def load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_synthetic_registry_matches_candidate_schema() -> None:
    Draft202012Validator(
        load(SCHEMA_PATH),
        format_checker=FormatChecker(),
    ).validate(load(REGISTRY_PATH))


def test_synthetic_registry_is_accepted_pinned_and_fixture_only() -> None:
    registry = load(REGISTRY_PATH)

    assert registry["status"] == "accepted"
    for candidate in registry["candidates"]:
        assert candidate["technology_type"] == "deterministic_fixture"
        assert candidate["status"] == "eligible_for_evaluation"
        assert candidate["authorized_analyzer_ids"]
        assert candidate["revision_policy"]["pin_required"] is True
        assert candidate["revision_policy"]["pinned_revision"]
        assert candidate["license_review"]["status"] == "verified"
