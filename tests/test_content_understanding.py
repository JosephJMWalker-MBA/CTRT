from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.canonical_content import CanonicalContentSnapshot, persist_canonical_corpus
from ctrt.content_understanding import (
    CONTENT_INSPECTION_PATHS,
    CONTENT_UNDERSTANDING_NOTICES,
    CONTENT_UNDERSTANDING_VERSION,
    ContentUnderstandingError,
    ContentUnderstandingRequest,
    ContentUnderstandingView,
    ReaderProvidedContext,
    build_content_understanding,
    render_content_understanding_markdown,
)
from ctrt.corpus_manifest import CorpusManifestSnapshot
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
        experiment_id="experiment.synthetic-content-understanding",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question=(
            "Can verified evidence support content inspection without surveillance or advice?"
        ),
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
        stopping_rules=("Stop after every content item has one governed session.",),
        created_at="2026-08-06T00:35:00Z",
    )


def _environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-content-understanding",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256(
            {"mode": "content-understanding"}
        ),
        hardware_profile="CPU-only synthetic execution",
    )


def _windows() -> tuple[StoredContentExecutionWindow, ...]:
    return (
        StoredContentExecutionWindow(
            content_id="content-001",
            started_at="2026-08-06T00:36:00Z",
            completed_at="2026-08-06T00:36:01Z",
        ),
        StoredContentExecutionWindow(
            content_id="content-002",
            started_at="2026-08-06T00:36:02Z",
            completed_at="2026-08-06T00:36:03Z",
        ),
        StoredContentExecutionWindow(
            content_id="content-003",
            started_at="2026-08-06T00:36:04Z",
            completed_at="2026-08-06T00:36:05Z",
        ),
    )


def _runtime_registry(
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
    receipt = StoredContentExperimentRunner(
        analyzer_registry=_runtime_registry(analyzers),
        artifact_store=store,
    ).run(
        plan=plan,
        candidate_registry=registry,
        corpus_manifest=corpus,
        environment=_environment(),
        windows=_windows(),
        experiment_run_id="phase1b-content-understanding-run",
    )
    return receipt, store


def _request(content_id: str) -> ContentUnderstandingRequest:
    return ContentUnderstandingRequest(
        content_id=content_id,
        context=ReaderProvidedContext(
            purpose="Understand the contrast and what context should be checked.",
            known_context="This sentence was submitted directly for inspection.",
            questions=(
                "What does the contrast emphasize?",
                "What cannot be concluded from these measurements?",
            ),
        ),
    )


def _prompt_ids(view: object) -> tuple[str, ...]:
    prompts = cast(Any, view).reflection_prompts
    return tuple(item.prompt_id for item in prompts)


def test_understanding_preserves_disagreement_agreement_and_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = _execute(tmp_path)

    disagreement = build_content_understanding(
        request=_request("content-001"),
        receipt=receipt,
        artifact_store=store,
    )
    assert disagreement.understanding_version == CONTENT_UNDERSTANDING_VERSION
    assert disagreement.lifecycle_status == "verified"
    assert disagreement.notices == CONTENT_UNDERSTANDING_NOTICES
    assert disagreement.inspection_paths == CONTENT_INSPECTION_PATHS
    instrument_text = tuple(
        item.text for item in disagreement.observations if item.kind == "instrument"
    )
    assert "valence 1 within [-1, 1]" in instrument_text[0]
    assert "'good' [15:19]" in instrument_text[0]
    assert "valence -1 within [-1, 1]" in instrument_text[1]
    assert "'bad' [41:44]" in instrument_text[1]
    assert "material-disagreement" in _prompt_ids(disagreement)
    assert "comparison-abstention" in _prompt_ids(disagreement)
    assert "source-context" in _prompt_ids(disagreement)
    assert "discussion-without-presumption" in _prompt_ids(disagreement)

    agreement = build_content_understanding(
        request=_request("content-002"),
        receipt=receipt,
        artifact_store=store,
    )
    assert agreement.evidence.comparison.agreement_status == "agreement"
    assert "instrument-agreement" in _prompt_ids(agreement)
    assert "material-disagreement" not in _prompt_ids(agreement)

    no_signal = build_content_understanding(
        request=_request("content-003"),
        receipt=receipt,
        artifact_store=store,
    )
    assert all(item.status == "abstained" for item in no_signal.evidence.measurements)
    assert "instrument-abstention" in _prompt_ids(no_signal)
    assert "comparison-abstention" in _prompt_ids(no_signal)
    assert "applicability-boundary" in _prompt_ids(no_signal)


def test_markdown_is_content_directed_and_non_prescriptive(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)
    view = build_content_understanding(
        request=_request("content-001"),
        receipt=receipt,
        artifact_store=store,
    )

    markdown = render_content_understanding_markdown(view)

    assert markdown.startswith("# Understand this content\n")
    assert "It does not decide what the content means" in markdown
    assert "not verified evidence" in markdown
    assert "> The launch was good, but the support was bad." in markdown
    assert "## Questions for closer inspection" in markdown
    assert "## Ways to continue understanding" in markdown
    assert "Read the content in its original surrounding context." in markdown
    assert "No overall CTRT score, safety label, restriction recommendation" in markdown
    assert "Safety classification:" not in markdown
    assert "Restriction decision:" not in markdown
    assert "Recommended action:" not in markdown
    assert "Viewer risk score:" not in markdown
    assert "You should block" not in markdown
    assert "You should restrict" not in markdown


def test_reader_context_remains_bounded_non_evidentiary_input() -> None:
    with pytest.raises(ValueError, match="reader purpose"):
        ReaderProvidedContext(purpose=" ")
    with pytest.raises(ValueError, match="known context"):
        ReaderProvidedContext(purpose="Understand this.", known_context=" ")
    with pytest.raises(ValueError, match="empty values"):
        ReaderProvidedContext(purpose="Understand this.", questions=("",))
    with pytest.raises(ValueError, match="question mark"):
        ReaderProvidedContext(
            purpose="Understand this.",
            questions=("This is not phrased as a question",),
        )
    with pytest.raises(ValueError, match="duplicates"):
        ReaderProvidedContext(
            purpose="Understand this.",
            questions=("What is missing?", "What is missing?"),
        )

    names = {item.name for item in fields(ContentUnderstandingView)}
    assert "viewer_id" not in names
    assert "parent_id" not in names
    assert "child_id" not in names
    assert "risk_score" not in names
    assert "restriction" not in names


def test_unknown_content_id_fails_without_guessing(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)

    with pytest.raises(ContentUnderstandingError, match="exactly one verified content"):
        build_content_understanding(
            request=_request("content-missing"),
            receipt=receipt,
            artifact_store=store,
        )


def test_understanding_inherits_receipt_drift_failure(tmp_path: Path) -> None:
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
    changed_receipt = replace(receipt, corpus_bound_receipt=changed_corpus)

    with pytest.raises(ArtifactIntegrityError, match="stored session receipt differs"):
        build_content_understanding(
            request=_request("content-001"),
            receipt=changed_receipt,
            artifact_store=store,
        )


def test_understanding_rehashes_content_before_reflection(tmp_path: Path) -> None:
    receipt, store = _execute(tmp_path)
    reference = receipt.content_artifact_refs[0]
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = store.root / "blobs" / "sha256" / digest
    blob.write_bytes(b"{}")

    with pytest.raises(ArtifactIntegrityError, match="failed SHA-256"):
        build_content_understanding(
            request=_request("content-001"),
            receipt=receipt,
            artifact_store=store,
        )


def test_module_exports_only_the_bounded_understanding_surface() -> None:
    import ctrt.content_understanding as module

    assert module.__all__ == [
        "CONTENT_INSPECTION_PATHS",
        "CONTENT_UNDERSTANDING_NOTICES",
        "CONTENT_UNDERSTANDING_VERSION",
        "ContentUnderstandingError",
        "ContentUnderstandingRequest",
        "ContentUnderstandingView",
        "ReaderProvidedContext",
        "UnderstandingObservation",
        "UnderstandingObservationKind",
        "UnderstandingPrompt",
        "UnderstandingPromptKind",
        "build_content_understanding",
        "render_content_understanding_markdown",
    ]
