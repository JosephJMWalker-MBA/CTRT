from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.contracts import AnalyzerIdentity, ContentItem, ModelResult
from ctrt.experiment_runner import ExperimentRunnerStatus
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.extraction_bound_runner import (
    EXTRACTION_BOUND_VERIFIED_CHECKS,
    ExtractionBoundExperimentError,
    ExtractionBoundExperimentRunner,
    ExtractionBoundRunnerStage,
    ExtractionBoundRunnerStatus,
    ExtractionExecutionWindow,
    VerifiedExtractionBoundExperimentReceipt,
)
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionCorpusManifestSnapshot,
    ExtractionManifestError,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
    load_extracted_corpus,
    persist_extracted_corpus,
)
from ctrt.serialization import CanonicalArtifact, canonical_sha256
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry, WorkbenchReportStatus

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.1.0.json"
SOURCE_PATHS = tuple(
    ROOT / "docs" / "corpora" / "extraction" / "sources" / f"source-{index:03d}.json"
    for index in range(1, 4)
)
CONTENT_PATHS = tuple(
    ROOT / "docs" / "corpora" / "extraction" / "content" / f"content-{index:03d}.json"
    for index in range(1, 4)
)
EXTRACTION_PATHS = tuple(
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "manifests"
    / f"extraction-{index:03d}.json"
    for index in range(1, 4)
)
SOURCE_SCHEMA = ROOT / "schemas" / "source-artifact.schema.json"
CONTENT_SCHEMA = ROOT / "schemas" / "extracted-content-artifact.schema.json"
EXTRACTION_SCHEMA = ROOT / "schemas" / "extraction-manifest.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "extraction-corpus-manifest.schema.json"
COMPLETION_SCHEMA = (
    ROOT / "schemas" / "extraction-bound-experiment-completion.schema.json"
)
LEGACY_CONTENT_PATH = ROOT / "docs" / "corpora" / "content" / "synthetic-content-001.json"
COMPLETION_ID = "extraction-run-001:extraction-bound-completion"


@dataclass(frozen=True, slots=True)
class FailOnContentAnalyzer:
    base: PositionalSentimentFixture
    fail_content_id: str

    @property
    def dimension_id(self) -> str:
        return self.base.dimension_id

    @property
    def implementation_revision(self) -> str:
        return self.base.implementation_revision

    @property
    def execution_configuration(self) -> Mapping[str, object]:
        return self.base.execution_configuration

    @property
    def identity(self) -> AnalyzerIdentity:
        return self.base.identity

    def analyze(self, content: ContentItem) -> ModelResult:
        if content.content_id == self.fail_content_id:
            raise RuntimeError("synthetic extraction-bound execution failure")
        return self.base.analyze(content)


class SourceReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path, source_id: str) -> None:
        super().__init__(root)
        self._source_id = source_id

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id == self._source_id:
            raise ArtifactIntegrityError("synthetic source artifact read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class CompletionAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(":extraction-bound-completion"):
            raise ArtifactIntegrityError("synthetic extraction completion failure")
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def registry_snapshot() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(load_document(REGISTRY_PATH))


def corpus_snapshot() -> ExtractionCorpusManifestSnapshot:
    return ExtractionCorpusManifestSnapshot.from_document(load_document(CORPUS_PATH))


def source_snapshots() -> tuple[SourceArtifactSnapshot, ...]:
    return tuple(
        SourceArtifactSnapshot.from_document(load_document(path))
        for path in SOURCE_PATHS
    )


def content_snapshots() -> tuple[ExtractedContentSnapshot, ...]:
    return tuple(
        ExtractedContentSnapshot.from_document(load_document(path))
        for path in CONTENT_PATHS
    )


def extraction_snapshots() -> tuple[ExtractionManifestSnapshot, ...]:
    return tuple(
        ExtractionManifestSnapshot.from_document(load_document(path))
        for path in EXTRACTION_PATHS
    )


def analyzers() -> tuple[PositionalSentimentFixture, PositionalSentimentFixture]:
    return first_signal_fixture(), last_signal_fixture()


def artifact(artifact_id: str, value: object) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=canonical_sha256(value),
    )


def experiment_plan(
    registry: CandidateRegistrySnapshot,
    manifest: ExtractionCorpusManifestSnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-extraction-bound",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can stored extraction provenance reconstruct exact inputs?",
        protocol_ref=artifact("protocol.synthetic-workbench", {"version": "0.1.0"}),
        candidate_registry_ref=registry.reference(),
        corpus_ref=manifest.reference(),
        content_ids=manifest.content_ids,
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
        stopping_rules=("Stop after every extracted content item has one session.",),
        created_at="2026-08-02T23:48:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-extraction-bound",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256(
            {"mode": "synthetic-extraction-bound"}
        ),
        hardware_profile="CPU-only synthetic execution",
    )


def windows() -> tuple[ExtractionExecutionWindow, ...]:
    return (
        ExtractionExecutionWindow(
            content_id="content-001",
            started_at="2026-08-02T23:49:00Z",
            completed_at="2026-08-02T23:49:01Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-002",
            started_at="2026-08-02T23:49:02Z",
            completed_at="2026-08-02T23:49:03Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-003",
            started_at="2026-08-02T23:49:04Z",
            completed_at="2026-08-02T23:49:05Z",
        ),
    )


def analyzer_registry(*items: object) -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for item in items:
        registry.register(cast(Any, item))
    return registry


def prepare_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
) -> tuple[
    FileSystemArtifactStore,
    CandidateRegistrySnapshot,
    ExtractionCorpusManifestSnapshot,
    ExperimentPlan,
    tuple[PositionalSentimentFixture, PositionalSentimentFixture],
]:
    candidate_registry = registry_snapshot()
    manifest = corpus_snapshot()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate_registry, manifest, fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    persist_extracted_corpus(
        artifact_store,
        plan=plan,
        manifest=manifest,
        sources=source_snapshots(),
        extractions=extraction_snapshots(),
        contents=content_snapshots(),
    )
    return artifact_store, candidate_registry, manifest, plan, fixture_analyzers


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    runtime_registry: AnalyzerRegistry | None = None,
) -> tuple[VerifiedExtractionBoundExperimentReceipt, FileSystemArtifactStore]:
    (
        artifact_store,
        candidate_registry,
        manifest,
        plan,
        fixture_analyzers,
    ) = prepare_store(tmp_path, store=store)
    runner = ExtractionBoundExperimentRunner(
        analyzer_registry=(
            runtime_registry or analyzer_registry(*fixture_analyzers)
        ),
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate_registry,
        corpus_manifest=manifest,
        environment=environment(),
        windows=windows(),
        experiment_run_id="extraction-run-001",
    )
    return receipt, artifact_store


def validate_schema(path: Path, document: dict[str, Any]) -> None:
    Draft202012Validator(
        load_document(path),
        format_checker=FormatChecker(),
    ).validate(document)


def test_extraction_graph_validates_and_reconstructs_inputs(tmp_path: Path) -> None:
    store, _, manifest, _, _ = prepare_store(tmp_path)
    loaded = load_extracted_corpus(store, manifest)

    assert tuple(item.content_id for item in loaded.contents) == manifest.content_ids
    assert all(
        item.canonical_extraction_ref.startswith("extraction:")
        for item in loaded.contents
    )
    assert loaded.source_refs == tuple(
        item.source_artifact_ref for item in manifest.contents
    )
    assert loaded.extraction_refs == tuple(
        item.extraction_artifact_ref for item in manifest.contents
    )
    assert loaded.content_refs == tuple(
        item.content_artifact_ref for item in manifest.contents
    )

    for path in SOURCE_PATHS:
        validate_schema(SOURCE_SCHEMA, load_document(path))
    for path in CONTENT_PATHS:
        validate_schema(CONTENT_SCHEMA, load_document(path))
    for path in EXTRACTION_PATHS:
        validate_schema(EXTRACTION_SCHEMA, load_document(path))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_runner_executes_from_ids_and_timestamps_only(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is ExtractionBoundRunnerStatus.VERIFIED
    assert receipt.verified_checks == EXTRACTION_BOUND_VERIFIED_CHECKS
    assert receipt.experiment_receipt.status is ExperimentRunnerStatus.VERIFIED
    assert tuple(
        item.workbench_status
        for item in receipt.experiment_receipt.session_receipts
    ) == (
        WorkbenchReportStatus.ABSTAINED,
        WorkbenchReportStatus.COMPLETE,
        WorkbenchReportStatus.ABSTAINED,
    )

    completion = store.get(
        receipt.completion_manifest_ref.artifact_id,
        expected_hash=receipt.completion_manifest_ref.artifact_hash,
    )
    document = cast(dict[str, Any], json.loads(completion.text))
    validate_schema(COMPLETION_SCHEMA, document)
    assert "text" not in document
    assert "aggregate_score" not in document
    assert "overall_status" not in document


def test_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.source_artifact_refs == second.source_artifact_refs
    assert first.extraction_artifact_refs == second.extraction_artifact_refs
    assert first.content_artifact_refs == second.content_artifact_refs
    assert first.completion_manifest_ref == second.completion_manifest_ref


def test_legacy_content_item_identity_is_not_an_extraction_artifact() -> None:
    with pytest.raises(ExtractionManifestError, match="extracted content ID"):
        ExtractedContentSnapshot.from_document(load_document(LEGACY_CONTENT_PATH))


def test_method_revision_drift_invalidates_extraction_identity() -> None:
    document = load_document(EXTRACTION_PATHS[0])
    document["method_revision"] = "ctrt-synthetic-identity-text@0.2.0"

    with pytest.raises(ExtractionManifestError, match="extraction ID"):
        ExtractionManifestSnapshot.from_document(document)


def test_coordinate_map_must_cover_complete_text() -> None:
    document = load_document(EXTRACTION_PATHS[0])
    coordinate = cast(list[dict[str, Any]], document["coordinate_map"])
    coordinate[0]["source_end"] -= 1
    coordinate[0]["canonical_end"] -= 1
    extraction = ExtractionManifestSnapshot.from_document(document)

    with pytest.raises(ExtractionManifestError, match="complete source text"):
        extraction.verify(source_snapshots()[0], content_snapshots()[0])


def test_missing_source_fails_before_experiment_completion(tmp_path: Path) -> None:
    store, candidate_registry, manifest, plan, fixture_analyzers = prepare_store(tmp_path)
    failing_store = SourceReadFailsStore(
        store.root,
        manifest.contents[1].source_artifact_ref.artifact_id,
    )
    runner = ExtractionBoundExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing_store,
    )

    with pytest.raises(ExtractionBoundExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=manifest,
            environment=environment(),
            windows=windows(),
            experiment_run_id="extraction-run-missing-source",
        )

    assert caught.value.stage is ExtractionBoundRunnerStage.EXTRACTION_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("extraction-run-missing-source:experiment-completion")


def test_later_execution_failure_preserves_prior_receipt(tmp_path: Path) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ExtractionBoundExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=runtime_registry,
        )

    assert caught.value.stage is ExtractionBoundRunnerStage.EXPERIMENT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    store.get(
        "extraction-run-001:0000:content-001:governed-session:receipt"
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_completion_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = CompletionAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(ExtractionBoundExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExtractionBoundRunnerStage.COMPLETION_PERSISTENCE
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)
