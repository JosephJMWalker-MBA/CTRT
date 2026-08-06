"""Public boundary for preregistered candidate-to-human-reference evaluation.

The result lifecycle lives in a private implementation module. This public boundary
first proves that the in-memory synthesis receipt names exactly the collections bound
by the stored synthesis plan and receipt manifest. That prevents a caller from
removing fixture-marked collection objects before the production fixture gate runs.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from ctrt import _candidate_reference_evaluation_lifecycle as _lifecycle
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.human_reference_synthesis import (
    VerifiedSynthesisReceipt,
    find_collection_store,
    is_test_fixture_collection,
)
from ctrt.vader_adapter import VaderSentimentAdapter

EVALUATION_NON_CLAIMS = _lifecycle.EVALUATION_NON_CLAIMS
EVALUATION_RECORD_TYPE = _lifecycle.EVALUATION_RECORD_TYPE
EVALUATION_VERSION = _lifecycle.EVALUATION_VERSION
FIXTURE_NON_CLAIM = _lifecycle.FIXTURE_NON_CLAIM
CandidateEvaluationEligibility = _lifecycle.CandidateEvaluationEligibility
CandidateReferenceEvaluationCompletion = (
    _lifecycle.CandidateReferenceEvaluationCompletion
)
CandidateReferenceEvaluationError = _lifecycle.CandidateReferenceEvaluationError
CandidateReferenceEvaluationPlan = _lifecycle.CandidateReferenceEvaluationPlan
CandidateReferenceEvaluationRequest = _lifecycle.CandidateReferenceEvaluationRequest
CandidateReferenceItemEvaluation = _lifecycle.CandidateReferenceItemEvaluation
DirectionalContingency = _lifecycle.DirectionalContingency
EvaluationLifecycleSummary = _lifecycle.EvaluationLifecycleSummary
ItemEvaluationStatus = _lifecycle.ItemEvaluationStatus
PreservedCandidateOutput = _lifecycle.PreservedCandidateOutput
VerifiedCandidateReferenceEvaluation = (
    _lifecycle.VerifiedCandidateReferenceEvaluation
)
render_candidate_reference_evaluation_markdown = (
    _lifecycle.render_candidate_reference_evaluation_markdown
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CandidateReferenceEvaluationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CandidateReferenceEvaluationError(f"{field_name} keys must be strings")
    return value


def _verify_collection_population(
    *,
    request: CandidateReferenceEvaluationRequest,
    synthesis: VerifiedSynthesisReceipt,
    require_fixtures: bool,
) -> None:
    """Bind in-memory included collections to the stored synthesis manifest."""

    store = FileSystemArtifactStore(synthesis.artifact_directory)
    plan_artifact = store.get(
        synthesis.plan_ref.artifact_id,
        expected_hash=synthesis.plan_ref.artifact_hash,
    )
    stored_plan = _mapping(json.loads(plan_artifact.text), "stored synthesis plan")
    stored_annotators = stored_plan.get("annotator_ids")
    stored_completion_refs = stored_plan.get("completion_refs")
    if not isinstance(stored_annotators, list) or any(
        not isinstance(item, str) for item in stored_annotators
    ):
        raise CandidateReferenceEvaluationError(
            "stored synthesis plan has invalid annotator identities"
        )
    if not isinstance(stored_completion_refs, list):
        raise CandidateReferenceEvaluationError(
            "stored synthesis plan has invalid completion references"
        )

    manifest_artifact = store.get(
        synthesis.completion.receipt_manifest_ref.artifact_id,
        expected_hash=synthesis.completion.receipt_manifest_ref.artifact_hash,
    )
    manifest = _mapping(json.loads(manifest_artifact.text), "stored receipt manifest")
    manifest_annotators = manifest.get("ordered_annotator_ids")
    manifest_refs = manifest.get("completion_refs")
    if not isinstance(manifest_annotators, list) or any(
        not isinstance(item, str) for item in manifest_annotators
    ):
        raise CandidateReferenceEvaluationError(
            "stored receipt manifest has invalid annotator identities"
        )
    if not isinstance(manifest_refs, list):
        raise CandidateReferenceEvaluationError(
            "stored receipt manifest has invalid completion references"
        )

    included_annotators = tuple(item.annotator_id for item in synthesis.included)
    expected_annotators = synthesis.plan.annotator_ids
    if (
        tuple(stored_annotators) != expected_annotators
        or tuple(manifest_annotators) != expected_annotators
        or included_annotators != expected_annotators
    ):
        raise CandidateReferenceEvaluationError(
            "included collection identities differ from the stored synthesis plan"
        )

    included_refs = tuple(item.completion_ref for item in synthesis.included)
    if included_refs != synthesis.plan.completion_refs:
        raise CandidateReferenceEvaluationError(
            "included collection references differ from the stored synthesis plan"
        )
    if len(stored_completion_refs) != len(included_refs) or len(manifest_refs) != len(
        included_refs
    ):
        raise CandidateReferenceEvaluationError(
            "included collection population differs from stored synthesis evidence"
        )

    for plan_ref, manifest_ref, included in zip(
        stored_completion_refs,
        manifest_refs,
        synthesis.included,
        strict=True,
    ):
        plan_document = _mapping(plan_ref, "stored plan completion reference")
        manifest_document = _mapping(
            manifest_ref,
            "stored manifest completion reference",
        )
        expected = {
            "artifact_id": included.completion_ref.artifact_id,
            "artifact_hash": included.completion_ref.artifact_hash,
        }
        if (
            plan_document.get("artifact_id") != expected["artifact_id"]
            or plan_document.get("artifact_hash") != expected["artifact_hash"]
            or manifest_document.get("annotator_id") != included.annotator_id
            or manifest_document.get("assignment_id") != included.assignment_id
            or manifest_document.get("artifact_id") != expected["artifact_id"]
            or manifest_document.get("artifact_hash") != expected["artifact_hash"]
        ):
            raise CandidateReferenceEvaluationError(
                "included collection differs from stored synthesis evidence"
            )

        collection_store = find_collection_store(
            request.human_workspace,
            included.completion_ref.artifact_id,
        )
        collection_store.get(
            included.completion_ref.artifact_id,
            expected_hash=included.completion_ref.artifact_hash,
        )
        marked = is_test_fixture_collection(
            collection_store,
            assignment_id=included.assignment_id,
        )
        if require_fixtures and not marked:
            raise CandidateReferenceEvaluationError(
                "the test-only evaluation entry point requires every included "
                "collection to be explicitly marked as a synthetic fixture"
            )
        if not require_fixtures and marked:
            raise CandidateReferenceEvaluationError(
                f"collection {included.assignment_id!r} is marked as a synthetic "
                "test fixture and may not enter a production evaluation"
            )


def run_candidate_reference_evaluation(
    request: CandidateReferenceEvaluationRequest,
    *,
    synthesis: VerifiedSynthesisReceipt,
) -> VerifiedCandidateReferenceEvaluation:
    """Run production evaluation only after exact collection binding verification."""

    _verify_collection_population(
        request=request,
        synthesis=synthesis,
        require_fixtures=False,
    )
    return _lifecycle.run_candidate_reference_evaluation(
        request,
        synthesis=synthesis,
    )


def run_candidate_reference_evaluation_with_test_fixtures(
    request: CandidateReferenceEvaluationRequest,
    *,
    synthesis: VerifiedSynthesisReceipt,
    adapter: VaderSentimentAdapter,
) -> VerifiedCandidateReferenceEvaluation:
    """Run test-only evaluation after exact fixture population verification."""

    _verify_collection_population(
        request=request,
        synthesis=synthesis,
        require_fixtures=True,
    )
    return _lifecycle.run_candidate_reference_evaluation_with_test_fixtures(
        request,
        synthesis=synthesis,
        adapter=adapter,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate the CLI, whose production synthesis already rejects fixtures."""

    return _lifecycle.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
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
]
