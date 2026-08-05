from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    persist_experiment_bundle,
    verify_experiment_bundle,
)
from ctrt.candidate_eligibility import (
    CandidateEligibilityError,
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.contracts import ResultStatus
from ctrt.execution_session import ExecutionSessionStatus
from ctrt.experiments import InMemoryExperimentLedger
from ctrt.extraction_bound_runner import (
    ExtractionBoundExperimentError,
    ExtractionBoundExperimentRunner,
    ExtractionBoundRunnerStage,
    ExtractionBoundRunnerStatus,
)
from ctrt.extraction_manifest import (
    ExtractedContentSnapshot,
    ExtractionManifestError,
    load_extracted_corpus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.serialization import (
    CANONICALIZATION_VERSION,
    canonical_data,
    serialize_artifact,
)
from ctrt.workbench import WorkbenchReportStatus

workbench_fx = import_module("test_synthetic_workbench")
execution_fx = import_module("test_execution_session")
artifact_fx = import_module("test_artifact_store")
candidate_fx = import_module("test_candidate_eligibility")
experiment_fx = import_module("test_experiments")
extraction_fx = import_module("test_extraction_manifest_binding")
adjudication_fx = import_module(
    "test_adjudicated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)
closure_fx = import_module(
    "test_closure_checkpoint_gated_current_revocation_conflict_adjudicator_"
    "checkpoint_witness_conflict_adjudicator_credential_revocation_runner"
)

FORBIDDEN_AGGREGATE_FIELDS = {
    "aggregate_confidence",
    "aggregate_score",
    "confidence_score",
    "consequential_decision",
    "consequential_decision_support",
    "consequential_label",
    "content_label",
    "ctrt_score",
    "decision_support",
    "overall_confidence",
    "overall_ctrt_score",
    "overall_label",
    "overall_score",
    "overall_status",
    "production_ready",
    "scalar_tone_rating",
    "tone_rating",
    "tone_score",
    "validated_production_readiness",
}
FORBIDDEN_SCOPE_VALUES = {
    "consequential-decision-support",
    "production-ready",
    "validated-production-readiness",
}


def _assert_constitutional_output_surface(value: object) -> None:
    """Reject semantic collapse while permitting per-instrument measurements."""

    def visit(item: object, path: tuple[str, ...] = ()) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = key.strip().lower().replace("-", "_")
                assert normalized not in FORBIDDEN_AGGREGATE_FIELDS, (
                    f"forbidden constitutional field at {'.'.join((*path, key))}"
                )
                visit(nested, (*path, key))
            return
        if isinstance(item, list):
            for index, nested in enumerate(item):
                visit(nested, (*path, str(index)))
            return
        if isinstance(item, str):
            normalized_value = item.strip().lower().replace("_", "-")
            assert normalized_value not in FORBIDDEN_SCOPE_VALUES, (
                f"forbidden Phase 1A scope claim at {'.'.join(path)}"
            )

    visit(canonical_data(value))


def _blob_path(root: Path, artifact_hash: str) -> Path:
    return root / "blobs" / "sha256" / artifact_hash.removeprefix("sha256:")


def test_measurement_remains_separate_from_judgment_and_disagreement() -> None:
    bench, analyzer_ids = workbench_fx.workbench()
    run = bench.run_content_item(
        run_id="constitutional-disagreement",
        content=workbench_fx.content(
            "The launch was good, but the support was bad."
        ),
        analyzer_ids=analyzer_ids,
    )

    assert tuple(result.status for result in run.results) == (
        ResultStatus.SUCCESS,
        ResultStatus.SUCCESS,
    )
    assert tuple(
        result.normalized_scores[0].value for result in run.results
    ) == (1.0, -1.0)
    assert run.comparison.status is WorkbenchReportStatus.ABSTAINED
    assert run.comparison.disagreements[0].material is True
    assert run.comparison.score_combination_permitted is False
    _assert_constitutional_output_surface(run)


def test_verified_receipt_can_preserve_analytical_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = execution_fx.execute(tmp_path)

    assert receipt.status is ExecutionSessionStatus.VERIFIED
    assert receipt.workbench_status is WorkbenchReportStatus.ABSTAINED
    assert receipt.result_statuses == (
        ResultStatus.SUCCESS,
        ResultStatus.SUCCESS,
    )
    _assert_constitutional_output_surface(receipt)

    manifest = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.manifest_ref.artifact_id,
                expected_hash=receipt.manifest_ref.artifact_hash,
            ).text
        ),
    )
    _assert_constitutional_output_surface(manifest)
    for member in cast(list[dict[str, Any]], manifest["artifacts"]):
        reference = cast(dict[str, Any], member["artifact"])
        artifact = store.get(
            cast(str, reference["artifact_id"]),
            expected_hash=cast(str, reference["artifact_hash"]),
        )
        _assert_constitutional_output_surface(json.loads(artifact.text))


def test_append_only_identity_and_read_time_rehashing_are_non_replaceable(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "canonical-store")
    first = serialize_artifact("artifact.constitutional", {"value": 1})
    reference = store.append(first)

    assert reference.canonicalization_version == CANONICALIZATION_VERSION
    assert store.append(first) == reference
    with pytest.raises(ArtifactConflictError, match="append-only"):
        store.append(
            serialize_artifact("artifact.constitutional", {"value": 2})
        )

    _blob_path(store.root, first.artifact_hash).write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        store.get(first.artifact_id)


def test_complete_bundle_rehashes_every_required_member(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "bundle-store")
    stored = persist_experiment_bundle(store, artifact_fx._bundle())
    verify_experiment_bundle(store, stored)

    roles = tuple(item.role for item in stored.manifest.artifacts)
    assert roles == (
        "plan",
        "candidate-eligibility",
        "environment",
        "result:0",
        "result:1",
        "comparison",
        "run-record",
    )
    result_ref = next(
        item.artifact
        for item in stored.manifest.artifacts
        if item.role == "result:0"
    )
    _blob_path(store.root, result_ref.artifact_hash).write_bytes(
        b"tampered-constitutional-result"
    )
    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        verify_experiment_bundle(store, stored)


def test_exact_candidate_scope_authorizes_only_pinned_synthetic_fixtures() -> None:
    registry = candidate_fx.synthetic_snapshot()
    plan = candidate_fx.plan_for(registry)
    report = validate_candidate_eligibility(plan, registry)

    assert report.authorized_candidate_ids == (
        "fixture.first-signal",
        "fixture.last-signal",
    )
    assert report.authorized_analyzer_ids == (
        "synthetic.sentiment.first-signal",
        "synthetic.sentiment.last-signal",
    )

    changed_revision = replace(
        plan.instrument_revisions[0],
        implementation_revision="ctrt-fixture-first@9.9.9",
    )
    drifted = replace(
        plan,
        instrument_revisions=(
            changed_revision,
            plan.instrument_revisions[1],
        ),
    )
    with pytest.raises(CandidateEligibilityError, match="registry pin"):
        validate_candidate_eligibility(drifted, registry)

    real_document = candidate_fx.load_document(candidate_fx.INITIAL_PATH)
    real_document["status"] = "accepted"
    real_registry = CandidateRegistrySnapshot.from_document(real_document)
    with pytest.raises(CandidateEligibilityError):
        validate_candidate_eligibility(
            candidate_fx.plan_for(real_registry),
            real_registry,
        )


def test_extraction_provenance_reconstructs_inputs_and_blocks_partial_completion(
    tmp_path: Path,
) -> None:
    store, candidate_registry, manifest, plan, analyzers = (
        extraction_fx.prepare_store(tmp_path)
    )
    loaded = load_extracted_corpus(store, manifest)

    assert tuple(item.content_id for item in loaded.contents) == manifest.content_ids
    assert all(
        item.canonical_extraction_ref.startswith("extraction:")
        for item in loaded.contents
    )
    assert all(
        not reference.artifact_id.startswith("content-item:")
        for reference in loaded.content_refs
    )
    with pytest.raises(ExtractionManifestError, match="extracted content ID"):
        ExtractedContentSnapshot.from_document(
            extraction_fx.load_document(extraction_fx.LEGACY_CONTENT_PATH)
        )

    failing_store = extraction_fx.SourceReadFailsStore(
        store.root,
        manifest.contents[1].source_artifact_ref.artifact_id,
    )
    runner = ExtractionBoundExperimentRunner(
        analyzer_registry=extraction_fx.analyzer_registry(*analyzers),
        artifact_store=failing_store,
    )
    run_id = "constitutional-missing-source"
    with pytest.raises(ExtractionBoundExperimentError) as captured:
        runner.run(
            plan=plan,
            candidate_registry=candidate_registry,
            corpus_manifest=manifest,
            environment=extraction_fx.environment(),
            windows=extraction_fx.windows(),
            experiment_run_id=run_id,
        )
    assert captured.value.stage is ExtractionBoundRunnerStage.EXTRACTION_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:experiment-completion")


def test_historical_plans_and_runs_remain_interpretable_and_append_only() -> None:
    frozen, frozen_ref, _, record = experiment_fx.recorded_run()
    ledger = InMemoryExperimentLedger()
    ledger.append_plan(frozen_ref, frozen)
    ledger.append_run(record)

    successor = replace(
        frozen,
        experiment_version="0.1.1",
        research_question=(
            "Can a new specification append without rewriting prior evidence?"
        ),
        created_at="2026-08-02T20:02:00Z",
    )
    successor_ref = experiment_fx.plan_reference(successor)
    ledger.append_plan(successor_ref, successor)

    assert ledger.plans() == (frozen, successor)
    assert ledger.runs() == (record,)
    with pytest.raises(ValueError, match="append-only"):
        ledger.append_plan(frozen_ref, frozen)
    with pytest.raises(ValueError, match="append-only"):
        ledger.append_run(record)


def test_unresolved_authority_conflict_stops_before_delegation(
    tmp_path: Path,
) -> None:
    document = deepcopy(
        adjudication_fx.contract_fx.load_document(
            adjudication_fx.contract_fx.ADJUDICATION_PATH
        )
    )
    document["status"] = "unresolved"
    document["selected_head_ref"] = None
    document["rationale"] = "Constitutional proof preserves unresolved conflict."
    record = adjudication_fx.contract_fx.conflict_adjudication(document)
    run_id = "constitutional-unresolved-authority"
    receipt, store, stub, _ = adjudication_fx.execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=None,
        record=record,
    )

    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert all(
        getattr(receipt, name) is None
        for name in adjudication_fx.DELEGATED_OUTCOME_FIELDS
    )
    assert receipt.predecessor_witness_receipt is None
    assert not stub.calls
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            f"{run_id}:current-revocation-checkpoint-witness-conflict-"
            "adjudicator-credential-revocation-checkpoint-witness-completion"
        )


def test_closed_real_chain_can_be_verified_with_delegated_abstention(
    tmp_path: Path,
) -> None:
    run_id = "constitutional-closed-chain-abstention"
    delegated = closure_fx.later_abstaining_revocation_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = closure_fx.execute(
        tmp_path,
        run_id=run_id,
        revocation_receipt=delegated,
        current_credential_revocation_evaluated_at=(
            "2027-01-01T00:00:22Z"
        ),
        current_credential_revocation_completed_at=(
            "2027-01-01T00:00:23Z"
        ),
        completed_at="2027-01-01T00:00:24Z",
    )

    assert receipt.status is closure_fx.RunnerStatus.VERIFIED
    assert receipt.closure_state == "closed"
    assert receipt.automatic_successor_layers_allowed is False
    assert receipt.reopen_requires_documented_failure is True
    assert (
        receipt.permitted_reopen_trigger
        == "concrete-unrepresented-failure"
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert tuple(
        getattr(receipt, name) for name in closure_fx.PR53_OUTCOME_FIELDS
    ) == tuple(
        getattr(delegated, name) for name in closure_fx.PR53_OUTCOME_FIELDS
    )
    assert stub.report_existed_before_call is True
    assert len(stub.calls) == 1

    final = closure_fx.final_document(receipt, store)
    _assert_constitutional_output_surface(receipt)
    _assert_constitutional_output_surface(final)

    checkpoint = closure_fx.closure_fx.checkpoint()
    assert receipt.checkpoint_head_ref.artifact_hash == checkpoint.artifact_hash
    population_payload = json.dumps(
        {
            "event_refs": [
                canonical_data(reference)
                for reference in checkpoint.event_refs
            ]
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert checkpoint.event_population_hash == (
        f"sha256:{hashlib.sha256(population_payload).hexdigest()}"
    )
