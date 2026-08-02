from __future__ import annotations

import hashlib
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
from ctrt.contracts import AnalyzerIdentity, ContentItem, ModelResult, SourceType
from ctrt.corpus_bound_runner import (
    CORPUS_BOUND_VERIFIED_CHECKS,
    CorpusBoundExperimentError,
    CorpusBoundExperimentRunner,
    CorpusBoundRunnerStage,
    CorpusBoundRunnerStatus,
    VerifiedCorpusBoundExperimentReceipt,
)
from ctrt.corpus_manifest import CorpusManifestSnapshot
from ctrt.experiment_runner import ContentExecutionRequest
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.serialization import CanonicalArtifact, canonical_sha256
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "synthetic-three-items.v0.1.0.json"
CORPUS_SCHEMA_PATH = ROOT / "schemas" / "corpus-manifest.schema.json"
COMPLETION_SCHEMA_PATH = (
    ROOT / "schemas" / "corpus-bound-experiment-completion.schema.json"
)
BOUND_COMPLETION_ID = "experiment-run-001:corpus-bound-completion"


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
            raise RuntimeError("synthetic second-content failure")
        return self.base.analyze(content)


class CorpusAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id == "corpus.synthetic-three-items":
            raise ArtifactIntegrityError("synthetic corpus persistence failure")
        return super().append(artifact)


class SecondBoundCompletionReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._completion_reads = 0

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id.endswith(":corpus-bound-completion"):
            self._completion_reads += 1
            if self._completion_reads == 2:
                raise ArtifactIntegrityError(
                    "synthetic corpus-bound completion reverification failure"
                )
        return super().get(artifact_id, expected_hash=expected_hash)


def _document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def registry_snapshot() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(_document(REGISTRY_PATH))


def corpus_snapshot() -> CorpusManifestSnapshot:
    return CorpusManifestSnapshot.from_document(_document(CORPUS_PATH))


def artifact(artifact_id: str, value: object) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=canonical_sha256(value),
    )


def analyzers() -> tuple[PositionalSentimentFixture, PositionalSentimentFixture]:
    return first_signal_fixture(), last_signal_fixture()


def plan(
    registry: CandidateRegistrySnapshot,
    manifest: CorpusManifestSnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-corpus-bound",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Does exact corpus binding fail closed before execution?",
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
        stopping_rules=("Stop after every frozen corpus item has one session.",),
        created_at="2026-08-02T22:41:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-corpus-bound",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256({"mode": "corpus-bound"}),
        hardware_profile="CPU-only synthetic execution",
    )


def content(
    content_id: str,
    text: str,
    *,
    language: str = "en",
    source_type: SourceType = SourceType.RAW_TEXT,
    extraction_ref: str | None = None,
    content_hash: str | None = None,
) -> ContentItem:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ContentItem(
        content_id=content_id,
        text=text,
        source_type=source_type,
        content_hash=content_hash or f"sha256:{digest}",
        language=language,
        extraction_ref=extraction_ref,
    )


def requests() -> tuple[ContentExecutionRequest, ...]:
    return (
        ContentExecutionRequest(
            content=content(
                "content-001",
                "The launch was good, but the support was bad.",
            ),
            started_at="2026-08-02T22:42:00Z",
            completed_at="2026-08-02T22:42:01Z",
        ),
        ContentExecutionRequest(
            content=content(
                "content-002",
                "The launch was good and the support was good.",
            ),
            started_at="2026-08-02T22:42:02Z",
            completed_at="2026-08-02T22:42:03Z",
        ),
        ContentExecutionRequest(
            content=content(
                "content-003",
                "The report contains no fixture vocabulary.",
            ),
            started_at="2026-08-02T22:42:04Z",
            completed_at="2026-08-02T22:42:05Z",
        ),
    )


def analyzer_registry(*items: object) -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for item in items:
        registry.register(cast(Any, item))
    return registry


def execute(
    tmp_path: Path,
    *,
    execution_requests: tuple[ContentExecutionRequest, ...] | None = None,
    experiment_plan: ExperimentPlan | None = None,
    manifest: CorpusManifestSnapshot | None = None,
    runtime_registry: AnalyzerRegistry | None = None,
    store: FileSystemArtifactStore | None = None,
) -> tuple[VerifiedCorpusBoundExperimentReceipt, FileSystemArtifactStore]:
    candidate_registry = registry_snapshot()
    frozen_manifest = manifest or corpus_snapshot()
    fixture_analyzers = analyzers()
    loaded_registry = runtime_registry or analyzer_registry(*fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    runner = CorpusBoundExperimentRunner(
        analyzer_registry=loaded_registry,
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=experiment_plan
        or plan(candidate_registry, frozen_manifest, fixture_analyzers),
        candidate_registry=candidate_registry,
        corpus_manifest=frozen_manifest,
        environment=environment(),
        requests=execution_requests or requests(),
        experiment_run_id="experiment-run-001",
    )
    return receipt, artifact_store


def assert_empty_store(tmp_path: Path) -> None:
    index_root = tmp_path / "artifacts" / "ids" / "sha256"
    assert not list(index_root.glob("*.json"))


def test_exact_frozen_corpus_completes_without_aggregate_output(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is CorpusBoundRunnerStatus.VERIFIED
    assert receipt.verified_checks == CORPUS_BOUND_VERIFIED_CHECKS
    assert receipt.content_ids == ("content-001", "content-002", "content-003")
    assert receipt.corpus_manifest_ref.artifact_id == "corpus.synthetic-three-items"

    corpus_document = _document(CORPUS_PATH)
    corpus_schema = _document(CORPUS_SCHEMA_PATH)
    Draft202012Validator(
        corpus_schema,
        format_checker=FormatChecker(),
    ).validate(corpus_document)

    completion_artifact = store.get(
        receipt.completion_manifest_ref.artifact_id,
        expected_hash=receipt.completion_manifest_ref.artifact_hash,
    )
    completion_document = cast(
        dict[str, Any],
        json.loads(completion_artifact.text),
    )
    completion_schema = _document(COMPLETION_SCHEMA_PATH)
    Draft202012Validator(
        completion_schema,
        format_checker=FormatChecker(),
    ).validate(completion_document)
    assert "aggregate_score" not in completion_document
    assert "overall_status" not in completion_document
    assert completion_document["experiment_completion_ref"] == {
        "artifact_id": "experiment-run-001:experiment-completion",
        "artifact_hash": receipt.experiment_receipt.completion_manifest_ref.artifact_hash,
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }


def test_identical_corpus_bound_run_is_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.corpus_manifest_ref == second.corpus_manifest_ref
    assert first.completion_manifest_ref == second.completion_manifest_ref


@pytest.mark.parametrize(
    "mutated_requests",
    [
        lambda items: (items[1], items[0], items[2]),
        lambda items: items[:2],
        lambda items: (*items, items[0]),
        lambda items: (items[0], items[0], items[2]),
    ],
)
def test_scope_drift_fails_before_any_artifact_write(
    tmp_path: Path,
    mutated_requests: Any,
) -> None:
    items = requests()

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(tmp_path, execution_requests=tuple(mutated_requests(items)))

    assert caught.value.stage is CorpusBoundRunnerStage.PREFLIGHT
    assert_empty_store(tmp_path)


def test_changed_text_with_stale_hash_fails_before_write(tmp_path: Path) -> None:
    items = list(requests())
    original = items[0].content
    altered = content(
        original.content_id,
        original.text + " altered",
        content_hash=original.content_hash,
    )
    items[0] = replace(items[0], content=altered)

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(tmp_path, execution_requests=tuple(items))

    assert caught.value.stage is CorpusBoundRunnerStage.PREFLIGHT
    assert "UTF-8 text" in str(caught.value)
    assert_empty_store(tmp_path)


def test_substituted_valid_hash_fails_manifest_binding(tmp_path: Path) -> None:
    items = list(requests())
    altered_text = items[0].content.text + " altered"
    items[0] = replace(
        items[0],
        content=content("content-001", altered_text),
    )

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(tmp_path, execution_requests=tuple(items))

    assert caught.value.stage is CorpusBoundRunnerStage.PREFLIGHT
    assert "corpus manifest" in str(caught.value)
    assert_empty_store(tmp_path)


@pytest.mark.parametrize(
    ("field", "replacement_value", "expected_message"),
    [
        ("language", "fr", "language differs"),
        ("source_type", SourceType.WEBPAGE, "source type differs"),
        (
            "extraction_ref",
            "extraction:other",
            "extraction identity differs",
        ),
    ],
)
def test_metadata_drift_fails_before_write(
    tmp_path: Path,
    field: str,
    replacement_value: object,
    expected_message: str,
) -> None:
    items = list(requests())
    original = items[0].content
    kwargs: dict[str, object] = {
        "language": original.language or "en",
        "source_type": original.source_type,
        "extraction_ref": original.extraction_ref,
    }
    kwargs[field] = replacement_value
    mutated = content(
        original.content_id,
        original.text,
        language=cast(str, kwargs["language"]),
        source_type=cast(SourceType, kwargs["source_type"]),
        extraction_ref=cast(str | None, kwargs["extraction_ref"]),
    )
    items[0] = replace(items[0], content=mutated)

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(tmp_path, execution_requests=tuple(items))

    assert caught.value.stage is CorpusBoundRunnerStage.PREFLIGHT
    assert expected_message in str(caught.value)
    assert_empty_store(tmp_path)


def test_plan_corpus_reference_drift_fails_before_write(tmp_path: Path) -> None:
    candidate_registry = registry_snapshot()
    manifest = corpus_snapshot()
    fixture_analyzers = analyzers()
    frozen_plan = plan(candidate_registry, manifest, fixture_analyzers)
    mismatched_ref = replace(
        frozen_plan.corpus_ref,
        artifact_hash="sha256:" + "f" * 64,
    )

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(
            tmp_path,
            experiment_plan=replace(frozen_plan, corpus_ref=mismatched_ref),
            manifest=manifest,
        )

    assert caught.value.stage is CorpusBoundRunnerStage.PREFLIGHT
    assert "corpus_ref" in str(caught.value)
    assert_empty_store(tmp_path)


def test_corpus_persistence_failure_stops_before_sessions(tmp_path: Path) -> None:
    store = CorpusAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is CorpusBoundRunnerStage.CORPUS_PERSISTENCE
    with pytest.raises(ArtifactNotFoundError):
        store.get("experiment-run-001:experiment-completion")


def test_later_session_failure_preserves_prior_progress_without_bound_completion(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(
            tmp_path,
            runtime_registry=runtime_registry,
            store=store,
        )

    assert caught.value.stage is CorpusBoundRunnerStage.EXPERIMENT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    assert store.reference("corpus.synthetic-three-items").artifact_id == (
        "corpus.synthetic-three-items"
    )
    store.get("experiment-run-001:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get(BOUND_COMPLETION_ID)


def test_bound_completion_reverification_failure_returns_no_receipt(
    tmp_path: Path,
) -> None:
    store = SecondBoundCompletionReadFailsStore(tmp_path / "artifacts")

    with pytest.raises(CorpusBoundExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is CorpusBoundRunnerStage.VERIFICATION
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    assert store.reference(BOUND_COMPLETION_ID).artifact_id == BOUND_COMPLETION_ID
