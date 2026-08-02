import pytest

from ctrt.confidence import AgreementStatus
from ctrt.contracts import ContentItem, ResultStatus, SourceType
from ctrt.synthetic import first_signal_fixture, last_signal_fixture
from ctrt.taxonomy import TaxonomyDisplayMode, TaxonomyRelation
from ctrt.workbench import (
    AnalyzerRegistry,
    ContentAnalysisWorkbench,
    WorkbenchReportStatus,
)


def content(text: str, *, language: str | None = "en") -> ContentItem:
    return ContentItem(
        content_id="content-001",
        text=text,
        source_type=SourceType.RAW_TEXT,
        content_hash="sha256:synthetic-workbench",
        language=language,
    )


def workbench() -> tuple[ContentAnalysisWorkbench, tuple[str, str]]:
    registry = AnalyzerRegistry()
    first = first_signal_fixture()
    last = last_signal_fixture()
    registry.register(first)
    registry.register(last)
    return ContentAnalysisWorkbench(registry), (
        first.identity.analyzer_id,
        last.identity.analyzer_id,
    )


def test_mixed_fixture_signals_preserve_results_and_force_report_abstention() -> None:
    bench, analyzer_ids = workbench()

    run = bench.run_content_item(
        run_id="run-001",
        content=content("The launch was good, but the support was bad."),
        analyzer_ids=analyzer_ids,
    )

    assert tuple(result.status for result in run.results) == (
        ResultStatus.SUCCESS,
        ResultStatus.SUCCESS,
    )
    assert tuple(result.normalized_scores[0].value for result in run.results) == (1.0, -1.0)
    assert run.results[0].raw_output["selected_token"] == "good"
    assert run.results[1].raw_output["selected_token"] == "bad"
    assert run.results[0].analysis_target == run.results[1].analysis_target
    assert run.comparison.confidence.inter_instrument_agreement.status is (
        AgreementStatus.STRONG_DISAGREEMENT
    )
    assert run.comparison.status is WorkbenchReportStatus.ABSTAINED
    assert run.comparison.confidence.system_abstention.triggered
    assert run.comparison.confidence.system_abstention.reasons == (
        "strong-disagreement",
    )
    assert run.comparison.disagreements[0].material


def test_identical_taxonomy_is_recorded_without_score_combination() -> None:
    bench, analyzer_ids = workbench()

    run = bench.run_content_item(
        run_id="run-001",
        content=content("The launch was good, but the support was bad."),
        analyzer_ids=analyzer_ids,
    )

    taxonomy = run.comparison.taxonomy_comparisons[0]
    assert taxonomy.relation is TaxonomyRelation.IDENTICAL
    assert taxonomy.display_mode is TaxonomyDisplayMode.MAPPED_COMPARISON
    assert not taxonomy.score_combination_permitted
    assert not run.comparison.score_combination_permitted


def test_no_fixture_signal_preserves_abstained_results() -> None:
    bench, analyzer_ids = workbench()

    run = bench.run_content_item(
        run_id="run-002",
        content=content("The report contains no fixture vocabulary."),
        analyzer_ids=analyzer_ids,
    )

    assert all(result.status is ResultStatus.ABSTAINED for result in run.results)
    assert all(not result.normalized_scores for result in run.results)
    assert run.comparison.confidence.inter_instrument_agreement.status is AgreementStatus.ABSTAIN
    assert run.comparison.status is WorkbenchReportStatus.ABSTAINED
    assert run.comparison.confidence.system_abstention.reasons == (
        "agreement-abstain",
    )


def test_out_of_domain_fixture_results_preserve_required_abstention() -> None:
    bench, analyzer_ids = workbench()

    run = bench.run_content_item(
        run_id="run-003",
        content=content("good then bad", language="es"),
        analyzer_ids=analyzer_ids,
    )

    assert all(result.status is ResultStatus.ABSTAINED for result in run.results)
    assert all(
        "out-of-domain" in result.confidence.system_abstention.reasons
        for result in run.results
    )
    assert run.comparison.status is WorkbenchReportStatus.ABSTAINED


def test_registry_rejects_duplicate_identity() -> None:
    registry = AnalyzerRegistry()
    analyzer = first_signal_fixture()
    registry.register(analyzer)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(analyzer)


def test_side_by_side_run_requires_two_unique_analyzers() -> None:
    registry = AnalyzerRegistry()
    analyzer = first_signal_fixture()
    registry.register(analyzer)
    bench = ContentAnalysisWorkbench(registry)

    with pytest.raises(ValueError, match="at least two"):
        bench.run_content_item(
            run_id="run-004",
            content=content("good"),
            analyzer_ids=(analyzer.identity.analyzer_id,),
        )

    with pytest.raises(ValueError, match="must be unique"):
        bench.run_content_item(
            run_id="run-005",
            content=content("good"),
            analyzer_ids=(
                analyzer.identity.analyzer_id,
                analyzer.identity.analyzer_id,
            ),
        )
