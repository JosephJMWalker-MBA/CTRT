from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.canonical_content import (
    CanonicalContentSnapshot,
    persist_canonical_corpus,
)
from ctrt.corpus_manifest import CorpusManifestSnapshot
from ctrt.evidence_view import (
    PRESENTATION_NOTICES,
    PRESENTATION_VERSION,
    EvidenceViewError,
    build_stored_content_evidence_view,
    render_evidence_view_markdown,
)
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.serialization import canonical_sha256
from ctrt.stored_content_runner import (
    StoredContentExecutionWindow,
    StoredContentExperimentRunner,
)
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "synthetic-three-items.v0.2.0.json"
CONTENT_PATHS = (
    ROOT / "docs" / "corpora" / "content" / "synthetic-content-001.json",
    ROOT / "docs" / "corpora" / "content" / "synthetic-content-002.json",
    ROOT / "docs" / "corpora" / "content" / "synthetic-content-003.json",
)


def _document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _registry() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(_document(REGISTRY_PATH))


def _corpus() -> CorpusManifestSnapshot:
    return CorpusManifestSnapshot.from_document(_document(CORPUS_PATH))


def _contents() -> tuple[CanonicalContentSnapshot, ...]:
    return tuple(
        CanonicalContentSnapshot.from_document(_document(path))
        for path in CONTENT_PATHS
    )


def _analyzers() -> tuple[PositionalSentimentFixture, PositionalSentimentFixture]:
    return first_signal_fixture(), last_signal_fixture()


def _artifact(artifact_id: str, value: object) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=canonical_sha256(value),
    )


def _plan(
    registry: CandidateRegistrySnapshot,
    corpus: CorpusManifestSnapshot,
    analyzers: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = analyzers
    return ExperimentPlan(
        experiment_id="experiment.synthetic-evidence-view",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can verified evidence be surfaced without aggregation?",
        protocol_ref=_artifact("protocol.synthetic-workbench", {"version": "0.1.0"}),
        candidate_registry_ref=registry.reference(),
        corpus_ref=corpus.reference(),
        content_ids=corpus.content_ids,
        dimension_ids=("sentiment_valence",),
        instrument_revisions=(
            InstrumentRevision(
                candidate_id="fixture.first-signal",
                analyzer_id=first.identity.analyzer_id,
                dimension_id=first.dimension_id,
                implementation_revision=first.implementation_revision,
                adapter_version=first.identity.adapter_version,
                configuration_hash=canonical_sha256(first.execution_configuration),
            ),
            InstrumentRevision(
                candidate_id="fixture.last-signal",
                analyzer_id=last.identity.analyzer_id,
                dimension_id=last.dimension_id,
                implementation_revision=last.implementation_revision,
                adapter_version=last.identity.adapter_version,
                configuration_hash=canonical_sha256(last.execution_configuration),
            ),
        ),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=(),
        stopping_rules=("Stop after every stored content item has one session.",),
        created_at="2026-08-05T14:10:00Z",
    )


def _environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-evidence-view",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256({"mode": "evidence-view"}),
        hardware_profile="CPU-only synthetic execution",
    )


def _windows() -> tuple[StoredContentExecutionWindow, ...]:
    return (
        StoredContentExecutionWindow(
            content_id="content-001",
            started_at="2026-08-05T14:11:00Z",
            completed_at="2026-08-05T14:11:01Z",
        ),
        StoredContentExecutionWindow(
            content_id="content-002",
            started_at="2026-08-05T14:11:02Z",
            completed_at="2026-08-05T14:11:03Z",
        ),
        StoredContentExecutionWindow(
            content_id="content-003",
            started_at="2026-08-05T14:11:04Z",
            completed_at="2026-08-05T14:11:05Z",
        ),
    )


def _analyzer_registry(
    analyzers: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for analyzer in analyzers:
        registry.register(analyzer)
    return registry


def _execute(tmp_path: Path):
    registry = _registry()
    corpus = _corpus()
    analyzers = _analyzers()
    plan = _plan(registry, corpus, analyzers)
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    persist_canonical_corpus(
        store,
        plan=plan,
        manifest=corpus,
        contents=tuple(item.to_content_item() for item in _contents()),
    )
    runner = StoredContentExperimentRunner(
        analyzer_registry=_analyzer_registry(analyzers),
        artifact_store=store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=registry,
        corpus_manifest=corpus,
        environment=_environment(),
        windows=_windows(),
        experiment_run_id="phase1b-evidence-view-run",
    )
    return receipt, store


def test_reader_surfaces_exact_content_and_preserved_outcomes(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)

    view = build_stored_content_evidence_view(
        receipt=receipt,
        artifact_store=store,
    )

    assert view.presentation_version == PRESENTATION_VERSION
    assert view.lifecycle_status == "verified"
    assert view.notices == PRESENTATION_NOTICES
    assert tuple(item.content_id for item in view.contents) == receipt.content_ids

    disagreement = view.contents[0]
    assert disagreement.text == "The launch was good, but the support was bad."
    assert tuple(
        item.normalized_measurements[0].value
        for item in disagreement.measurements
    ) == (1.0, -1.0)
    assert tuple(
        item.evidence_spans[0].excerpt for item in disagreement.measurements
    ) == ("good", "bad")
    assert disagreement.comparison.status == "abstained"
    assert disagreement.comparison.agreement_status == "strong-disagreement"
    assert disagreement.comparison.abstention_reasons == ("strong-disagreement",)
    assert not disagreement.comparison.score_combination_permitted

    agreement = view.contents[1]
    assert agreement.comparison.status == "complete"
    assert agreement.comparison.agreement_status == "agreement"

    no_signal = view.contents[2]
    assert tuple(item.status for item in no_signal.measurements) == (
        "abstained",
        "abstained",
    )
    assert all(not item.normalized_measurements for item in no_signal.measurements)
    assert no_signal.comparison.status == "abstained"


def test_markdown_surfaces_evidence_without_a_verdict(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)
    view = build_stored_content_evidence_view(
        receipt=receipt,
        artifact_store=store,
    )

    markdown = render_evidence_view_markdown(view)

    assert markdown.startswith("# CTRT Evidence View\n")
    assert "> The launch was good, but the support was bad." in markdown
    assert "**'good'**" in markdown
    assert "**'bad'**" in markdown
    assert "- Score combination: **not permitted**" in markdown
    assert "- Agreement: `strong-disagreement`" in markdown
    assert "- Result status: **abstained**" in markdown
    assert "Canonical stored artifacts remain controlling." in markdown
    assert "No overall CTRT score" in markdown
    assert "Overall score:" not in markdown
    assert "Publish recommendation:" not in markdown
    assert "Safe / unsafe:" not in markdown


def test_reader_rehashes_content_before_presenting_it(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)
    reference = receipt.content_artifact_refs[0]
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = store.root / "blobs" / "sha256" / digest
    blob.write_bytes(b"{}")

    with pytest.raises(ArtifactIntegrityError, match="failed SHA-256"):
        build_stored_content_evidence_view(
            receipt=receipt,
            artifact_store=store,
        )


def test_reader_rejects_caller_receipt_drift(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)
    experiment = receipt.corpus_bound_receipt.experiment_receipt
    first = experiment.session_receipts[0]
    changed_first = replace(
        first,
        analyzer_ids=tuple(reversed(first.analyzer_ids)),
    )
    changed_experiment = replace(
        experiment,
        session_receipts=(changed_first, *experiment.session_receipts[1:]),
    )
    changed_corpus = replace(
        receipt.corpus_bound_receipt,
        experiment_receipt=changed_experiment,
    )
    changed_receipt = replace(
        receipt,
        corpus_bound_receipt=changed_corpus,
    )

    with pytest.raises(
        ArtifactIntegrityError,
        match="stored session receipt differs",
    ):
        build_stored_content_evidence_view(
            receipt=changed_receipt,
            artifact_store=store,
        )


def test_reader_rejects_content_reference_reordering(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)
    changed = replace(
        receipt,
        content_artifact_refs=tuple(reversed(receipt.content_artifact_refs)),
    )

    with pytest.raises(EvidenceViewError, match="content order"):
        build_stored_content_evidence_view(
            receipt=changed,
            artifact_store=store,
        )


def test_module_exports_only_the_bounded_phase1b_surface() -> None:
    import ctrt.evidence_view as module

    assert module.__all__ == [
        "ComparisonEvidenceView",
        "ContentEvidenceView",
        "DisagreementView",
        "EvidenceArtifactReference",
        "EvidenceSpanView",
        "EvidenceViewError",
        "InstrumentEvidenceView",
        "NormalizedMeasurementView",
        "PRESENTATION_NOTICES",
        "PRESENTATION_VERSION",
        "StoredContentEvidenceView",
        "build_stored_content_evidence_view",
        "render_evidence_view_markdown",
    ]
