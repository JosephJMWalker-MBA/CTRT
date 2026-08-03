from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from ctrt.adjudicated_extraction_runner import (
    ADJUDICATED_EXTRACTION_VERIFIED_CHECKS,
    AdjudicatedExtractionExperimentError,
    AdjudicatedExtractionExperimentRunner,
    AdjudicatedExtractionRunnerStage,
    AdjudicatedExtractionRunnerStatus,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
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
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import (
    ExtractionQualityAssessmentSnapshot,
    ExtractionQualityPolicySnapshot,
)
from ctrt.extraction_review_adjudication import (
    AdjudicationStatus,
    ReviewAdjudicationError,
    ReviewAdjudicationPolicySnapshot,
    ReviewAdjudicationSnapshot,
    ReviewBoundExtractionCorpusSnapshot,
    ReviewDecisionOutcome,
    ReviewerRegistrySnapshot,
    load_review_adjudication_evidence,
    persist_review_bound_corpus,
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
REVIEWER_REGISTRY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-extraction-reviewer-registry.v0.1.0.json"
)
REVIEW_POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-extraction-review-adjudication-policy.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.4.0.json"
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
REVIEW_PATHS = tuple(
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "review"
    / f"review-content-{index:03d}.json"
    for index in range(1, 4)
)
REVIEWER_SCHEMA = ROOT / "schemas" / "reviewer-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "review-adjudication-policy.schema.json"
REVIEW_SCHEMA = ROOT / "schemas" / "extraction-review-adjudication.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "review-bound-extraction-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "review-adjudication-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "review-adjudicated-extraction-final.schema.json"


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
            raise RuntimeError("synthetic review-adjudicated execution failure")
        return self.base.analyze(content)


class AdjudicationReadFailsStore(FileSystemArtifactStore):
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
            raise ArtifactIntegrityError("synthetic adjudication read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":review-adjudicated-completion",
                ":review-adjudication-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic adjudicated final failure")
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


def reviewer_registry() -> ReviewerRegistrySnapshot:
    return ReviewerRegistrySnapshot.from_document(
        load_document(REVIEWER_REGISTRY_PATH)
    )


def review_policy() -> ReviewAdjudicationPolicySnapshot:
    return ReviewAdjudicationPolicySnapshot.from_document(
        load_document(REVIEW_POLICY_PATH)
    )


def review_corpus(
    document: dict[str, Any] | None = None,
) -> ReviewBoundExtractionCorpusSnapshot:
    return ReviewBoundExtractionCorpusSnapshot.from_document(
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


def review_snapshots() -> tuple[ReviewAdjudicationSnapshot, ...]:
    return tuple(
        ReviewAdjudicationSnapshot.from_document(load_document(path))
        for path in REVIEW_PATHS
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
    corpus: ReviewBoundExtractionCorpusSnapshot,
    loaded: tuple[PositionalSentimentFixture, PositionalSentimentFixture],
) -> ExperimentPlan:
    first, last = loaded
    return ExperimentPlan(
        experiment_id="experiment.synthetic-review-adjudicated",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question=(
            "Can contradictory extraction reviews be preserved without voting?"
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
            "Abstain before analysis when review disagreement is unresolved.",
        ),
        created_at="2026-08-03T00:52:00Z",
    )


def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-review-adjudicated",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=canonical_sha256({"dependencies": []}),
        runtime_configuration_hash=canonical_sha256(
            {"mode": "synthetic-review-adjudicated"}
        ),
        hardware_profile="CPU-only synthetic execution",
    )


def windows() -> tuple[ExtractionExecutionWindow, ...]:
    return (
        ExtractionExecutionWindow(
            content_id="content-001",
            started_at="2026-08-03T00:53:00Z",
            completed_at="2026-08-03T00:53:01Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-002",
            started_at="2026-08-03T00:53:02Z",
            completed_at="2026-08-03T00:53:03Z",
        ),
        ExtractionExecutionWindow(
            content_id="content-003",
            started_at="2026-08-03T00:53:04Z",
            completed_at="2026-08-03T00:53:05Z",
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


def stored_ref_document(reference: StoredArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def rebuild_review_case(
    *,
    index: int,
    mutate: Any,
    corpus_version: str,
) -> tuple[
    ReviewBoundExtractionCorpusSnapshot,
    tuple[ReviewAdjudicationSnapshot, ...],
]:
    documents = [load_document(path) for path in REVIEW_PATHS]
    changed = deepcopy(documents[index])
    mutate(changed)
    changed["adjudication_id"] = (
        f"{changed['adjudication_id']}.{corpus_version}"
    )
    changed["artifact_id"] = (
        f"review-adjudication:{changed['adjudication_id']}"
    )
    documents[index] = changed
    adjudications = tuple(
        ReviewAdjudicationSnapshot.from_document(document)
        for document in documents
    )

    corpus_document = load_document(CORPUS_PATH)
    corpus_document["corpus_version"] = corpus_version
    corpus_document["created_at"] = "2026-08-03T00:54:00Z"
    corpus_document["contents"][index]["review_adjudication_ref"] = (
        stored_ref_document(adjudications[index].reference())
    )
    return review_corpus(corpus_document), adjudications


def prepare_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    corpus: ReviewBoundExtractionCorpusSnapshot | None = None,
    adjudications: tuple[ReviewAdjudicationSnapshot, ...] | None = None,
) -> tuple[
    FileSystemArtifactStore,
    CandidateRegistrySnapshot,
    ExtractionMethodRegistrySnapshot,
    ExtractionQualityPolicySnapshot,
    ReviewerRegistrySnapshot,
    ReviewAdjudicationPolicySnapshot,
    ReviewBoundExtractionCorpusSnapshot,
    ExperimentPlan,
    tuple[PositionalSentimentFixture, PositionalSentimentFixture],
]:
    candidate = candidate_registry()
    methods = method_registry()
    quality = quality_policy()
    reviewers = reviewer_registry()
    review_rules = review_policy()
    frozen_corpus = corpus or review_corpus()
    review_records = adjudications or review_snapshots()
    fixture_analyzers = analyzers()
    plan = experiment_plan(candidate, frozen_corpus, fixture_analyzers)
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    persist_review_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=frozen_corpus,
        quality_policy=quality,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        sources=source_snapshots(),
        extractions=extraction_snapshots(),
        contents=content_snapshots(),
        assessments=quality_snapshots(),
        adjudications=review_records,
        evaluated_at="2026-08-03T00:52:30Z",
    )
    return (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        frozen_corpus,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    corpus: ReviewBoundExtractionCorpusSnapshot | None = None,
    adjudications: tuple[ReviewAdjudicationSnapshot, ...] | None = None,
    runtime_registry: AnalyzerRegistry | None = None,
    run_id: str = "review-run-001",
):
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        frozen_corpus,
        plan,
        fixture_analyzers,
    ) = prepare_store(
        tmp_path,
        store=store,
        corpus=corpus,
        adjudications=adjudications,
    )
    runner = AdjudicatedExtractionExperimentRunner(
        analyzer_registry=(
            runtime_registry or analyzer_registry(*fixture_analyzers)
        ),
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate,
        method_registry=methods,
        quality_policy=quality,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        corpus=frozen_corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        quality_evaluated_at="2026-08-03T00:52:20Z",
        review_evaluated_at="2026-08-03T00:52:30Z",
    )
    return receipt, artifact_store


def test_clean_review_evidence_executes_and_validates_schemas(
    tmp_path: Path,
) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is AdjudicatedExtractionRunnerStatus.VERIFIED
    assert receipt.review_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.quality_gated_receipt is not None
    assert receipt.verified_checks == ADJUDICATED_EXTRACTION_VERIFIED_CHECKS

    validate_schema(REVIEWER_SCHEMA, load_document(REVIEWER_REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(REVIEW_POLICY_PATH))
    for path in REVIEW_PATHS:
        validate_schema(REVIEW_SCHEMA, load_document(path))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    decision = store.get(
        receipt.review_decision_ref.artifact_id,
        expected_hash=receipt.review_decision_ref.artifact_hash,
    )
    decision_document = cast(dict[str, Any], json.loads(decision.text))
    validate_schema(DECISION_SCHEMA, decision_document)
    assert "vote_count" not in decision_document
    assert "consensus_score" not in decision_document

    final = store.get(
        receipt.final_manifest_ref.artifact_id,
        expected_hash=receipt.final_manifest_ref.artifact_hash,
    )
    final_document = cast(dict[str, Any], json.loads(final.text))
    validate_schema(FINAL_SCHEMA, final_document)
    assert final_document["review_outcome"] == "execute"
    assert final_document["terminal_outcome"] == "execute"
    assert "aggregate_score" not in final_document


def test_review_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.review_adjudication_refs == second.review_adjudication_refs
    assert first.review_decision_ref == second.review_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


def test_unresolved_conflict_abstains_before_analyzer_execution(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["observations"][1]["finding"] = "issue"
        document["observations"][1]["notes"] = (
            "The secondary reviewer identifies an unresolved boundary issue."
        )
        document["conflicts"] = [
            {
                "conflict_id": "conflict.synthetic.boundary",
                "kind": "contradictory_findings",
                "observation_ids": [
                    document["observations"][0]["observation_id"],
                    document["observations"][1]["observation_id"],
                ],
                "description": "Reviewers disagree about text fidelity.",
            }
        ]
        document["adjudication_status"] = "unresolved"
        document["unresolved_conflict_ids"] = [
            "conflict.synthetic.boundary"
        ]
        document["abstention"] = {
            "triggered": True,
            "reasons": ["review-status:unresolved"],
        }

    corpus, adjudications = rebuild_review_case(
        index=1,
        mutate=mutate,
        corpus_version="0.4.1-test-unresolved",
    )
    receipt, store = execute(
        tmp_path,
        corpus=corpus,
        adjudications=adjudications,
        run_id="review-run-unresolved",
    )

    assert receipt.review_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.quality_gated_receipt is None
    assert receipt.final_manifest_ref.artifact_id == (
        "review-run-unresolved:review-adjudication-abstention"
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get("review-run-unresolved:quality-gated-completion")
    with pytest.raises(ArtifactNotFoundError):
        store.get("review-run-unresolved:experiment-completion")


def test_majority_count_cannot_override_unresolved_conflict(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["observations"][1]["finding"] = "issue"
        document["observations"].append(
            {
                "observation_id": "review-observation:extra-confirmation",
                "reviewer_id": "reviewer.synthetic.primary",
                "reviewer_role": "primary_reviewer",
                "review_question_id": "canonical-text-fidelity",
                "finding": "confirmed",
                "notes": "A second confirming observation does not resolve dissent.",
                "evidence_refs": [
                    document["quality_assessment_ref"]["artifact_id"]
                ],
                "observed_at": "2026-08-03T00:55:00Z",
            }
        )
        document["conflicts"] = [
            {
                "conflict_id": "conflict.synthetic.majority-forbidden",
                "kind": "contradictory_findings",
                "observation_ids": [
                    item["observation_id"] for item in document["observations"]
                ],
                "description": "Two confirmations do not erase one issue finding.",
            }
        ]
        document["adjudication_status"] = "pending"
        document["unresolved_conflict_ids"] = [
            "conflict.synthetic.majority-forbidden"
        ]
        document["abstention"] = {
            "triggered": True,
            "reasons": ["review-status:pending"],
        }

    corpus, adjudications = rebuild_review_case(
        index=0,
        mutate=mutate,
        corpus_version="0.4.1-test-majority",
    )
    receipt, _ = execute(
        tmp_path,
        corpus=corpus,
        adjudications=adjudications,
        run_id="review-run-majority",
    )

    assert receipt.review_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.quality_gated_receipt is None


def test_resolved_conflict_preserves_dissent_and_executes(
    tmp_path: Path,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        secondary_id = document["observations"][1]["observation_id"]
        document["observations"][1]["finding"] = "issue"
        document["observations"][1]["notes"] = (
            "The secondary reviewer retains a boundary concern."
        )
        document["conflicts"] = [
            {
                "conflict_id": "conflict.synthetic.resolved",
                "kind": "contradictory_findings",
                "observation_ids": [
                    document["observations"][0]["observation_id"],
                    secondary_id,
                ],
                "description": "Reviewers disagree about one boundary.",
            }
        ]
        document["adjudication_status"] = "resolved"
        document["adjudicator_id"] = "reviewer.synthetic.adjudicator"
        document["resolution_notes"] = (
            "The exact mapping supports execution while dissent remains visible."
        )
        document["dissent"] = [
            {
                "dissent_id": "dissent.synthetic.secondary",
                "reviewer_id": "reviewer.synthetic.secondary",
                "observation_ids": [secondary_id],
                "position": "Boundary concern remains material.",
                "rationale": "The reviewer interprets the source edge differently.",
                "preserved": True,
            }
        ]
        document["unresolved_conflict_ids"] = []
        document["abstention"] = {"triggered": False, "reasons": []}

    corpus, adjudications = rebuild_review_case(
        index=2,
        mutate=mutate,
        corpus_version="0.4.1-test-resolved",
    )
    receipt, store = execute(
        tmp_path,
        corpus=corpus,
        adjudications=adjudications,
        run_id="review-run-resolved",
    )

    assert receipt.review_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    decision = store.get(
        receipt.review_decision_ref.artifact_id,
        expected_hash=receipt.review_decision_ref.artifact_hash,
    )
    document = cast(dict[str, Any], json.loads(decision.text))
    assert document["adjudications"][2]["adjudication_status"] == "resolved"
    assert document["adjudications"][2]["dissent_ids"] == [
        "dissent.synthetic.secondary"
    ]


def test_contradictory_observations_require_conflict_record() -> None:
    document = load_document(REVIEW_PATHS[0])
    document["adjudication_id"] += ".missing-conflict"
    document["artifact_id"] = f"review-adjudication:{document['adjudication_id']}"
    document["observations"][1]["finding"] = "issue"

    adjudication = ReviewAdjudicationSnapshot.from_document(document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document["corpus_version"] = "0.4.1-test-missing-conflict"
    corpus_document["contents"][0]["review_adjudication_ref"] = (
        stored_ref_document(adjudication.reference())
    )
    corpus = review_corpus(corpus_document)
    plan = experiment_plan(candidate_registry(), corpus, analyzers())

    with pytest.raises(ReviewAdjudicationError, match="lacks conflict record"):
        from ctrt.extraction_review_adjudication import (
            validate_review_adjudication_evidence,
        )

        validate_review_adjudication_evidence(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            review_policy=review_policy(),
            adjudications=(adjudication, *review_snapshots()[1:]),
            evaluated_at="2026-08-03T00:52:30Z",
        )


def test_resolved_conflict_requires_authorized_adjudicator() -> None:
    document = load_document(REVIEW_PATHS[0])
    first_id = document["observations"][0]["observation_id"]
    second_id = document["observations"][1]["observation_id"]
    document["observations"][1]["finding"] = "issue"
    document["conflicts"] = [
        {
            "conflict_id": "conflict.synthetic.unauthorized",
            "kind": "contradictory_findings",
            "observation_ids": [first_id, second_id],
            "description": "Synthetic conflict.",
        }
    ]
    document["adjudication_status"] = "resolved"
    document["adjudicator_id"] = "reviewer.synthetic.primary"
    document["resolution_notes"] = "An unauthorized reviewer attempted resolution."

    corpus, adjudications = rebuild_review_case(
        index=0,
        mutate=lambda target: target.update(document),
        corpus_version="0.4.1-test-adjudicator",
    )
    plan = experiment_plan(candidate_registry(), corpus, analyzers())

    with pytest.raises(ReviewAdjudicationError, match="adjudicator lacks"):
        from ctrt.extraction_review_adjudication import (
            validate_review_adjudication_evidence,
        )

        validate_review_adjudication_evidence(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            review_policy=review_policy(),
            adjudications=adjudications,
            evaluated_at="2026-08-03T00:52:30Z",
        )


def test_vote_count_field_is_rejected_by_schema_and_parser() -> None:
    document = load_document(REVIEW_PATHS[0])
    document["vote_count"] = {"confirmed": 2, "issue": 1}

    with pytest.raises(ValidationError):
        validate_schema(REVIEW_SCHEMA, document)
    with pytest.raises(ReviewAdjudicationError, match="unsupported fields"):
        ReviewAdjudicationSnapshot.from_document(document)


def test_missing_review_artifact_fails_before_decision(tmp_path: Path) -> None:
    (
        store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        corpus,
        plan,
        fixture_analyzers,
    ) = prepare_store(tmp_path)
    failing_store = AdjudicationReadFailsStore(
        store.root,
        corpus.review_entries[1].review_adjudication_ref.artifact_id,
    )
    runner = AdjudicatedExtractionExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing_store,
    )

    with pytest.raises(AdjudicatedExtractionExperimentError) as caught:
        runner.run(
            plan=plan,
            candidate_registry=candidate,
            method_registry=methods,
            quality_policy=quality,
            reviewer_registry=reviewers,
            review_policy=review_rules,
            corpus=corpus,
            environment=environment(),
            windows=windows(),
            experiment_run_id="review-run-missing",
            quality_evaluated_at="2026-08-03T00:52:20Z",
            review_evaluated_at="2026-08-03T00:52:30Z",
        )

    assert caught.value.stage is AdjudicatedExtractionRunnerStage.EVIDENCE_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("review-run-missing:review-adjudication-decision")


def test_later_execution_failure_preserves_decision_and_prior_receipt(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(AdjudicatedExtractionExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=runtime_registry,
        )

    assert caught.value.stage is AdjudicatedExtractionRunnerStage.QUALITY_GATE
    assert caught.value.completed_content_ids == ("content-001",)
    store.get("review-run-001:review-adjudication-decision")
    store.get("review-run-001:extraction-quality-decision")
    store.get("review-run-001:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get("review-run-001:review-adjudicated-completion")


def test_final_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(AdjudicatedExtractionExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is AdjudicatedExtractionRunnerStage.FINAL_PERSISTENCE
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get("review-run-001:review-adjudicated-completion")


def test_stored_review_evidence_reconstructs_exact_adjudications(
    tmp_path: Path,
) -> None:
    store, _, _, _, reviewers, rules, corpus, _, _ = prepare_store(tmp_path)
    loaded = load_review_adjudication_evidence(
        store,
        corpus=corpus,
        reviewer_registry=reviewers,
        review_policy=rules,
    )

    assert loaded.adjudications == review_snapshots()
    assert tuple(item.adjudication_status for item in loaded.adjudications) == (
        AdjudicationStatus.NOT_REQUIRED,
        AdjudicationStatus.NOT_REQUIRED,
        AdjudicationStatus.NOT_REQUIRED,
    )
