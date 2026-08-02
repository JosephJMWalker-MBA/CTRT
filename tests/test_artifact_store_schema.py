import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "schemas"
    / "experiment-bundle-manifest.schema.json"
)
HASHES = tuple(f"sha256:{character * 64}" for character in "abcdefg")


def _validator() -> Draft202012Validator:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _artifact(artifact_id: str, artifact_hash: str) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "artifact_hash": artifact_hash,
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }


def _manifest() -> dict[str, Any]:
    roles = (
        "plan",
        "candidate-eligibility",
        "environment",
        "result:0",
        "result:1",
        "comparison",
        "run-record",
    )
    return {
        "bundle_id": "run-001:record:artifact-bundle",
        "run_record_id": "run-001:record",
        "artifacts": [
            {
                "role": role,
                "artifact": _artifact(f"artifact-{index}", HASHES[index]),
            }
            for index, role in enumerate(roles)
        ],
    }


def test_complete_bundle_manifest_validates() -> None:
    _validator().validate(_manifest())


def test_bundle_manifest_requires_at_least_two_results() -> None:
    manifest = _manifest()
    manifest["artifacts"] = [
        item
        for item in manifest["artifacts"]
        if item["role"] != "result:1"
    ]

    with pytest.raises(ValidationError):
        _validator().validate(manifest)
