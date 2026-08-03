from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
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
from ctrt.confidence import ExtractionQualityStatus
from ctrt.contracts import AnalyzerIdentity, ContentItem, ModelResult
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
)
from ctrt.extraction_method_eligibility import (
    ExtractionMethodRegistrySnapshot,
)
from ctrt.extraction_quality import (
    AutomatedCheckOutcome,
    ExtractionQualityAssessmentSnapshot,
    ExtractionQualityEvidenceError,
    ExtractionQualityPolicySnapshot,
    QualityBoundExtractionCorpusSnapshot,
    QualityDecisionOutcome,
    load_quality_evidence,
    persist_quality_bound_corpus,
)
from ctrt.quality_gated_extraction_runner import (
    QUALITY_GATED_VERIFIED_CHECKS,
    QualityGatedExperimentError,
    QualityGatedExtractionExperimentRunner,
    QualityGatedRunnerStage,
    QualityGatedRunnerStatus,
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
QUALITY_POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-extraction-quality-policy.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.3.0.json"
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
QUALITY_PATHS = tuple(
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "quality"
    / f"quality-content-{index:03d}.json"
    for index in range(1, 4)
)
POLICY_SCHEMA = ROOT / "schemas" / "extraction-quality-policy.schema.json"
ASSESSMENT_SCHEMA = (
    ROOT / "schemas" / "extraction-quality-assessment.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / "quality-bound-extraction-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "extraction-quality-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "quality-gated-extraction-final.schema.json"


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
            raise RuntimeError("synthetic quality-gated execution failure")
        return self.base.analyze(content)


class AssessmentReadFailsStore(FileSystemArtifactStore):
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
            raise ArtifactIntegrityError(
                "synthetic quality assessment read failure"
            )
        return super().get(artifact_id, expected_hash=expected_hash)


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (":quality-gated-completion", ":quality-abstention")
        ):
            raise ArtifactIntegrityError("synthetic quality final failure")
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def candidate_registry() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(
        load_document(CANDIDATE_REGISTRY_PATH)
    )


def method_registry() -> ExtractionMethodRegistrySnapshot:
    return ExtractionMethodRegistrySnapshot.from_document(
        load_document(METHOD_REGISTRY_PATH)
    )


def quality_policy() -> ExtractionQualityPolicySnapshot:
    return ExtractionQualityPolicySnapshot.from_document(
        load_document(QUALITY_POLICY_PATH)
    )


def quality_corpus(
    document: dict[str, Any] | None = None,
) -> QualityBoundExtractionCorpusSnapshot:
    return QualityBoundExtractionCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


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


def quality_snapshots() -> tuple[ExtractionQualityAssessmentSnapshot, ...]:
    return tuple(
        ExtractionQualityAssessmentSnapshot.from_document(load_document(path))
        for path in QUALITY_PATHS
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
    corpus: QualityBoundExtractionCorpusSnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-quality-gated",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question=(
            "Can independent extraction-quality evidence gate analyzer execution?"
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
                configuration_hash=canonical_sha256(
                    first.execution_configuration
                ),
            ),
            InstrumentRevision(
                candidate_id="fixture.last-signal",
                analyzer_id=last.identity.analyzer_id,
                dimension_id=last.dimension_id,
                implementation_revision=last.implementation_revision,
                adapter_version=last.identity.adapter_version,
                configuration_hash=canonical_sha256(
                    last.execution_configuration
                ),
            ),
        ),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=(),
        stopping_rules=(
            "Abstain before analysis when extraction quality requires it.",
        ),
        created_at="2026-08-03T00:30:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-quality-gated",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256(
            {"mode": "synthetic-quality-gated"}
        ),
        hardware_profile="CPU-only synthetic execution",
    )


def windows() -> tuple[ExtractionExecutionWindow, ...]:
    return (
        ExtractionExecutionWindow(
            content_id="content-001",
            started_at="2026-08-03T00:31:00Z",
            completed_at="2026-08-03T00:31:01Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-002",
            started_at="2026-08-03T00:31:02Z",
            completed_at="2026-08-03T00:31:03Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-003",
            started_at="2026-08-03T00:31:04Z",
            completed_at="2026-08-03T00:31:05Z",
        ),
    )


def analyzer_registry(*items: object) -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for item in items:
        registry.register(cast(Any, item))
    return registry


def validate_schema(path: Path, document: dict[str, Any]) -> None:
    Draft202012Validator(
        load_document(path),
        format_checker=FormatChecker(),
    ).validate(document)


def rebuild_quality_case(
    *,
    index: int,
    mutate: Any,
    corpus_version: str,
) -> tuple[
    QualityBoundExtractionCorpusSnapshot,
    tuple[ExtractionQualityAssessmentSnapshot, ...],
]:
    documents = [load_document(path) for path in QUALITY_PATHS]
    changed = deepcopy(documents[index])
    mutate(changed)
    changed["assessment_id"] = (
        f"{changed['assessment_id']}.{corpus_version}"
    )
    changed["artifact_id"] = f"extraction-quality:{changed['assessment_id']}"
    documents[index] = changed
    assessments = tuple(
        ExtractionQualityAssessmentSnapshot.from_document(document)
        for document in documents
    )

    corpus_document = load_document(CORPUS_PATH)
    corpus_document["corpus_version"] = corpus_version
    corpus_document["created_at"] = "2026-08-03T00:32:00Z"
    quality_ref = assessments[index].reference()
    corpus_document["contents"][index]["quality_assessment_ref"] = {
        "artifact_id": quality_ref.artifact_id,
        "artifact_hash": quality_ref.artifact_hash,
        "canonicalization_version": quality_ref.canonicalization_version,
        "media_type": quality_ref.media_type,
    }
    return quality_corpus(corpus_document), assessments


def prepare_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    corpus: QualityBoundExtractionCorpusSnapshot | None = None,
    assessments: tuple[ExtractionQualityAssessmentSnapshot, ...] | None = None,
) -> tuple[
    FileSystemArtifactStore,
    CandidateRegistrySnapshot,
    ExtractionMethodRegistrySnapshot,
    ExtractionQualityPolicySnapshot,
    QualityBoundExtractionCorpusSnapshot,
    ExperimentPlan,
    tuple[PositionalSentimentFixture, PositionalSentimentFixture],
]:
    candidate = candidate_registry()
    methods = method_registry()
    policy = quality_policy()
    frozen_corpus = corpus or quality_corpus()
    quality_assessments = assessments or quality_snapshots()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate, frozen_corpus, fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    persist_quality_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=frozen_corpus,
        policy=policy,
        sources=source_snapshots(),
        extractions=extraction_snapshots(),
        contents=content_snapshots(),
        assessments=quality_assessments,
        evaluated_at="2026-08-03T00:30:30Z",
    )
    return (
        artifact_store,
        candidate,
        methods,
        policy,
        frozen_corpus,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    corpus: QualityBoundExtractionCorpusSnapshot | None = None,
    assessments: tuple[ExtractionQualityAssessmentSnapshot, ...] | None = None,
    runtime_registry: AnalyzerRegistry | None = None,
    run_id: str = "quality-run-001",
):
    (
        artifact_store,
        candidate,
        methods,
        policy,
        frozen_corpus,
        plan,
        fixture_analyzers,
    ) = prepare_store(
        tmp_path,
        store=store,
        corpus=corpus,
        assessments=assessments,
    )
    runner = QualityGatedExtractionExperimentRunner(
        analyzer_registry=(
            runtime_registry or analyzer_registry(*fixture_analyzers)
        ),
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate,
        method_registry=methods,
        quality_policy=policy,
        corpus=frozen_corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        quality_evaluated_at="2026-08-03T00:30:30Z",
    )
    return receipt, artifact_store


def test_clean_quality_evidence_executes_and_validates_schemas(
    tmp_path: Path,
) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is QualityGatedRunnerStatus.VERIFIED
    assert receipt.outcome is QualityDecisionOutcome.EXECUTE
    assert receipt.eligible_extraction_receipt is not None
    assert receipt.verified_checks == QUALITY_GATED_VERIFIED_CHECKS

    validate_schema(POLICY_SCHEMA, load_document(QUALITY_POLICY_PATH))
    for path in QUALITY_PATHS:
        validate_schema(ASSESSMENT_SCHEMA, load_document(path))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    decision = store.get(
        receipt.quality_decision_ref.artifact_id,
        expected_hash=receipt.quality_decision_ref.artifact_hash,
    )
    validate_schema(
        DECISION_SCHEMA,
        cast(dict[str, Any], json.loads(decision.text)),
    )
    final = store.get(
        receipt.final_manifest_ref.artifact_id,
        expected_hash=receipt.final_manifest_ref.artifact_hash,
    )
    final_document = cast(dict[str, Any], json.loads(final.text))
    validate_schema(FINAL_SCHEMA, final_document)
    assert final_document["outcome"] == "execute"
    assert "aggregate_score" not in final_document
    assert "overall_status" not in final_document


def test_quality_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.quality_assessment_refs == second.quality_assessment_refs
    assert first.quality_decision_ref == second.quality_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


def test_uncertainty_and_manual_abstention_prevent_analyzer_execution(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["quality_status"] = "partial"
        document["issues"] = ["review uncertainty remains unresolved"]
        document["reviewer_observations"][0]["finding"] = "uncertain"
        document["reviewer_observations"][0]["notes"] = (
            "The reviewer could not independently resolve one source boundary."
        )
        document["uncertainties"] = [
            {
                "uncertainty_id": "uncertainty.synthetic.boundary",
                "description": "One source boundary remains uncertain.",
                "evidence_refs": [
                    document["extraction_artifact_ref"]["artifact_id"]
                ],
            }
        ]
        document["abstention"] = {
            "triggered": True,
            "reasons": ["reviewer-uncertainty"],
        }

    corpus, assessments = rebuild_quality_case(
        index=1,
        mutate=mutate,
        corpus_version="0.3.1-test-abstain",
    )
    receipt, store = execute(
        tmp_path,
        corpus=corpus,
        assessments=assessments,
        run_id="quality-run-abstain",
    )

    assert receipt.outcome is QualityDecisionOutcome.ABSTAIN
    assert receipt.eligible_extraction_receipt is None
    assert receipt.final_manifest_ref.artifact_id == (
        "quality-run-abstain:quality-abstention"
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get("quality-run-abstain:experiment-completion")
    with pytest.raises(ArtifactNotFoundError):
        store.get("quality-run-abstain:eligible-extraction-completion")


def test_failed_quality_requires_explicit_abstention_reason() -> None:
    document = load_document(QUALITY_PATHS[0])
    document["assessment_id"] += ".failed"
    document["artifact_id"] = f"extraction-quality:{document['assessment_id']}"
    document["quality_status"] = "failed"
    document["issues"] = ["synthetic extraction failure"]
    document["automated_checks"][0]["outcome"] = "failed"
    document["abstention"] = {
        "triggered": True,
        "reasons": ["quality-status:failed"],
    }

    with pytest.raises(
        ExtractionQualityEvidenceError,
        match="extraction-quality-failed",
    ):
        ExtractionQualityAssessmentSnapshot.from_document(document)


def test_clean_status_rejects_failed_automated_check() -> None:
    document = load_document(QUALITY_PATHS[0])
    document["automated_checks"][0]["outcome"] = (
        AutomatedCheckOutcome.FAILED.value
    )

    with pytest.raises(
        ExtractionQualityEvidenceError,
        match="clean quality",
    ):
        ExtractionQualityAssessmentSnapshot.from_document(document)


def test_policy_reviewer_minimum_fails_before_manifest_write(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["reviewer_observations"] = []

    corpus, assessments = rebuild_quality_case(
        index=0,
        mutate=mutate,
        corpus_version="0.3.1-test-reviewer",
    )
    candidate = candidate_registry()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate, corpus, fixture_analyzers)
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(
        ExtractionQualityEvidenceError,
        match="reviewer observation minimum",
    ):
        persist_quality_bound_corpus(
            store,
            plan=plan,
            corpus=corpus,
            policy=quality_policy(),
            sources=source_snapshots(),
            extractions=extraction_snapshots(),
            contents=content_snapshots(),
            assessments=assessments,
            evaluated_at="2026-08-03T00:30:30Z",
        )
    with pytest.raises(ArtifactNotFoundError):
        store.get(corpus.reference().artifact_id)


def test_missing_quality_artifact_fails_before_decision(
    tmp_path: Path,
) -> None:
    (
        store,
        candidate,
        methods,
        policy,
        corpus,
        plan,
        fixture_analyzers,
    ) = prepare_store(tmp_path)
    failing_store = AssessmentReadFailsStore(
        store.root,
        corpus.quality_entries[1].quality_assessment_ref.artifact_id,
    )
    runner = QualityGatedExtractionExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing_store,
    )

    with pytest.raises(QualityGatedExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate,
            method_registry=methods,
            quality_policy=policy,
            corpus=corpus,
            environment=environment(),
            windows=windows(),
            experiment_run_id="quality-run-missing",
            quality_evaluated_at="2026-08-03T00:30:30Z",
        )

    assert caught.value.stage is QualityGatedRunnerStage.QUALITY_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            "experiment.synthetic-quality-gated:0.1.0:"
            "extraction-quality-decision"
        )


def test_later_execution_failure_preserves_quality_decision_and_receipt(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(QualityGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=runtime_registry,
        )

    assert caught.value.stage is QualityGatedRunnerStage.EXPERIMENT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    store.get(
        "experiment.synthetic-quality-gated:0.1.0:"
        "extraction-quality-decision"
    )
    store.get("quality-run-001:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get("quality-run-001:quality-gated-completion")


def test_final_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(QualityGatedExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is QualityGatedRunnerStage.FINAL_PERSISTENCE
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get("quality-run-001:quality-gated-completion")


def test_stored_quality_evidence_reconstructs_exact_assessments(
    tmp_path: Path,
) -> None:
    store, _, _, policy, corpus, _, _ = prepare_store(tmp_path)
    loaded = load_quality_evidence(store, corpus=corpus, policy=policy)

    assert loaded.assessments == quality_snapshots()
    assert tuple(
        item.quality_status for item in loaded.assessments
    ) == (
        ExtractionQualityStatus.CLEAN,
        ExtractionQualityStatus.CLEAN,
        ExtractionQualityStatus.CLEAN,
    )
