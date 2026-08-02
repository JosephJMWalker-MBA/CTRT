from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ctrt.artifact_pipeline import serialize_experiment_run
from ctrt.candidate_eligibility import (
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.contracts import ContentItem, SourceType
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.serialization import canonical_sha256
from ctrt.synthetic import first_signal_fixture, last_signal_fixture
from ctrt.workbench import AnalyzerRegistry, ContentAnalysisWorkbench

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def registry_snapshot() -> CandidateRegistrySnapshot:
    document = cast(
        dict[str, Any],
        json.loads(REGISTRY_PATH.read_text(encoding="utf-8")),
    )
    return CandidateRegistrySnapshot.from_document(document)


def artifact(artifact_id: str, artifact_hash: str) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=artifact_hash,
    )


def experiment_plan(registry: CandidateRegistrySnapshot) -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="experiment.synthetic-disagreement",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can canonical artifacts preserve a governed synthetic run?",
        protocol_ref=artifact("protocol.synthetic-workbench", HASH_A),
        candidate_registry_ref=registry.reference(),
        corpus_ref=artifact("corpus.synthetic-vocabulary", HASH_B),
        content_ids=("content-001",),
        dimension_ids=("sentiment_valence",),
        instrument_revisions=(
            InstrumentRevision(
                candidate_id="fixture.first-signal",
                analyzer_id="synthetic.sentiment.first-signal",
                dimension_id="sentiment_valence",
                implementation_revision="ctrt-fixture-first@0.1.0",
                adapter_version="0.1.0",
                configuration_hash=HASH_A,
            ),
            InstrumentRevision(
                candidate_id="fixture.last-signal",
                analyzer_id="synthetic.sentiment.last-signal",
                dimension_id="sentiment_valence",
                implementation_revision="ctrt-fixture-last@0.1.0",
                adapter_version="0.1.0",
                configuration_hash=HASH_B,
            ),
        ),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=(),
        stopping_rules=("Stop after the declared fixture run.",),
        created_at="2026-08-02T21:15:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-ci",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=HASH_A,
        runtime_configuration_hash=HASH_B,
        hardware_profile="GitHub-hosted CPU runner",
    )


def workbench_run():
    registry = AnalyzerRegistry()
    first = first_signal_fixture()
    last = last_signal_fixture()
    registry.register(first)
    registry.register(last)
    content = ContentItem(
        content_id="content-001",
        text="The launch was good, but the support was bad.",
        source_type=SourceType.RAW_TEXT,
        content_hash=HASH_C,
        language="en",
    )
    return ContentAnalysisWorkbench(registry).run_content_item(
        run_id="run-001",
        content=content,
        analyzer_ids=(first.identity.analyzer_id, last.identity.analyzer_id),
    )


def test_pipeline_computes_every_hash_and_links_the_record() -> None:
    registry = registry_snapshot()
    plan = experiment_plan(registry)
    eligibility = validate_candidate_eligibility(plan, registry)
    run = workbench_run()

    bundle = serialize_experiment_run(
        plan=plan,
        eligibility=eligibility,
        environment=environment(),
        run=run,
        started_at="2026-08-02T21:16:00Z",
        completed_at="2026-08-02T21:16:01Z",
    )

    assert bundle.plan.artifact_hash == canonical_sha256(plan)
    assert bundle.candidate_eligibility.artifact_hash == canonical_sha256(eligibility)
    assert bundle.environment.artifact_hash == canonical_sha256(environment())
    assert tuple(item.artifact_hash for item in bundle.results) == tuple(
        item.artifact_hash for item in bundle.run_record.result_artifacts
    )
    assert bundle.comparison.artifact_hash == (
        bundle.run_record.comparison_artifact.artifact_hash
    )
    assert bundle.run_record.candidate_eligibility_ref == eligibility.reference()
    assert bundle.run_record_artifact.artifact_hash == canonical_sha256(
        bundle.run_record
    )


def test_identical_inputs_produce_identical_artifact_hashes() -> None:
    registry = registry_snapshot()
    plan = experiment_plan(registry)
    eligibility = validate_candidate_eligibility(plan, registry)
    run = workbench_run()
    arguments = {
        "plan": plan,
        "eligibility": eligibility,
        "environment": environment(),
        "run": run,
        "started_at": "2026-08-02T21:16:00Z",
        "completed_at": "2026-08-02T21:16:01Z",
    }

    first = serialize_experiment_run(**arguments)
    second = serialize_experiment_run(**arguments)

    assert first.plan.artifact_hash == second.plan.artifact_hash
    assert tuple(item.artifact_hash for item in first.results) == tuple(
        item.artifact_hash for item in second.results
    )
    assert first.comparison.artifact_hash == second.comparison.artifact_hash
    assert first.run_record_artifact.artifact_hash == second.run_record_artifact.artifact_hash
