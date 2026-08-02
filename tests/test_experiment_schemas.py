import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).parents[1] / "schemas"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
HASH_D = "sha256:" + "d" * 64
HASH_E = "sha256:" + "e" * 64


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
    return Draft202012Validator(
        schema,
        registry=schema_registry(),
        format_checker=FormatChecker(),
    )


def artifact(artifact_id: str, artifact_hash: str) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "artifact_version": "0.1.0",
        "artifact_hash": artifact_hash,
    }


def instrument(candidate_id: str, analyzer_id: str, artifact_hash: str) -> dict[str, str]:
    return {
        "candidate_id": candidate_id,
        "analyzer_id": analyzer_id,
        "dimension_id": "sentiment_valence",
        "implementation_revision": "fixture@0.1.0",
        "adapter_version": "0.1.0",
        "configuration_hash": artifact_hash,
    }


def experiment_plan() -> dict[str, Any]:
    return {
        "experiment_id": "experiment.synthetic-disagreement",
        "experiment_version": "0.1.0",
        "status": "frozen",
        "research_question": "Can successful results coexist with comparison abstention?",
        "protocol_ref": artifact("protocol.synthetic-workbench", HASH_A),
        "candidate_registry_ref": artifact("registry.synthetic-fixtures", HASH_B),
        "corpus_ref": artifact("corpus.synthetic-vocabulary", HASH_C),
        "content_ids": ["content-001"],
        "dimension_ids": ["sentiment_valence"],
        "instrument_revisions": [
            instrument(
                "fixture.first-signal",
                "synthetic.sentiment.first-signal",
                HASH_D,
            ),
            instrument(
                "fixture.last-signal",
                "synthetic.sentiment.last-signal",
                HASH_E,
            ),
        ],
        "metrics": [
            {"metric_id": "signed-valence-agreement", "metric_version": "0.1.0"}
        ],
        "exclusion_rules": ["Exclude content outside the declared fixture domain."],
        "stopping_rules": ["Stop after all declared runs complete."],
        "created_at": "2026-08-02T20:00:00Z",
    }


def execution_environment() -> dict[str, str]:
    return {
        "environment_id": "environment.synthetic-ci",
        "environment_version": "0.1.0",
        "python_version": "3.11",
        "operating_system": "Ubuntu 24.04",
        "architecture": "x86_64",
        "dependency_lock_hash": HASH_A,
        "runtime_configuration_hash": HASH_B,
        "hardware_profile": "GitHub-hosted CPU runner",
    }


def run_record() -> dict[str, Any]:
    plan = experiment_plan()
    first_id = "content-001:synthetic.sentiment.first-signal:0.1.0"
    last_id = "content-001:synthetic.sentiment.last-signal:0.1.0"
    return {
        "record_id": "run-001:record",
        "experiment_plan_ref": artifact(plan["experiment_id"], HASH_C),
        "candidate_eligibility_ref": artifact(
            "experiment.synthetic-disagreement:candidate-eligibility",
            HASH_B,
        ),
        "workbench_run_id": "run-001",
        "status": "abstained",
        "environment": execution_environment(),
        "content_id": "content-001",
        "instrument_revisions": plan["instrument_revisions"],
        "result_artifacts": [
            {
                "result_id": first_id,
                "analyzer_id": "synthetic.sentiment.first-signal",
                "content_id": "content-001",
                "status": "success",
                "artifact_hash": HASH_D,
            },
            {
                "result_id": last_id,
                "analyzer_id": "synthetic.sentiment.last-signal",
                "content_id": "content-001",
                "status": "success",
                "artifact_hash": HASH_E,
            },
        ],
        "comparison_artifact": {
            "comparison_id": "run-001:comparison",
            "content_id": "content-001",
            "status": "abstained",
            "result_ids": [first_id, last_id],
            "artifact_hash": HASH_A,
        },
        "started_at": "2026-08-02T20:01:00Z",
        "completed_at": "2026-08-02T20:01:01Z",
    }


def test_frozen_plan_and_run_record_validate() -> None:
    validator("experiment-plan.schema.json").validate(experiment_plan())
    validator("experiment-run-record.schema.json").validate(run_record())


def test_frozen_plan_requires_protocol_registry_and_corpus_versions() -> None:
    plan = experiment_plan()
    del plan["candidate_registry_ref"]

    with pytest.raises(ValidationError):
        validator("experiment-plan.schema.json").validate(plan)


def test_frozen_plan_requires_two_pinned_instruments() -> None:
    plan = experiment_plan()
    plan["instrument_revisions"] = plan["instrument_revisions"][:1]

    with pytest.raises(ValidationError):
        validator("experiment-plan.schema.json").validate(plan)


def test_instrument_revision_requires_dimension_identity() -> None:
    plan = experiment_plan()
    del plan["instrument_revisions"][0]["dimension_id"]

    with pytest.raises(ValidationError):
        validator("experiment-plan.schema.json").validate(plan)


def test_scalar_confidence_metric_is_rejected() -> None:
    plan = experiment_plan()
    plan["metrics"] = [{"metric_id": "scalar-confidence", "metric_version": "0.1.0"}]

    with pytest.raises(ValidationError):
        validator("experiment-plan.schema.json").validate(plan)


def test_run_record_requires_candidate_eligibility_reference() -> None:
    record = run_record()
    del record["candidate_eligibility_ref"]

    with pytest.raises(ValidationError):
        validator("experiment-run-record.schema.json").validate(record)


def test_run_record_preserves_abstained_result_status() -> None:
    record = run_record()
    record["result_artifacts"][0]["status"] = "abstained"

    validator("experiment-run-record.schema.json").validate(record)
    assert record["result_artifacts"][0]["status"] == "abstained"


def test_run_record_rejects_unhashed_or_overwritten_result_reference() -> None:
    record = run_record()
    record["result_artifacts"][0]["artifact_hash"] = "mutable-result"

    with pytest.raises(ValidationError):
        validator("experiment-run-record.schema.json").validate(record)


def test_execution_environment_requires_dependency_and_runtime_hashes() -> None:
    environment = execution_environment()
    del environment["dependency_lock_hash"]

    with pytest.raises(ValidationError):
        validator("execution-environment.schema.json").validate(environment)
