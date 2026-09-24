from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.candidate_reference_evaluation import (
    EVALUATION_NON_CLAIMS,
    EVALUATION_RECORD_TYPE,
    EVALUATION_VERSION,
    FIXTURE_NON_CLAIM,
    CandidateReferenceEvaluationError,
    CandidateReferenceEvaluationRequest,
    DirectionalContingency,
    ItemEvaluationStatus,
    VerifiedCandidateReferenceEvaluation,
    run_candidate_reference_evaluation,
    run_candidate_reference_evaluation_with_test_fixtures,
)
from ctrt.candidate_reference_evaluation_protocol import (
    CANDIDATE_BUCKETS,
    DEFAULT_REAL_CANDIDATE_REGISTRY,
)
from ctrt.contracts import ContentItem, ModelResult
from ctrt.human_reference_annotation import (
    open_assignment,
    persist_collection_inputs,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    AbstentionReason,
    ContextSufficiency,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    SupportingSpan,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
)
from ctrt.human_reference_synthesis import (
    DEFAULT_ANNOTATION_PROTOCOL,
    DEFAULT_CORPUS,
    SUFFICIENT_COVERAGE,
    VerifiedSynthesisReceipt,
    mark_test_fixture_collection,
    run_human_reference_synthesis,
)
from ctrt.serialization import serialize_artifact
from ctrt.vader_adapter import (
    PRESERVED_OUTPUT_KEYS,
    VADER_PINNED_VERSION,
    VaderSentimentAdapter,
)


class _DeterministicScorer:
    """Fixture scorer emitting three valid VADER-shaped directions."""

    def polarity_scores(self, text: str) -> Mapping[str, float]:
        bucket = sum(text.encode("utf-8")) % 3
        if bucket == 0:
            return {"neg": 0.8, "neu": 0.2, "pos": 0.0, "compound": -0.5}
        if bucket == 1:
            return {"neg": 0.1, "neu": 0.8, "pos": 0.1, "compound": 0.0}
        return {"neg": 0.0, "neu": 0.2, "pos": 0.8, "compound": 0.5}


class _InvalidScorer:
    """Fixture scorer that violates the pinned output contract."""

    def polarity_scores(self, text: str) -> Mapping[str, float]:
        del text
        return {"neg": 0.1, "neu": 0.8, "pos": 0.1}


class _OneAbstentionAdapter:
    """Fixture wrapper exercising abstention without changing the frozen corpus."""

    def __init__(self, base: VaderSentimentAdapter) -> None:
        self._base = base

    @property
    def package_version(self) -> str:
        return self._base.package_version

    @property
    def dimension_id(self) -> str:
        return self._base.dimension_id

    @property
    def dimension_version(self) -> str:
        return self._base.dimension_version

    @property
    def implementation_revision(self) -> str:
        return self._base.implementation_revision

    @property
    def execution_configuration(self) -> Mapping[str, object]:
        return self._base.execution_configuration

    @property
    def identity(self) -> Any:
        return self._base.identity

    def analyze(self, content: ContentItem) -> ModelResult:
        if content.content_id == "hr-001":
            content = replace(content, language="fr")
        return self._base.analyze(content)


def _adapter(scorer: object | None = None) -> VaderSentimentAdapter:
    return VaderSentimentAdapter(
        package_version=VADER_PINNED_VERSION,
        _scorer=scorer or _DeterministicScorer(),
    )


def _corpus() -> Any:
    return load_evaluation_corpus(
        cast(dict[str, Any], json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8")))
    )


def _protocol() -> Any:
    return load_annotation_protocol(
        cast(
            dict[str, Any],
            json.loads(DEFAULT_ANNOTATION_PROTOCOL.read_text(encoding="utf-8")),
        )
    )


def _fixture_collection(
    workspace: Path,
    *,
    annotator_id: str,
    label: ValenceLabel,
) -> str:
    session, store = open_assignment(
        workspace=workspace,
        annotator_id=annotator_id,
        created_at=datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
    )
    persist_collection_inputs(
        store,
        corpus=_corpus(),
        protocol=_protocol(),
        assignment=session.assignment,
    )
    mark_test_fixture_collection(store, assignment_id=session.assignment.assignment_id)

    for index, item_id in enumerate(session.assignment.item_ids):
        spans: tuple[SupportingSpan, ...] = ()
        if index == 0 and label is not ABSTENTION_LABEL:
            spans = (SupportingSpan(start=0, end=3),)
        session.record(
            item_id=item_id,
            valence_label=label,
            context_sufficiency=(
                ContextSufficiency.INSUFFICIENT
                if label is ABSTENTION_LABEL
                else ContextSufficiency.SUFFICIENT
            ),
            perceived_ambiguity=(
                PerceivedAmbiguity.HIGH
                if label is ABSTENTION_LABEL
                else PerceivedAmbiguity.SOME
            ),
            abstention_reason=(
                AbstentionReason.INSUFFICIENT_CONTEXT
                if label is ABSTENTION_LABEL
                else None
            ),
            self_reported_certainty=(
                None
                if label is ABSTENTION_LABEL
                else SelfReportedCertainty.MEDIUM
            ),
            rationale="Fixture rationale." if index == 0 else None,
            supporting_spans=spans,
            recorded_at=datetime(2026, 8, 6, 10, 15, tzinfo=UTC),
        )
    completion, _ = session.complete(
        completed_at=datetime(2026, 8, 6, 10, 45, tzinfo=UTC)
    )
    return completion.completion_id


def _three_fixtures(workspace: Path) -> list[str]:
    labels = (
        ValenceLabel.SOMEWHAT_FAVORABLE,
        ValenceLabel.NEITHER,
        ABSTENTION_LABEL,
    )
    return [
        _fixture_collection(
            workspace,
            annotator_id=f"rater-{index + 1:03d}",
            label=label,
        )
        for index, label in enumerate(labels)
    ]


def _synthesis(human_workspace: Path) -> VerifiedSynthesisReceipt:
    return run_human_reference_synthesis(
        workspace=human_workspace,
        completion_ids=_three_fixtures(human_workspace),
        allow_test_fixtures=True,
        created_at=datetime(2026, 8, 6, 11, 0, tzinfo=UTC),
    )


def _request(tmp_path: Path, human_workspace: Path) -> CandidateReferenceEvaluationRequest:
    return CandidateReferenceEvaluationRequest(
        workspace=tmp_path / "evaluation",
        human_workspace=human_workspace,
        run_token="fixture-run-0001",
        started_at=datetime(2026, 8, 6, 11, 30, tzinfo=UTC),
    )


def _evaluate(
    tmp_path: Path,
    *,
    adapter: VaderSentimentAdapter | Any | None = None,
) -> tuple[VerifiedSynthesisReceipt, VerifiedCandidateReferenceEvaluation]:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)
    receipt = run_candidate_reference_evaluation_with_test_fixtures(
        _request(tmp_path, human_workspace),
        synthesis=synthesis,
        adapter=cast(VaderSentimentAdapter, adapter or _adapter()),
    )
    return synthesis, receipt


def test_fixture_evaluation_executes_complete_frozen_corpus(tmp_path: Path) -> None:
    synthesis, receipt = _evaluate(tmp_path)

    assert receipt.evaluation_version == EVALUATION_VERSION
    assert receipt.plan.record_type == EVALUATION_RECORD_TYPE
    assert receipt.plan.item_ids == _corpus().item_ids
    assert len(receipt.items) == 48
    assert len(receipt.completion.candidate_result_refs) == 48
    assert len(receipt.completion.item_evaluation_refs) == 48
    assert receipt.plan.synthesis_completion_ref == synthesis.completion_ref
    assert receipt.completion.synthesis_completion_ref == synthesis.completion_ref
    assert receipt.completion.candidate_lifecycle_status == "eligible_for_evaluation"
    assert receipt.plan.synthetic_test_fixture is True
    assert receipt.completion.synthetic_test_fixture is True
    assert receipt.completion.non_claims == (*EVALUATION_NON_CLAIMS, FIXTURE_NON_CLAIM)


def test_every_item_preserves_candidate_and_human_evidence(tmp_path: Path) -> None:
    _, receipt = _evaluate(tmp_path)

    for item in receipt.items:
        assert set(item.original_human_distribution) == {
            label.value for label in ValenceLabel
        }
        assert len(item.original_human_distribution) == 6
        assert item.human_directional_distribution.neutral == 1
        assert item.human_directional_distribution.favorable == 1
        assert item.human_directional_distribution.unfavorable == 0
        assert item.human_directional_distribution.abstention == 1
        assert item.human_coverage_status == SUFFICIENT_COVERAGE
        assert item.evaluation_status is ItemEvaluationStatus.DESCRIBED
        assert item.candidate_bucket in CANDIDATE_BUCKETS
        assert item.correspondence is not None
        assert item.correspondence.directional_denominator == 2
        assert item.correspondence.human_abstention_count == 1
        assert item.correspondence.same_direction_count == (
            item.human_directional_distribution.count(item.candidate_bucket)
        )
        assert tuple(output.key for output in item.candidate_outputs) == (
            PRESERVED_OUTPUT_KEYS
        )
        assert tuple(item.candidate_raw_output) == PRESERVED_OUTPUT_KEYS
        assert not hasattr(item.correspondence, "accuracy")
        assert not hasattr(item.correspondence, "rate")


def test_contingency_is_response_counting_not_item_accuracy(tmp_path: Path) -> None:
    _, receipt = _evaluate(tmp_path)
    contingency = receipt.contingency

    assert isinstance(contingency, DirectionalContingency)
    assert contingency.directional_denominator == 48 * 2
    assert sum(contingency.cells.values()) == contingency.directional_denominator
    assert receipt.lifecycle.human_directional_responses_described == 48 * 2
    assert receipt.lifecycle.human_abstentions_preserved == 48
    assert receipt.lifecycle.items_with_described_correspondence == 48
    assert not hasattr(contingency, "accuracy")
    assert not hasattr(contingency, "rate")
    assert not hasattr(contingency, "score")


def test_fixture_report_is_visibly_non_empirical(tmp_path: Path) -> None:
    _, receipt = _evaluate(tmp_path)
    report = receipt.markdown

    assert "SYNTHETIC TEST FIXTURE — NOT HUMAN RESEARCH EVIDENCE" in report
    assert FIXTURE_NON_CLAIM in report
    assert "correspondence, not accuracy" in report
    assert "Candidate lifecycle: `eligible_for_evaluation`" in report
    assert "User-facing execution permitted: no" in report
    assert "No accuracy, precision, recall, F1" in report
    assert "does not create a candidate selection record" in report


def test_production_entry_point_refuses_fixture_collections(tmp_path: Path) -> None:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)

    # Prove the production fixture check runs *before* the optional candidate
    # dependency is loaded. The loader lives in the private lifecycle module, so
    # it must be patched there; patching the public module resolves nothing and
    # would leave this property unverified.
    import ctrt._candidate_reference_evaluation_lifecycle as lifecycle

    original = lifecycle.load_vader_sentiment_adapter
    loaded: list[bool] = []

    def fail_if_loaded() -> VaderSentimentAdapter:
        loaded.append(True)
        raise AssertionError("candidate dependency loaded before fixture rejection")

    lifecycle.load_vader_sentiment_adapter = fail_if_loaded
    try:
        with pytest.raises(
            CandidateReferenceEvaluationError,
            match="may not enter a production evaluation",
        ):
            run_candidate_reference_evaluation(
                _request(tmp_path, human_workspace),
                synthesis=synthesis,
            )
    finally:
        lifecycle.load_vader_sentiment_adapter = original
    assert loaded == [], "the candidate dependency must never be loaded"


def test_candidate_failure_remains_separate_from_human_reference(tmp_path: Path) -> None:
    _, receipt = _evaluate(tmp_path, adapter=_adapter(_InvalidScorer()))

    assert receipt.lifecycle.candidate_failures == 48
    assert receipt.lifecycle.candidate_successes == 0
    assert receipt.lifecycle.candidate_abstentions == 0
    assert receipt.lifecycle.items_with_sufficient_reference_coverage == 48
    assert receipt.lifecycle.items_with_described_correspondence == 0
    assert receipt.contingency.directional_denominator == 0
    assert all(
        item.evaluation_status is ItemEvaluationStatus.CANDIDATE_FAILED
        for item in receipt.items
    )
    assert all(item.correspondence is None for item in receipt.items)
    assert all(item.human_directional_distribution.total_responses == 3 for item in receipt.items)


def test_candidate_abstention_remains_separate_from_failure_and_coverage(
    tmp_path: Path,
) -> None:
    adapter = _OneAbstentionAdapter(_adapter())
    _, receipt = _evaluate(tmp_path, adapter=adapter)

    first = receipt.items[0]
    assert first.item_id == "hr-001"
    assert first.evaluation_status is ItemEvaluationStatus.CANDIDATE_ABSTAINED
    assert first.correspondence is None
    assert first.exclusion_reasons == ("out-of-domain",)
    assert first.human_coverage_status == SUFFICIENT_COVERAGE
    assert first.human_directional_distribution.total_responses == 3
    assert receipt.lifecycle.candidate_abstentions == 1
    assert receipt.lifecycle.candidate_failures == 0
    assert receipt.lifecycle.candidate_successes == 47
    assert receipt.lifecycle.items_with_sufficient_reference_coverage == 48
    assert receipt.lifecycle.items_with_described_correspondence == 47


def test_synthesis_receipt_object_drift_fails_before_candidate_execution(
    tmp_path: Path,
) -> None:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)
    first = synthesis.items[0]
    changed = replace(first, text=first.text + " altered")
    drifted = replace(synthesis, items=(changed, *synthesis.items[1:]))

    with pytest.raises(ArtifactIntegrityError, match="differs from the receipt"):
        run_candidate_reference_evaluation_with_test_fixtures(
            _request(tmp_path, human_workspace),
            synthesis=drifted,
            adapter=_adapter(),
        )


def test_stored_synthesis_tampering_fails_on_read(tmp_path: Path) -> None:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)
    reference = synthesis.completion.item_synthesis_refs[0]
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = synthesis.artifact_directory / "blobs" / "sha256" / digest
    blob.write_bytes(blob.read_bytes() + b"tamper")

    with pytest.raises(ArtifactIntegrityError):
        run_candidate_reference_evaluation_with_test_fixtures(
            _request(tmp_path, human_workspace),
            synthesis=synthesis,
            adapter=_adapter(),
        )


def test_registry_drift_fails_before_candidate_execution(tmp_path: Path) -> None:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)
    registry = cast(
        dict[str, Any],
        json.loads(DEFAULT_REAL_CANDIDATE_REGISTRY.read_text(encoding="utf-8")),
    )
    candidates = cast(list[dict[str, Any]], registry["candidates"])
    candidates[0]["status"] = "selected_for_domain"
    path = tmp_path / "changed-registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    request = replace(_request(tmp_path, human_workspace), real_registry_path=path)

    with pytest.raises(ValueError, match="candidate lifecycle status mismatch"):
        run_candidate_reference_evaluation_with_test_fixtures(
            request,
            synthesis=synthesis,
            adapter=_adapter(),
        )


def test_completion_manifest_and_referenced_artifacts_reverify(tmp_path: Path) -> None:
    _, receipt = _evaluate(tmp_path)
    store = FileSystemArtifactStore(receipt.artifact_directory)

    stored = store.get(
        receipt.completion_ref.artifact_id,
        expected_hash=receipt.completion_ref.artifact_hash,
    )
    expected = serialize_artifact(receipt.completion.completion_id, receipt.completion)
    assert stored.payload == expected.payload
    for reference in (
        receipt.plan_ref,
        receipt.completion.protocol_ref,
        receipt.completion.eligibility_ref,
        receipt.completion.contingency_ref,
        receipt.completion.lifecycle_ref,
        *receipt.completion.candidate_result_refs,
        *receipt.completion.item_evaluation_refs,
    ):
        assert store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).artifact_hash == reference.artifact_hash


def test_repeated_identical_fixture_run_is_idempotent(tmp_path: Path) -> None:
    human_workspace = tmp_path / "human"
    synthesis = _synthesis(human_workspace)
    request = _request(tmp_path, human_workspace)

    first = run_candidate_reference_evaluation_with_test_fixtures(
        request,
        synthesis=synthesis,
        adapter=_adapter(),
    )
    second = run_candidate_reference_evaluation_with_test_fixtures(
        request,
        synthesis=synthesis,
        adapter=_adapter(),
    )

    assert first.completion_ref == second.completion_ref
    assert first.plan_ref == second.plan_ref
    assert first.markdown == second.markdown


def test_public_surface_is_bounded_and_contains_no_selection_operation() -> None:
    import ctrt.candidate_reference_evaluation as module

    expected = {
        "EVALUATION_NON_CLAIMS",
        "EVALUATION_RECORD_TYPE",
        "EVALUATION_VERSION",
        "FIXTURE_NON_CLAIM",
        "CandidateEvaluationEligibility",
        "CandidateReferenceEvaluationCompletion",
        "CandidateReferenceEvaluationError",
        "CandidateReferenceEvaluationPlan",
        "CandidateReferenceEvaluationRequest",
        "CandidateReferenceItemEvaluation",
        "DirectionalContingency",
        "EvaluationLifecycleSummary",
        "ItemEvaluationStatus",
        "PreservedCandidateOutput",
        "VerifiedCandidateReferenceEvaluation",
        "main",
        "render_candidate_reference_evaluation_markdown",
        "run_candidate_reference_evaluation",
        "run_candidate_reference_evaluation_with_test_fixtures",
    }
    assert set(module.__all__) == expected
    assert not any("select" in name.lower() for name in module.__all__)
    assert not any("authorize_product" in name.lower() for name in module.__all__)
    assert not any("accuracy" in field.name for field in fields(DirectionalContingency))


def test_module_imports_no_browser_or_creator_surface() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "ctrt" / (
        "candidate_reference_evaluation.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)

    assert not any("creator_preflight" in name for name in imports)
    assert not any("content_understanding" in name for name in imports)
    assert not any("local_browser" in name for name in imports)
