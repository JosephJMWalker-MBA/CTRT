from __future__ import annotations

import hashlib
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
from ctrt.contracts import AnalyzerIdentity, ContentItem, ModelResult, ResultStatus, SourceType
from ctrt.experiment_runner import (
    EXPERIMENT_VERIFIED_CHECKS,
    ContentExecutionRequest,
    ExperimentRunnerStage,
    ExperimentRunnerStatus,
    MultiContentExperimentError,
    MultiContentExperimentRunner,
    VerifiedExperimentReceipt,
)
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
from ctrt.workbench import AnalyzerRegistry, WorkbenchReportStatus

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
SCHEMA_PATH = ROOT / "schemas" / "experiment-completion-manifest.schema.json"
COMPLETION_ID = "experiment-run-001:experiment-completion"


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
            raise RuntimeError("synthetic second-content execution failure")
        return self.base.analyze(content)


class SecondReceiptAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if ":0001:content-002:governed-session:receipt" in artifact.artifact_id:
            raise ArtifactIntegrityError("synthetic second receipt persistence failure")
        return super().append(artifact)


class CompletionAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(":experiment-completion"):
            raise ArtifactIntegrityError("synthetic completion persistence failure")
        return super().append(artifact)


class FourthBundleReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._bundle_reads: dict[str, int] = {}

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id.endswith(":artifact-bundle"):
            count = self._bundle_reads.get(artifact_id, 0) + 1
            self._bundle_reads[artifact_id] = count
            if ":0000:content-001:" in artifact_id and count == 4:
                raise ArtifactIntegrityError("synthetic bundle reload failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class SecondCompletionReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._completion_reads = 0

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id.endswith(":experiment-completion"):
            self._completion_reads += 1
            if self._completion_reads == 2:
                raise ArtifactIntegrityError(
                    "synthetic completion manifest reverification failure"
                )
        return super().get(artifact_id, expected_hash=expected_hash)


def registry_snapshot() -> CandidateRegistrySnapshot:
    document = cast(
        dict[str, Any],
        json.loads(REGISTRY_PATH.read_text(encoding="utf-8")),
    )
    return CandidateRegistrySnapshot.from_document(document)


def artifact(artifact_id: str, value: object) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=canonical_sha256(value),
    )


def analyzers() -> tuple[PositionalSentimentFixture, PositionalSentimentFixture]:
    return first_signal_fixture(), last_signal_fixture()


def experiment_plan(
    registry: CandidateRegistrySnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    content_ids = ("content-001", "content-002", "content-003")
    return ExperimentPlan(
        experiment_id="experiment.synthetic-multi-content",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can every declared synthetic content run verify independently?",
        protocol_ref=artifact("protocol.synthetic-workbench", {"version": "0.1.0"}),
        candidate_registry_ref=registry.reference(),
        corpus_ref=artifact("corpus.synthetic-three-items", {"content_ids": content_ids}),
        content_ids=content_ids,
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
        stopping_rules=("Stop after every declared content item has one session.",),
        created_at="2026-08-02T22:25:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-multi-content",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256({"mode": "synthetic-multi"}),
        hardware_profile="CPU-only synthetic execution",
    )


def content(content_id: str, text: str) -> ContentItem:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ContentItem(
        content_id=content_id,
        text=text,
        source_type=SourceType.RAW_TEXT,
        content_hash=f"sha256:{digest}",
        language="en",
    )


def execution_requests() -> tuple[ContentExecutionRequest, ...]:
    return (
        ContentExecutionRequest(
            content=content(
                "content-001",
                "The launch was good, but the support was bad.",
            ),
            started_at="2026-08-02T22:26:00Z",
            completed_at="2026-08-02T22:26:01Z",
        ),
        ContentExecutionRequest(
            content=content(
                "content-002",
                "The launch was good and the support was good.",
            ),
            started_at="2026-08-02T22:26:02Z",
            completed_at="2026-08-02T22:26:03Z",
        ),
        ContentExecutionRequest(
            content=content(
                "content-003",
                "The report contains no fixture vocabulary.",
            ),
            started_at="2026-08-02T22:26:04Z",
            completed_at="2026-08-02T22:26:05Z",
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
    runtime_registry: AnalyzerRegistry | None = None,
    store: FileSystemArtifactStore | None = None,
    requests: tuple[ContentExecutionRequest, ...] | None = None,
) -> tuple[VerifiedExperimentReceipt, FileSystemArtifactStore]:
    candidate_registry = registry_snapshot()
    fixture_analyzers = analyzers()
    loaded_registry = runtime_registry or analyzer_registry(*fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    runner = MultiContentExperimentRunner(
        analyzer_registry=loaded_registry,
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=experiment_plan(candidate_registry, fixture_analyzers),
        candidate_registry=candidate_registry,
        environment=environment(),
        requests=requests or execution_requests(),
        experiment_run_id="experiment-run-001",
    )
    return receipt, artifact_store


def test_all_declared_sessions_verify_without_aggregate_measurement(
    tmp_path: Path,
) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is ExperimentRunnerStatus.VERIFIED
    assert receipt.verified_checks == EXPERIMENT_VERIFIED_CHECKS
    assert receipt.content_ids == ("content-001", "content-002", "content-003")
    assert tuple(item.run_id for item in receipt.session_receipts) == (
        "experiment-run-001:0000:content-001",
        "experiment-run-001:0001:content-002",
        "experiment-run-001:0002:content-003",
    )
    assert tuple(item.workbench_status for item in receipt.session_receipts) == (
        WorkbenchReportStatus.ABSTAINED,
        WorkbenchReportStatus.COMPLETE,
        WorkbenchReportStatus.ABSTAINED,
    )
    assert receipt.session_receipts[0].result_statuses == (
        ResultStatus.SUCCESS,
        ResultStatus.SUCCESS,
    )
    assert receipt.session_receipts[2].result_statuses == (
        ResultStatus.ABSTAINED,
        ResultStatus.ABSTAINED,
    )

    manifest_artifact = store.get(
        receipt.completion_manifest_ref.artifact_id,
        expected_hash=receipt.completion_manifest_ref.artifact_hash,
    )
    document = cast(dict[str, Any], json.loads(manifest_artifact.text))
    schema = cast(dict[str, Any], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(document)
    assert "aggregate_score" not in document
    assert "overall_status" not in document
    assert [item["content_id"] for item in document["sessions"]] == list(
        receipt.content_ids
    )

    for reference in receipt.session_receipt_refs:
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)


def test_identical_multi_content_run_is_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.completion_manifest_ref == second.completion_manifest_ref
    assert first.session_receipt_refs == second.session_receipt_refs


def test_request_order_must_exactly_match_frozen_content_scope(tmp_path: Path) -> None:
    requests = execution_requests()
    reordered = (requests[1], requests[0], requests[2])

    with pytest.raises(MultiContentExperimentError) as caught:
        execute(tmp_path, requests=reordered)

    assert caught.value.stage is ExperimentRunnerStage.PREFLIGHT
    assert not list((tmp_path / "artifacts" / "ids" / "sha256").glob("*.json"))


def test_second_session_failure_preserves_first_receipt_without_completion(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(MultiContentExperimentError) as caught:
        execute(
            tmp_path,
            runtime_registry=runtime_registry,
            store=store,
        )

    assert caught.value.stage is ExperimentRunnerStage.SESSION_EXECUTION
    assert caught.value.content_id == "content-002"
    assert caught.value.completed_content_ids == ("content-001",)
    store.get(
        "experiment-run-001:0000:content-001:governed-session:receipt"
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_second_receipt_failure_prevents_completion_manifest(tmp_path: Path) -> None:
    store = SecondReceiptAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(MultiContentExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExperimentRunnerStage.RECEIPT_PERSISTENCE
    assert caught.value.content_id == "content-002"
    assert caught.value.completed_content_ids == ("content-001",)
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_bundle_reload_failure_occurs_before_completion_write(tmp_path: Path) -> None:
    store = FourthBundleReadFailsStore(tmp_path / "artifacts")

    with pytest.raises(MultiContentExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExperimentRunnerStage.VERIFICATION
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_completion_append_failure_returns_no_verified_receipt(tmp_path: Path) -> None:
    store = CompletionAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(MultiContentExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExperimentRunnerStage.COMPLETION_PERSISTENCE
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_completion_reverification_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = SecondCompletionReadFailsStore(tmp_path / "artifacts")

    with pytest.raises(MultiContentExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExperimentRunnerStage.VERIFICATION
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    assert store.reference(COMPLETION_ID).artifact_id == COMPLETION_ID
