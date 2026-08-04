from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_gated_witness_conflict_adjudicator_checkpoint_runner import (
    WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS,
    WitnessConflictAdjudicatorCheckpointExperimentError,
    WitnessConflictAdjudicatorCheckpointRunnerStage,
    WitnessConflictAdjudicatorCheckpointRunnerStatus,
    WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner,
)

witness_fx = import_module("test_witness_conflict_adjudicator_checkpoint_witness")
checkpoint_fx = import_module(
    "test_checkpoint_conflict_witness_adjudicator_credential_"
    "revocation_checkpoints"
)
lower_fx = checkpoint_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "witness-gated-witness-conflict-adjudicator-checkpoint-final.schema.json"
)


def prepare_current_store(
    tmp_path: Path,
    *,
    run_id: str,
    conflict: bool,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    if not conflict:
        return witness_fx.prepare_witness_store(tmp_path, run_id=run_id), (
            witness_fx.witness_attestations()
        )

    prepared = checkpoint_fx.prepare_checkpoint_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    documents = tuple(
        load_document(path) for path in witness_fx.ATTESTATION_PATHS
    )
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed_documents[2]["observation_kind"] = "conflicting_head"
    attestations = witness_fx.witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(witness_fx.CORPUS_PATH))
    key = (
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_checkpoint_witness_attestation_refs"
    )
    corpus_document[key][2] = witness_fx.stored_ref_document(
        attestations[2].reference()
    )
    selected = witness_fx.witness_corpus(
        corpus_document,
        predecessor=prepared[2],
    )
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    witness_fx.persist_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=prepared[2],
        registry=witness_fx.witness_registry(),
        policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        attestations=attestations,
        evaluated_at="2026-08-03T19:55:05Z",
    )
    return (store, plan, selected, *prepared[2:]), attestations


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    conflict: bool = False,
    checkpoint_verified_at: str = "2026-08-03T19:55:04Z",
    current_witness_evaluated_at: str = "2026-08-03T19:55:05Z",
    revocation_evaluated_at: str = "2026-08-03T19:55:06Z",
    credential_evaluated_at: str = "2026-08-03T19:55:10Z",
    adjudication_evaluated_at: str = "2026-08-03T19:55:30Z",
    adjudication_completed_at: str = "2026-08-03T19:56:00Z",
    credential_completed_at: str = "2026-08-03T19:56:30Z",
    revocation_completed_at: str = "2026-08-03T19:56:45Z",
    checkpoint_completed_at: str = "2026-08-03T19:57:00Z",
    completed_at: str = "2026-08-03T19:57:15Z",
):
    prepared, current_attestations = prepare_current_store(
        tmp_path,
        run_id=run_id,
        conflict=conflict,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        checkpoint_corpus=prepared[3],
        revocation_corpus=prepared[4],
        credential_corpus=prepared[5],
        adjudication_corpus=prepared[6],
        checkpoint_policy=checkpoint_fx.checkpoint_policy(),
        checkpoint_log=checkpoint_fx.checkpoint_log(),
        checkpoints=(checkpoint_fx.checkpoint(),),
        current_witness_registry=witness_fx.witness_registry(),
        current_witness_policy=witness_fx.witness_policy(),
        current_witness_attestations=current_attestations,
        prior_witness_registry=lower_fx.credential_runner_fx.witness_fx.witness_registry(),
        prior_witness_policy=lower_fx.credential_runner_fx.witness_fx.witness_policy(),
        prior_witness_attestations=(
            lower_fx.credential_runner_fx.witness_fx.witness_attestations()
        ),
        prior_head_checkpoint=lower_fx.credential_runner_fx.checkpoint(),
        adjudicator_registry=(
            lower_fx.credential_runner_fx.adjudication_fx.adjudicator_registry()
        ),
        adjudication_policy=(
            lower_fx.credential_runner_fx.adjudication_fx.adjudication_policy()
        ),
        adjudication=lower_fx.credential_runner_fx.adjudication_fx.adjudication(),
        issuer_registry=lower_fx.credential_runner_fx.credential_fx.issuer_registry(),
        credential_policy=(
            lower_fx.credential_runner_fx.credential_fx.credential_policy()
        ),
        revocation_policy=lower_fx.revocation_fx.revocation_policy(),
        revocation_ledger=lower_fx.revocation_fx.revocation_ledger(),
        revocation_events=(lower_fx.revocation_fx.suspension_event(),),
        prior_witness_receipt=prepared[7],
        checkpoint_executor=None,
        experiment_run_id=run_id,
        checkpoint_verified_at=checkpoint_verified_at,
        current_witness_evaluated_at=current_witness_evaluated_at,
        prior_witness_evaluated_at="2026-08-03T19:53:30Z",
        revocation_evaluated_at=revocation_evaluated_at,
        credential_evaluated_at=credential_evaluated_at,
        adjudication_evaluated_at=adjudication_evaluated_at,
        adjudication_completed_at=adjudication_completed_at,
        credential_completed_at=credential_completed_at,
        revocation_completed_at=revocation_completed_at,
        checkpoint_completed_at=checkpoint_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def test_all_current_witnesses_delegate_exact_pr34_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-witness-execute")
    assert receipt.status is WitnessConflictAdjudicatorCheckpointRunnerStatus.VERIFIED
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert (
        receipt.prior_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.checkpoint_receipt is not None
    assert (
        receipt.verified_checks
        == WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_one_current_conflict_abstains_before_pr34(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-witness-conflict",
        conflict=True,
    )
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.revocation_outcome is None
    assert receipt.credential_outcome is None
    assert receipt.prior_checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    checkpoint_report = store.get(receipt.checkpoint_verification_ref.artifact_id)
    witness_decision = store.get(receipt.witness_decision_ref.artifact_id)
    assert checkpoint_report.artifact_hash == receipt.checkpoint_verification_ref.artifact_hash
    assert witness_decision.artifact_hash == receipt.witness_decision_ref.artifact_hash
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_current_witness_execute_preserves_later_revocation_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-witness-later-revocation",
        revocation_evaluated_at="2027-01-01T00:00:00Z",
        credential_evaluated_at="2027-01-01T00:00:01Z",
        adjudication_evaluated_at="2027-01-01T00:00:02Z",
        adjudication_completed_at="2027-01-01T00:00:03Z",
        credential_completed_at="2027-01-01T00:00:04Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        checkpoint_completed_at="2027-01-01T00:00:06Z",
        completed_at="2027-01-01T00:00:07Z",
    )
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.prior_checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is not None
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_current_witness_before_checkpoint_reverification_fails_preflight(
    tmp_path: Path,
) -> None:
    with pytest.raises(WitnessConflictAdjudicatorCheckpointExperimentError) as captured:
        execute(
            tmp_path,
            run_id="current-witness-before-checkpoint",
            current_witness_evaluated_at="2026-08-03T19:55:03Z",
        )
    assert captured.value.stage is WitnessConflictAdjudicatorCheckpointRunnerStage.PREFLIGHT
