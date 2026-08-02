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
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.contracts import AnalyzerIdentity, ContentItem, ModelResult, ResultStatus, SourceType
from ctrt.execution_session import (
    ExecutionSessionStage,
    ExecutionSessionStatus,
    GovernedExecutionError,
    GovernedExecutionSession,
    VERIFIED_CHECKS,
)
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.serialization import CanonicalArtifact, canonical_data, canonical_sha256
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry, WorkbenchReportStatus

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
RECEIPT_SCHEMA_PATH = ROOT / "schemas" / "governed-execution-receipt.schema.json"


@dataclass(frozen=True, slots=True)
class AnalyzerProxy:
    base: PositionalSentimentFixture
    revision_override: str | None = None
    configuration_override: Mapping[str, object] | None = None
    explode: bool = False

    @property
    def dimension_id(self) -> str:
        return self.base.dimension_id

    @property
    def implementation_revision(self) -> str:
        return self.revision_override or self.base.implementation_revision

    @property
    def execution_configuration(self) -> Mapping[str, object]:
        return self.configuration_override or self.base.execution_configuration

    @property
    def identity(self) -> AnalyzerIdentity:
        return self.base.identity

    def analyze(self, content: ContentItem) -> ModelResult:
        if self.explode:
            raise RuntimeError("synthetic execution failure")
        return self.base.analyze(content)


class FailingAppendStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        raise ArtifactIntegrityError("synthetic persistence failure")


class ThirdManifestReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._manifest_reads = 0

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id.endswith(":artifact-bundle"):
            self._manifest_reads += 1
            if self._manifest_reads == 3:
                raise ArtifactIntegrityError("synthetic post-persistence verification failure")
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


def plan(
    registry: CandidateRegistrySnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
    *,
    content_ids: tuple[str, ...] = ("content-001",),
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-governed-session",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can one governed session return only after stored verification?",
        protocol_ref=artifact("protocol.synthetic-workbench", {"version": "0.1.0"}),
        candidate_registry_ref=registry.reference(),
        corpus_ref=artifact("corpus.synthetic-vocabulary", {"content_ids": content_ids}),
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
        stopping_rules=("Stop after the declared content has one result per analyzer.",),
        created_at="2026-08-02T22:00:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-governed-session",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256({"mode": "synthetic"}),
        hardware_profile="CPU-only synthetic execution",
    )


def content(
    text: str = "The launch was good, but the support was bad.",
    *,
    content_id: str = "content-001",
) -> ContentItem:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ContentItem(
        content_id=content_id,
        text=text,
        source_type=SourceType.RAW_TEXT,
        content_hash=f"sha256:{digest}",
        language="en",
    )


def analyzer_registry(*items: object) -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for item in items:
        registry.register(cast(Any, item))
    return registry


def execute(
    tmp_path: Path,
    *,
    loaded_registry: AnalyzerRegistry | None = None,
    store: FileSystemArtifactStore | None = None,
    item: ContentItem | None = None,
):
    candidate_registry = registry_snapshot()
    fixture_analyzers = analyzers()
    runtime_registry = loaded_registry or analyzer_registry(*fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    session = GovernedExecutionSession(
        analyzer_registry=runtime_registry,
        artifact_store=artifact_store,
    )
    receipt = session.execute(
        plan=plan(candidate_registry, fixture_analyzers),
        candidate_registry=candidate_registry,
        environment=environment(),
        content=item or content(),
        run_id="run-001",
        started_at="2026-08-02T22:01:00Z",
        completed_at="2026-08-02T22:01:01Z",
    )
    return receipt, artifact_store


def test_verified_receipt_preserves_abstained_measurement_outcome(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is ExecutionSessionStatus.VERIFIED
    assert receipt.workbench_status is WorkbenchReportStatus.ABSTAINED
    assert receipt.result_statuses == (ResultStatus.SUCCESS, ResultStatus.SUCCESS)
    assert receipt.verified_checks == VERIFIED_CHECKS
    stored_manifest = store.get(
        receipt.manifest_ref.artifact_id,
        expected_hash=receipt.manifest_ref.artifact_hash,
    )
    assert stored_manifest.artifact_id == receipt.bundle_id

    schema = cast(
        dict[str, Any],
        json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8")),
    )
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(canonical_data(receipt))


def test_verified_receipt_preserves_analyzer_abstentions(tmp_path: Path) -> None:
    receipt, _ = execute(
        tmp_path,
        item=content("The report contains no fixture vocabulary."),
    )

    assert receipt.status is ExecutionSessionStatus.VERIFIED
    assert receipt.workbench_status is WorkbenchReportStatus.ABSTAINED
    assert receipt.result_statuses == (ResultStatus.ABSTAINED, ResultStatus.ABSTAINED)


def test_unauthorized_content_fails_preflight_without_manifest(tmp_path: Path) -> None:
    with pytest.raises(GovernedExecutionError) as caught:
        execute(tmp_path, item=content(content_id="content-unauthorized"))

    assert caught.value.stage is ExecutionSessionStage.PREFLIGHT
    assert not list((tmp_path / "artifacts" / "ids" / "sha256").glob("*.json"))


def test_runtime_revision_drift_fails_preflight(tmp_path: Path) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        AnalyzerProxy(first, revision_override="ctrt-fixture-first@9.9.9"),
        last,
    )

    with pytest.raises(GovernedExecutionError) as caught:
        execute(tmp_path, loaded_registry=runtime_registry)

    assert caught.value.stage is ExecutionSessionStage.PREFLIGHT
    assert "implementation revision" in str(caught.value)


def test_runtime_configuration_drift_fails_preflight(tmp_path: Path) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        AnalyzerProxy(first, configuration_override={"selection": "tampered"}),
        last,
    )

    with pytest.raises(GovernedExecutionError) as caught:
        execute(tmp_path, loaded_registry=runtime_registry)

    assert caught.value.stage is ExecutionSessionStage.PREFLIGHT
    assert "execution configuration" in str(caught.value)


def test_analyzer_exception_fails_execution_without_receipt(tmp_path: Path) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(AnalyzerProxy(first, explode=True), last)

    with pytest.raises(GovernedExecutionError) as caught:
        execute(tmp_path, loaded_registry=runtime_registry)

    assert caught.value.stage is ExecutionSessionStage.EXECUTION
    assert "synthetic execution failure" in str(caught.value)


def test_store_failure_is_reported_as_persistence_failure(tmp_path: Path) -> None:
    store = FailingAppendStore(tmp_path / "artifacts")

    with pytest.raises(GovernedExecutionError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExecutionSessionStage.PERSISTENCE
    assert "synthetic persistence failure" in str(caught.value)


def test_post_persistence_manifest_failure_prevents_verified_receipt(tmp_path: Path) -> None:
    store = ThirdManifestReadFailsStore(tmp_path / "artifacts")

    with pytest.raises(GovernedExecutionError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is ExecutionSessionStage.VERIFICATION
    assert "post-persistence verification failure" in str(caught.value)
