import pytest

from ctrt.contracts import ContentItem, ResultStatus, SourceType
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    ExperimentRunStatus,
    InMemoryExperimentLedger,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
    record_workbench_run,
)
from ctrt.synthetic import first_signal_fixture, last_signal_fixture
from ctrt.workbench import AnalyzerRegistry, ContentAnalysisWorkbench

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
HASH_D = "sha256:" + "d" * 64
HASH_E = "sha256:" + "e" * 64
HASH_F = "sha256:" + "f" * 64


def artifact(artifact_id: str, artifact_hash: str) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=artifact_hash,
    )


def revisions() -> tuple[InstrumentRevision, InstrumentRevision]:
    return (
        InstrumentRevision(
            candidate_id="fixture.first-signal",
            analyzer_id="synthetic.sentiment.first-signal",
            implementation_revision="ctrt-fixture-first@0.1.0",
            adapter_version="0.1.0",
            configuration_hash=HASH_D,
        ),
        InstrumentRevision(
            candidate_id="fixture.last-signal",
            analyzer_id="synthetic.sentiment.last-signal",
            implementation_revision="ctrt-fixture-last@0.1.0",
            adapter_version="0.1.0",
            configuration_hash=HASH_E,
        ),
    )


def plan(*, status: ExperimentPlanStatus = ExperimentPlanStatus.FROZEN) -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="experiment.synthetic-disagreement",
        experiment_version="0.1.0",
        status=status,
        research_question="Can immutable successful results coexist with comparison abstention?",
        protocol_ref=artifact("protocol.synthetic-workbench", HASH_A),
        candidate_registry_ref=artifact("registry.synthetic-fixtures", HASH_B),
        corpus_ref=artifact("corpus.synthetic-vocabulary", HASH_C),
        content_ids=("content-001",),
        dimension_ids=("sentiment_valence",),
        instrument_revisions=revisions(),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=("Exclude content outside the declared English fixture domain.",),
        stopping_rules=("Stop after all declared content and instruments have one result.",),
        created_at="2026-08-02T20:00:00Z",
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
        hardware_profile="GitHub-hosted CPU runner; no accelerator required",
    )


def workbench_run(text: str = "The launch was good, but the support was bad."):
    registry = AnalyzerRegistry()
    first = first_signal_fixture()
    last = last_signal_fixture()
    registry.register(first)
    registry.register(last)
    bench = ContentAnalysisWorkbench(registry)
    content = ContentItem(
        content_id="content-001",
        text=text,
        source_type=SourceType.RAW_TEXT,
        content_hash=HASH_F,
        language="en",
    )
    return bench.run_content_item(
        run_id="run-001",
        content=content,
        analyzer_ids=(first.identity.analyzer_id, last.identity.analyzer_id),
    )


def recorded_run(text: str = "The launch was good, but the support was bad."):
    frozen = plan()
    frozen_ref = artifact(frozen.experiment_id, HASH_F)
    run = workbench_run(text)
    hashes = {
        run.results[0].result_id: HASH_D,
        run.results[1].result_id: HASH_E,
    }
    return frozen, frozen_ref, record_workbench_run(
        plan=frozen,
        plan_ref=frozen_ref,
        environment=environment(),
        run=run,
        result_hashes=hashes,
        comparison_hash=HASH_C,
        started_at="2026-08-02T20:01:00Z",
        completed_at="2026-08-02T20:01:01Z",
    )


def test_frozen_plan_records_comparison_abstention_without_rewriting_results() -> None:
    _, _, record = recorded_run()

    assert record.status is ExperimentRunStatus.ABSTAINED
    assert tuple(item.status for item in record.result_artifacts) == (
        ResultStatus.SUCCESS,
        ResultStatus.SUCCESS,
    )
    assert record.comparison_artifact.status.value == "abstained"
    assert record.comparison_artifact.result_ids == tuple(
        item.result_id for item in record.result_artifacts
    )


def test_abstained_analyzer_results_remain_abstained_in_run_record() -> None:
    _, _, record = recorded_run("The report contains no fixture vocabulary.")

    assert record.status is ExperimentRunStatus.ABSTAINED
    assert all(item.status is ResultStatus.ABSTAINED for item in record.result_artifacts)


def test_draft_plan_cannot_authorize_execution() -> None:
    draft = plan(status=ExperimentPlanStatus.DRAFT)
    draft_ref = artifact(draft.experiment_id, HASH_F)
    run = workbench_run()

    with pytest.raises(ValueError, match="only a frozen"):
        record_workbench_run(
            plan=draft,
            plan_ref=draft_ref,
            environment=environment(),
            run=run,
            result_hashes={
                run.results[0].result_id: HASH_D,
                run.results[1].result_id: HASH_E,
            },
            comparison_hash=HASH_C,
            started_at="2026-08-02T20:01:00Z",
            completed_at="2026-08-02T20:01:01Z",
        )


def test_result_hashes_must_cover_exactly_the_preserved_results() -> None:
    frozen = plan()
    frozen_ref = artifact(frozen.experiment_id, HASH_F)
    run = workbench_run()

    with pytest.raises(ValueError, match="cover exactly"):
        record_workbench_run(
            plan=frozen,
            plan_ref=frozen_ref,
            environment=environment(),
            run=run,
            result_hashes={run.results[0].result_id: HASH_D},
            comparison_hash=HASH_C,
            started_at="2026-08-02T20:01:00Z",
            completed_at="2026-08-02T20:01:01Z",
        )


def test_plan_rejects_unpinned_instrument_revision() -> None:
    with pytest.raises(ValueError, match="implementation_revision"):
        InstrumentRevision(
            candidate_id="fixture.first-signal",
            analyzer_id="synthetic.sentiment.first-signal",
            implementation_revision="",
            adapter_version="0.1.0",
            configuration_hash=HASH_D,
        )


def test_experiment_ledger_is_append_only_for_plans_and_runs() -> None:
    frozen, frozen_ref, record = recorded_run()
    ledger = InMemoryExperimentLedger()
    ledger.append_plan(frozen_ref, frozen)
    ledger.append_run(record)

    with pytest.raises(ValueError, match="append-only"):
        ledger.append_plan(frozen_ref, frozen)
    with pytest.raises(ValueError, match="append-only"):
        ledger.append_run(record)

    assert ledger.plans() == (frozen,)
    assert ledger.runs() == (record,)


def test_run_analyzer_order_must_match_frozen_plan() -> None:
    frozen = plan()
    frozen_ref = artifact(frozen.experiment_id, HASH_F)
    run = workbench_run()
    reversed_plan = ExperimentPlan(
        experiment_id=frozen.experiment_id,
        experiment_version="0.1.1",
        status=ExperimentPlanStatus.FROZEN,
        research_question=frozen.research_question,
        protocol_ref=frozen.protocol_ref,
        candidate_registry_ref=frozen.candidate_registry_ref,
        corpus_ref=frozen.corpus_ref,
        content_ids=frozen.content_ids,
        dimension_ids=frozen.dimension_ids,
        instrument_revisions=tuple(reversed(frozen.instrument_revisions)),
        metrics=frozen.metrics,
        exclusion_rules=frozen.exclusion_rules,
        stopping_rules=frozen.stopping_rules,
        created_at=frozen.created_at,
    )
    reversed_ref = VersionedArtifactRef(
        artifact_id=reversed_plan.experiment_id,
        artifact_version=reversed_plan.experiment_version,
        artifact_hash=frozen_ref.artifact_hash,
    )

    with pytest.raises(ValueError, match="analyzer order"):
        record_workbench_run(
            plan=reversed_plan,
            plan_ref=reversed_ref,
            environment=environment(),
            run=run,
            result_hashes={
                run.results[0].result_id: HASH_D,
                run.results[1].result_id: HASH_E,
            },
            comparison_hash=HASH_C,
            started_at="2026-08-02T20:01:00Z",
            completed_at="2026-08-02T20:01:01Z",
        )
