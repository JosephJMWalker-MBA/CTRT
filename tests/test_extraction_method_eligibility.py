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
from ctrt.eligible_extraction_runner import (
    ELIGIBLE_EXTRACTION_VERIFIED_CHECKS,
    EligibleExtractionExperimentError,
    EligibleExtractionExperimentRunner,
    EligibleExtractionRunnerStage,
    EligibleExtractionRunnerStatus,
)
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestSnapshot,
    SourceArtifactSnapshot,
    persist_extracted_corpus,
)
from ctrt.extraction_method_eligibility import (
    ExtractionMethodEligibilityError,
    ExtractionMethodRegistrySnapshot,
    MethodBoundExtractionCorpusSnapshot,
    validate_extraction_method_eligibility,
)
from ctrt.serialization import CanonicalArtifact, canonical_sha256
from ctrt.synthetic import (
    PositionalSentimentFixture,
    first_signal_fixture,
    last_signal_fixture,
)
from ctrt.workbench import AnalyzerRegistry

ROOT = Path(__file__).parents[1]
CANDIDATE_REGISTRY_PATH = (
    ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
)
METHOD_REGISTRY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-extraction-method-registry.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.2.0.json"
)
LEGACY_CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.1.0.json"
)
SOURCE_PATHS = tuple(
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "sources"
    / f"source-{index:03d}.json"
    for index in range(1, 4)
)
CONTENT_PATHS = tuple(
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "content"
    / f"content-{index:03d}.json"
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
REGISTRY_SCHEMA = ROOT / "schemas" / "extraction-method-registry.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "method-bound-extraction-corpus.schema.json"
REPORT_SCHEMA = ROOT / "schemas" / "extraction-method-eligibility-report.schema.json"
COMPLETION_SCHEMA = (
    ROOT / "schemas" / "eligible-extraction-experiment-completion.schema.json"
)
REPORT_ID = (
    "experiment.synthetic-extraction-eligibility:0.1.0:"
    "extraction-method-eligibility"
)
COMPLETION_ID = "eligible-extraction-run-001:eligible-extraction-completion"


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
            raise RuntimeError("synthetic eligible extraction execution failure")
        return self.base.analyze(content)


class CompletionAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(":eligible-extraction-completion"):
            raise ArtifactIntegrityError(
                "synthetic eligible extraction completion failure"
            )
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def candidate_registry() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(
        load_document(CANDIDATE_REGISTRY_PATH)
    )


def method_registry(
    document: dict[str, Any] | None = None,
) -> ExtractionMethodRegistrySnapshot:
    return ExtractionMethodRegistrySnapshot.from_document(
        document or load_document(METHOD_REGISTRY_PATH)
    )


def method_bound_corpus(
    registry: ExtractionMethodRegistrySnapshot | None = None,
) -> MethodBoundExtractionCorpusSnapshot:
    document = load_document(CORPUS_PATH)
    if registry is not None:
        document["method_registry_ref"] = {
            "artifact_id": registry.registry_id,
            "artifact_version": registry.registry_version,
            "artifact_hash": registry.artifact_hash,
        }
    return MethodBoundExtractionCorpusSnapshot.from_document(document)


def sources() -> tuple[SourceArtifactSnapshot, ...]:
    return tuple(
        SourceArtifactSnapshot.from_document(load_document(path))
        for path in SOURCE_PATHS
    )


def contents() -> tuple[ExtractedContentSnapshot, ...]:
    return tuple(
        ExtractedContentSnapshot.from_document(load_document(path))
        for path in CONTENT_PATHS
    )


def extractions() -> tuple[ExtractionManifestSnapshot, ...]:
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
    corpus: MethodBoundExtractionCorpusSnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-extraction-eligibility",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question=(
            "Can frozen method policy authorize exact extraction provenance?"
        ),
        protocol_ref=artifact(
            "protocol.synthetic-workbench",
            {"version": "0.1.0"},
        ),
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
        stopping_rules=(
            "Stop after every authorized extracted content item has one session.",
        ),
        created_at="2026-08-03T00:09:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-extraction-eligibility",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256(
            {"mode": "synthetic-extraction-eligibility"}
        ),
        hardware_profile="CPU-only synthetic execution",
    )


def windows() -> tuple[ExtractionExecutionWindow, ...]:
    return (
        ExtractionExecutionWindow(
            content_id="content-001",
            started_at="2026-08-03T00:10:00Z",
            completed_at="2026-08-03T00:10:01Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-002",
            started_at="2026-08-03T00:10:02Z",
            completed_at="2026-08-03T00:10:03Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-003",
            started_at="2026-08-03T00:10:04Z",
            completed_at="2026-08-03T00:10:05Z",
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
    method_registry_snapshot: ExtractionMethodRegistrySnapshot | None = None,
    store: FileSystemArtifactStore | None = None,
) -> tuple[
    FileSystemArtifactStore,
    CandidateRegistrySnapshot,
    ExtractionMethodRegistrySnapshot,
    MethodBoundExtractionCorpusSnapshot,
    ExperimentPlan,
    tuple[PositionalSentimentFixture, PositionalSentimentFixture],
]:
    candidate = candidate_registry()
    method = method_registry_snapshot or method_registry()
    corpus = method_bound_corpus(method)
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate, corpus, fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    persist_extracted_corpus(
        artifact_store,
        plan=plan,
        manifest=corpus.corpus,
        sources=sources(),
        extractions=extractions(),
        contents=contents(),
    )
    return (
        artifact_store,
        candidate,
        method,
        corpus,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    method_registry_snapshot: ExtractionMethodRegistrySnapshot | None = None,
    store: FileSystemArtifactStore | None = None,
    runtime_registry: AnalyzerRegistry | None = None,
):
    (
        artifact_store,
        candidate,
        method,
        corpus,
        plan,
        fixture_analyzers,
    ) = prepare_store(
        tmp_path,
        method_registry_snapshot=method_registry_snapshot,
        store=store,
    )
    runner = EligibleExtractionExperimentRunner(
        analyzer_registry=(
            runtime_registry or analyzer_registry(*fixture_analyzers)
        ),
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate,
        method_registry=method,
        corpus=corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id="eligible-extraction-run-001",
    )
    return receipt, artifact_store


def validate_schema(path: Path, document: dict[str, Any]) -> None:
    Draft202012Validator(
        load_document(path),
        format_checker=FormatChecker(),
    ).validate(document)


def registry_variant(**changes: object) -> ExtractionMethodRegistrySnapshot:
    document = load_document(METHOD_REGISTRY_PATH)
    method = cast(dict[str, Any], cast(list[object], document["methods"])[0])
    for path, value in changes.items():
        if path == "registry_status":
            document["status"] = value
        elif path == "license_status":
            cast(dict[str, Any], method["license_review"])["status"] = value
        elif path == "pin_required":
            cast(dict[str, Any], method["revision_policy"])[
                "pin_required"
            ] = value
        elif path == "pinned_revision":
            cast(dict[str, Any], method["revision_policy"])[
                "pinned_revision"
            ] = value
        else:
            method[path] = value
    return method_registry(document)


def eligibility_report(
    method: ExtractionMethodRegistrySnapshot | None = None,
):
    selected = method or method_registry()
    corpus = method_bound_corpus(selected)
    plan = experiment_plan(candidate_registry(), corpus, analyzers())
    return validate_extraction_method_eligibility(
        plan=plan,
        corpus=corpus,
        registry=selected,
        extractions=extractions(),
    )


def test_registry_corpus_and_report_schemas_validate() -> None:
    registry_document = load_document(METHOD_REGISTRY_PATH)
    corpus_document = load_document(CORPUS_PATH)
    validate_schema(REGISTRY_SCHEMA, registry_document)
    validate_schema(CORPUS_SCHEMA, corpus_document)

    report = eligibility_report()
    report_document = cast(
        dict[str, Any],
        json.loads(report.artifact().text),
    )
    validate_schema(REPORT_SCHEMA, report_document)
    assert report.method_registry_ref == method_registry().reference()
    assert tuple(item.content_id for item in report.authorized_extractions) == (
        "content-001",
        "content-002",
        "content-003",
    )


def test_runner_executes_only_after_method_authorization(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is EligibleExtractionRunnerStatus.VERIFIED
    assert receipt.verified_checks == ELIGIBLE_EXTRACTION_VERIFIED_CHECKS
    assert receipt.method_registry_ref.artifact_hash == method_registry().artifact_hash
    store.get(
        receipt.eligibility_report_ref.artifact_id,
        expected_hash=receipt.eligibility_report_ref.artifact_hash,
    )
    completion = store.get(
        receipt.completion_manifest_ref.artifact_id,
        expected_hash=receipt.completion_manifest_ref.artifact_hash,
    )
    document = cast(dict[str, Any], json.loads(completion.text))
    validate_schema(COMPLETION_SCHEMA, document)
    assert "aggregate_score" not in document
    assert "overall_status" not in document


def test_execution_is_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.method_registry_ref == second.method_registry_ref
    assert first.eligibility_report_ref == second.eligibility_report_ref
    assert first.completion_manifest_ref == second.completion_manifest_ref


def test_legacy_extraction_corpus_lacks_method_registry_binding() -> None:
    with pytest.raises(ValueError, match="method_registry_ref"):
        MethodBoundExtractionCorpusSnapshot.from_document(
            load_document(LEGACY_CORPUS_PATH)
        )


def test_registry_hash_mismatch_fails_closed() -> None:
    changed = registry_variant(license_status="verified")
    corpus = method_bound_corpus()
    plan = experiment_plan(candidate_registry(), corpus, analyzers())

    with pytest.raises(
        ExtractionMethodEligibilityError,
        match="method_registry_ref",
    ):
        validate_extraction_method_eligibility(
            plan=plan,
            corpus=corpus,
            registry=changed,
            extractions=extractions(),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"registry_status": "draft"}, "must be accepted"),
        ({"license_status": "blocked"}, "license review is blocked"),
        (
            {"pinned_revision": "ctrt-synthetic-identity-text@0.2.0"},
            "revision differs",
        ),
        (
            {"supported_source_types": ["webpage"]},
            "source type is not supported",
        ),
        (
            {"authorized_configuration_hashes": ["sha256:" + "0" * 64]},
            "configuration hash is not authorized",
        ),
        ({"methods": []}, "absent from the registry"),
    ],
)
def test_method_policy_failures_are_explicit(
    changes: dict[str, object],
    message: str,
) -> None:
    if "methods" in changes:
        document = load_document(METHOD_REGISTRY_PATH)
        document["methods"] = []
        changed = method_registry(document)
    else:
        changed = registry_variant(**changes)
    corpus = method_bound_corpus(changed)
    plan = experiment_plan(candidate_registry(), corpus, analyzers())

    with pytest.raises(ExtractionMethodEligibilityError, match=message):
        validate_extraction_method_eligibility(
            plan=plan,
            corpus=corpus,
            registry=changed,
            extractions=extractions(),
        )


def test_eligibility_failure_prevents_execution_and_report_write(
    tmp_path: Path,
) -> None:
    blocked = registry_variant(license_status="blocked")
    (
        store,
        candidate,
        method,
        corpus,
        plan,
        fixture_analyzers,
    ) = prepare_store(tmp_path, method_registry_snapshot=blocked)
    runner = EligibleExtractionExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=store,
    )

    with pytest.raises(EligibleExtractionExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate,
            method_registry=method,
            corpus=corpus,
            environment=environment(),
            windows=windows(),
            experiment_run_id="eligible-extraction-blocked",
        )

    assert caught.value.stage is EligibleExtractionRunnerStage.ELIGIBILITY
    with pytest.raises(ArtifactNotFoundError):
        store.get(REPORT_ID)
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            "eligible-extraction-blocked:0000:content-001:"
            "governed-session:receipt"
        )


def test_later_execution_failure_preserves_authorization_and_prior_receipt(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(EligibleExtractionExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=runtime,
        )

    assert caught.value.stage is EligibleExtractionRunnerStage.EXPERIMENT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    store.get(method_registry().registry_id)
    store.get(REPORT_ID)
    store.get(
        "eligible-extraction-run-001:0000:content-001:"
        "governed-session:receipt"
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)


def test_completion_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = CompletionAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(EligibleExtractionExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is EligibleExtractionRunnerStage.COMPLETION_PERSISTENCE
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    store.get(method_registry().registry_id)
    store.get(REPORT_ID)
    with pytest.raises(ArtifactNotFoundError):
        store.get(COMPLETION_ID)
