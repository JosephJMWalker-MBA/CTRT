from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "schemas" / "candidate-registry.schema.json"
REGISTRY_PATH = ROOT / "docs" / "candidates" / "initial-registry.v0.1.0.json"


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _candidates() -> dict[str, dict[str, Any]]:
    registry = _load_json(REGISTRY_PATH)
    candidates = cast(list[dict[str, Any]], registry["candidates"])
    return {cast(str, candidate["candidate_id"]): candidate for candidate in candidates}


def test_initial_candidate_registry_matches_schema() -> None:
    schema = _load_json(SCHEMA_PATH)
    registry = _load_json(REGISTRY_PATH)

    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(registry)


def test_candidate_ids_are_unique() -> None:
    registry = _load_json(REGISTRY_PATH)
    candidates = cast(list[dict[str, Any]], registry["candidates"])
    candidate_ids = [cast(str, candidate["candidate_id"]) for candidate in candidates]

    assert len(candidate_ids) == len(set(candidate_ids))


def test_registry_does_not_preselect_any_technology() -> None:
    for candidate in _candidates().values():
        assert candidate["status"] != "selected_for_domain"


def test_analyzers_declare_at_least_one_dimension() -> None:
    for candidate in _candidates().values():
        if candidate["capability_type"] == "analyzer":
            assert candidate["dimensions"]


def test_newspaper_candidates_preserve_legacy_and_current_distinction() -> None:
    candidates = _candidates()

    assert candidates["extraction.newspaper3k"]["status"] == "proposed"
    assert candidates["extraction.newspaper4k"]["status"] == "eligible_for_evaluation"


def test_transcript_acquisition_is_deferred() -> None:
    candidate = _candidates()["transcript.youtube-transcript-api"]

    assert candidate["status"] == "deferred"
    assert candidate["capability_type"] == "transcript_acquisition"


def test_every_executable_candidate_requires_revision_pinning() -> None:
    for candidate in _candidates().values():
        if candidate["status"] == "eligible_for_evaluation":
            assert candidate["revision_policy"]["pin_required"] is True
            assert candidate["revision_policy"]["pinned_revision"] is None
