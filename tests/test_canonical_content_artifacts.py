from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
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
from ctrt.canonical_content import (
    CanonicalContentError,
    CanonicalContentSnapshot,
    load_canonical_corpus,
    persist_canonical_corpus,
)
from ctrt.contracts import AnalyzerIdentity, ContentItem, ModelResult, SourceType
from ctrt.corpus_manifest import CorpusManifestSnapshot
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.serialization import CanonicalArtifact, canonical_sha256
from ctrt.stored_content_runner import (
    STORED_CONTENT_VERIFIED_CHECKS,
    StoredContentExecutionWindow,
    StoredContentExperimentError,
    StoredContentExperimentRunner,
    StoredContentRunnerStage,
    StoredContentRunnerStatus,
)
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry, WorkbenchReportStatus

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "synthetic-three-items.v0.2.0.json"
LEGACY_CORPUS_PATH = ROOT / "docs" / "corpora" / "synthetic-three-items.v0.1.0.json"
CONTENT_PATHS = (
    ROOT / "docs" / "corpora" / "content" / "synthetic-content-001.json",
    ROOT / "docs" / "corpora" / "content" / "synthetic-content-002.json",
    ROOT / "docs" / "corpora" / "content" / "synthetic-content-003.json",
)
CONTENT_SCHEMA_PATH = ROOT / "schemas" / "canonical-content-artifact.schema.json"
CORPUS_SCHEMA_PATH = ROOT / "schemas" / "corpus-manifest.schema.json"
COMPLETION_SCHEMA_PATH = (
    ROOT / "schemas" / "stored-content-experiment-completion.schema.json"
)
COMPLETION_ID = "stored-run-001:stored-content-completion"


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
            raise RuntimeError("synthetic stored-content execution failure")
        return self.base.analyze(content)


class ContentReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path, artifact_id: str) -> None:
        super().__init__(root)
        self._artifact_id = artifact_id

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id == self._artifact_id:
            raise ArtifactIntegrityError("synthetic canonical content read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class CompletionAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(":stored-content-completion"):
            raise ArtifactIntegrityError("synthetic stored completion failure")
        return super().append(artifact)


class SecondCompletionReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._reads = 0

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id.endswith(":stored-content-completion"):
            self._reads += 1
            if self._reads == 2:
                raise ArtifactIntegrityError(
                    "synthetic stored completion reverification failure"
                )
        return super().get(artifact_id, expected_hash=expected_hash)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def registry_snapshot() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(load_document(REGISTRY_PATH))


def corpus_snapshot(path: Path = CORPUS_PATH) -> CorpusManifestSnapshot:
    return CorpusManifestSnapshot.from_document(load_document(path))


def content_snapshots() -> tuple[CanonicalContentSnapshot, ...]:
    return tuple(
        CanonicalContentSnapshot.from_document(load_document(path))
        for path in CONTENT_PATHS
    )


def contents() -> tuple[ContentItem, ...]:
    return tuple(item.to_content_item() for item in content_snapshots())


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
    manifest: CorpusManifestSnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-stored-content",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can exact experiment inputs be reconstructed from storage?",
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
        stopping_rules=("Stop after every stored content artifact has one session.",),
        created_at="2026-08-02T23:16:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-stored-content",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256({"mode": "stored-content"}),
        hardware_profile="CPU-only synthetic execution",
    )


def windows() -> tuple[StoredContentExecutionWindow, ...]:
    return (
        StoredContentExecutionWindow(
            content_id="content-001",
            started_at="2026-08-02T23:17:00Z",
            completed_at="2026-08-02T23:17:01Z",
        ),
        StoredContentExecutionWindow(
            content_id="content-002",
            started_at="2026-08-02T23:17:02Z",
            completed_at="2026-08-02T23:17:03Z",
        ),
        StoredContentExecutionWindow(
            content_id="content-003",
            started_at="2026-08-02T23:17:04Z",
            completed_at="2026-08-02T23:17:05Z",
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
    CorpusManifestSnapshot,
    ExperimentPlan,
    tuple[PositionalSentimentFixture, PositionalSentimentFixture],
]:
    candidate_registry = registry_snapshot()
    manifest = corpus_snapshot()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate_registry, manifest, fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    persist_canonical_corpus(
        artifact_store,
        plan=plan,
        manifest=manifest,
        contents=contents(),
    )
    return artifact_store, candidate_registry, manifest, plan, fixture_analyzers


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    runtime_registry: AnalyzerRegistry | None = None,
    execution_windows: tuple[StoredContentExecutionWindow, ...] | None = None,
):
    (
        artifact_store,
        candidate_registry,
        manifest,
        plan,
        fixture_analyzers,
    ) = prepare_store(tmp_path, store=store)
    loaded_registry = runtime_registry or analyzer_registry(*fixture_analyzers)
    runner = StoredContentExperimentRunner(
        analyzer_registry=loaded_registry,
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate_registry,
        corpus_manifest=manifest,
        environment=environment(),
        windows=execution_windows or windows(),
        experiment_run_id="stored-run-001",
    )
    return receipt, artifact_store


def test_content_artifacts_validate_and_reconstruct_exact_inputs(tmp_path: Path) -> None:
    store, _, manifest, plan, _ = prepare_store(tmp_path)
    loaded = load_canonical_corpus(store, manifest)

    assert loaded.manifest_ref.artifact_hash == manifest.artifact_hash
    assert loaded.content_refs == manifest.content_artifact_refs
    assert loaded.contents == contents()
    assert tuple(item.text for item in loaded.contents) == tuple(
        item.text for item in content_snapshots()
    )
    assert plan.corpus_ref == manifest.reference()

    content_schema = load_document(CONTENT_SCHEMA_PATH)
    corpus_schema = load_document(CORPUS_SCHEMA_PATH)
    validator = Draft202012Validator(
        content_schema,
        format_checker=FormatChecker(),
    )
    for path in CONTENT_PATHS:
        validator.validate(load_document(path))
    Draft202012Validator(
        corpus_schema,
        format_checker=FormatChecker(),
    ).validate(load_document(CORPUS_PATH))


def test_runner_executes_from_ids_and_timestamps_only(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is StoredContentRunnerStatus.VERIFIED
    assert receipt.verified_checks == STORED_CONTENT_VERIFIED_CHECKS
    assert receipt.content_ids == ("content-001", "content-002", "content-003")
    assert receipt.content_artifact_refs == corpus_snapshot().content_artifact_refs
    assert tuple(
        item.workbench_status
        for item in receipt.corpus_bound_receipt.experiment_receipt.session_receipts
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
    Draft202012Validator(
        load_document(COMPLETION_SCHEMA_PATH),
        format_checker=FormatChecker(),
    ).validate(document)
    assert "text" not in document
    assert "aggregate_score" not in document
    assert "overall_status" not in document


def test_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.content_artifact_refs == second.content_artifact_refs
    assert first.completion_manifest_ref == second.completion_manifest_ref


def test_legacy_unlinked_manifest_cannot_drive_storage_backed_execution(
    tmp_path: Path,
) -> None:
    legacy = corpus_snapshot(LEGACY_CORPUS_PATH)
    candidate_registry = registry_snapshot()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate_registry, legacy, fixture_analyzers)
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    runner = StoredContentExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=store,
    )

    with pytest.raises(StoredContentExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=legacy,
            environment=environment(),
            windows=windows(),
            experiment_run_id="stored-run-legacy",
        )

    assert caught.value.stage is StoredContentRunnerStage.PREFLIGHT
    assert not list((tmp_path / "artifacts" / "ids" / "sha256").glob("*.json"))


def test_ingestion_rejects_tampered_text_before_manifest_write(tmp_path: Path) -> None:
    candidate_registry = registry_snapshot()
    manifest = corpus_snapshot()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate_registry, manifest, fixture_analyzers)
    original = contents()
    tampered = (
        replace(original[0], text="The launch was altered."),
        original[1],
        original[2],
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(Exception, match="UTF-8 text"):
        persist_canonical_corpus(
            store,
            plan=plan,
            manifest=manifest,
            contents=tampered,
        )

    with pytest.raises(ArtifactNotFoundError):
        store.get(manifest.corpus_id)


def test_content_artifact_reference_drift_prevents_manifest_completion(
    tmp_path: Path,
) -> None:
    candidate_registry = registry_snapshot()
    manifest = corpus_snapshot()
    fixture_analyzers = analyzers()
    wrong_reference = StoredArtifactRef(
        artifact_id=manifest.content_artifact_refs[1].artifact_id,
        artifact_hash="sha256:" + "0" * 64,
    )
    changed_entry = replace(
        manifest.contents[1],
        content_artifact_ref=wrong_reference,
    )
    changed_manifest = replace(
        manifest,
        contents=(manifest.contents[0], changed_entry, manifest.contents[2]),
    )
    plan = experiment_plan(candidate_registry, changed_manifest, fixture_analyzers)
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(CanonicalContentError, match="reference differs"):
        persist_canonical_corpus(
            store,
            plan=plan,
            manifest=changed_manifest,
            contents=contents(),
        )

    with pytest.raises(ArtifactNotFoundError):
        store.get(changed_manifest.corpus_id)


def test_missing_stored_content_fails_before_experiment_artifacts(tmp_path: Path) -> None:
    store, candidate_registry, manifest, plan, fixture_analyzers = prepare_store(tmp_path)
    failing_store = ContentReadFailsStore(
        store.root,
        manifest.content_artifact_refs[1].artifact_id,
    )
    runner = StoredContentExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing_store,
    )

    with pytest.raises(StoredContentExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=manifest,
            environment=environment(),
            windows=windows(),
            experiment_run_id="stored-run-001",
        )

    assert caught.value.stage is StoredContentRunnerStage.CONTENT_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_underlying_partial_progress_is_preserved_without_stored_completion(
    tmp_path: Path,
) -> None:
    store, candidate_registry, manifest, plan, fixture_analyzers = prepare_store(tmp_path)
    first, last = fixture_analyzers
    runner = StoredContentExperimentRunner(
        analyzer_registry=analyzer_registry(
            FailOnContentAnalyzer(first, "content-002"),
            last,
        ),
        artifact_store=store,
    )

    with pytest.raises(StoredContentExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=manifest,
            environment=environment(),
            windows=windows(),
            experiment_run_id="stored-run-001",
        )

    assert caught.value.stage is StoredContentRunnerStage.EXPERIMENT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    store.get("stored-run-001:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_stored_completion_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    normal = FileSystemArtifactStore(root)
    _, candidate_registry, manifest, plan, fixture_analyzers = prepare_store(
        tmp_path,
        store=normal,
    )
    failing = CompletionAppendFailsStore(root)
    runner = StoredContentExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing,
    )

    with pytest.raises(StoredContentExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=manifest,
            environment=environment(),
            windows=windows(),
            experiment_run_id="stored-run-001",
        )

    assert caught.value.stage is StoredContentRunnerStage.COMPLETION_PERSISTENCE
    assert caught.value.completed_content_ids == manifest.content_ids
    with pytest.raises(ArtifactNotFoundError):
        normal.get(COMPLETION_ID)


def test_stored_completion_reverification_failure_returns_no_receipt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    normal = FileSystemArtifactStore(root)
    _, candidate_registry, manifest, plan, fixture_analyzers = prepare_store(
        tmp_path,
        store=normal,
    )
    failing = SecondCompletionReadFailsStore(root)
    runner = StoredContentExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing,
    )

    with pytest.raises(StoredContentExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=manifest,
            environment=environment(),
            windows=windows(),
            experiment_run_id="stored-run-001",
        )

    assert caught.value.stage is StoredContentRunnerStage.VERIFICATION
    assert caught.value.completed_content_ids == manifest.content_ids
    assert normal.reference(COMPLETION_ID).artifact_id == COMPLETION_ID
