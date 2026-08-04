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

from ctrt.adjudicated_witness_conflict_adjudicator_checkpoint_runner import (
    ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
    AdjudicatedCheckpointWitnessConflictExperimentError,
    AdjudicatedCheckpointWitnessConflictRunnerStage,
    AdjudicatedCheckpointWitnessConflictRunnerStatus,
    AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

conflict_fx = import_module(
    "test_witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication"
)
witness_fx = import_module("test_witness_conflict_adjudicator_checkpoint_witness")
checkpoint_fx = import_module(
    "test_checkpoint_conflict_witness_adjudicator_credential_"
    "revocation_checkpoints"
)
lower_fx = checkpoint_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "adjudicated-witness-conflict-adjudicator-checkpoint-final.schema.json"
)


def pending_adjudication():
    document = deepcopy(load_document(conflict_fx.ADJUDICATION_PATH))
    document.update(
        {
            "status": "pending",
            "adjudicator_id": None,
            "adjudicator_identity_revision": None,
            "selected_head_ref": None,
            "preserved_dissent": [],
            "rationale": "Synthetic conflict remains pending authorized review.",
        }
    )
    return conflict_fx.conflict_adjudication(document)


def prepare_for_record(
    tmp_path: Path,
    *,
    run_id: str,
    record: Any,
) -> tuple[Any, ...]:
    prepared = witness_fx.prepare_witness_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    document = deepcopy(load_document(conflict_fx.CORPUS_PATH))
    key = (
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_checkpoint_witness_conflict_adjudication_ref"
    )
    document[key] = conflict_fx.stored_ref_document(record.reference())
    if record.status.value != "resolved":
        document["corpus_id"] = (
            "corpus.synthetic-three-items.checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            f"witness-adjudication-bound.{record.status.value}-runner-test"
        )
        document["corpus_version"] = f"1.14.1-runner-{record.status.value}"
    selected = conflict_fx.adjudication_corpus(
        document,
        checkpoint_predecessor=prepared[3],
        witness_predecessor=prepared[2],
    )
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    conflict_fx.persist_adjudication_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        witness_predecessor=prepared[2],
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        witness_attestations=conflict_fx.conflict_attestations(),
        adjudicator_registry=conflict_fx.conflict_adjudicator_registry(),
        adjudication_policy=conflict_fx.conflict_adjudication_policy(),
        adjudication=record,
        evaluated_at="2026-08-03T19:57:21Z",
    )
    return (store, plan, selected, *prepared[2:])


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    record: Any | None = None,
    conflict_witness_evaluated_at: str = "2026-08-03T19:57:22Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:57:23Z",
    checkpoint_verified_at: str = "2026-08-03T19:57:24Z",
    predecessor_witness_evaluated_at: str = "2026-08-03T19:57:25Z",
    revocation_evaluated_at: str = "2026-08-03T19:57:26Z",
    credential_evaluated_at: str = "2026-08-03T19:57:30Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:57:40Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:00Z",
    credential_completed_at: str = "2026-08-03T19:58:15Z",
    revocation_completed_at: str = "2026-08-03T19:58:30Z",
    checkpoint_completed_at: str = "2026-08-03T19:58:45Z",
    prior_completed_at: str = "2026-08-03T19:59:00Z",
    completed_at: str = "2026-08-03T19:59:15Z",
):
    selected_record = record or conflict_fx.conflict_adjudication()
    prepared = prepare_for_record(
        tmp_path,
        run_id=run_id,
        record=selected_record,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        witness_predecessor=prepared[3],
        checkpoint_corpus=prepared[4],
        revocation_corpus=prepared[5],
        credential_corpus=prepared[6],
        adjudication_corpus=prepared[7],
        checkpoint_policy=checkpoint_fx.checkpoint_policy(),
        checkpoint_log=checkpoint_fx.checkpoint_log(),
        checkpoints=(checkpoint_fx.checkpoint(),),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        conflict_witness_attestations=conflict_fx.conflict_attestations(),
        predecessor_witness_attestations=witness_fx.witness_attestations(),
        conflict_adjudicator_registry=(
            conflict_fx.conflict_adjudicator_registry()
        ),
        conflict_adjudication_policy=(
            conflict_fx.conflict_adjudication_policy()
        ),
        conflict_adjudication=selected_record,
        inherited_witness_registry=(
            lower_fx.credential_runner_fx.witness_fx.witness_registry()
        ),
        inherited_witness_policy=(
            lower_fx.credential_runner_fx.witness_fx.witness_policy()
        ),
        inherited_witness_attestations=(
            lower_fx.credential_runner_fx.witness_fx.witness_attestations()
        ),
        inherited_head_checkpoint=lower_fx.credential_runner_fx.checkpoint(),
        inherited_adjudicator_registry=(
            lower_fx.credential_runner_fx.adjudication_fx.adjudicator_registry()
        ),
        inherited_adjudication_policy=(
            lower_fx.credential_runner_fx.adjudication_fx.adjudication_policy()
        ),
        inherited_adjudication=(
            lower_fx.credential_runner_fx.adjudication_fx.adjudication()
        ),
        issuer_registry=lower_fx.credential_runner_fx.credential_fx.issuer_registry(),
        credential_policy=(
            lower_fx.credential_runner_fx.credential_fx.credential_policy()
        ),
        revocation_policy=lower_fx.revocation_fx.revocation_policy(),
        revocation_ledger=lower_fx.revocation_fx.revocation_ledger(),
        revocation_events=(lower_fx.revocation_fx.suspension_event(),),
        inherited_witness_receipt=prepared[8],
        checkpoint_executor=None,
        experiment_run_id=run_id,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        conflict_adjudication_evaluated_at=(
            conflict_adjudication_evaluated_at
        ),
        checkpoint_verified_at=checkpoint_verified_at,
        predecessor_witness_evaluated_at=predecessor_witness_evaluated_at,
        inherited_witness_evaluated_at="2026-08-03T19:57:25Z",
        revocation_evaluated_at=revocation_evaluated_at,
        credential_evaluated_at=credential_evaluated_at,
        inherited_adjudication_evaluated_at=(
            inherited_adjudication_evaluated_at
        ),
        inherited_adjudication_completed_at=(
            inherited_adjudication_completed_at
        ),
        credential_completed_at=credential_completed_at,
        revocation_completed_at=revocation_completed_at,
        checkpoint_completed_at=checkpoint_completed_at,
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def test_resolved_conflict_delegates_exact_pr35_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="resolved-current-conflict")
    assert receipt.status is AdjudicatedCheckpointWitnessConflictRunnerStatus.VERIFIED
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.predecessor_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert (
        receipt.inherited_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.inherited_resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert (
        receipt.inherited_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.predecessor_witness_receipt is not None
    assert receipt.verified_checks == (
        ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
    )
    witness_decision = store.get(receipt.witness_decision_ref.artifact_id)
    adjudication_decision = store.get(receipt.adjudication_decision_ref.artifact_id)
    assert witness_decision.artifact_hash == receipt.witness_decision_ref.artifact_hash
    assert adjudication_decision.artifact_hash == receipt.adjudication_decision_ref.artifact_hash
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_pending_conflict_abstains_before_pr35(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="pending-current-conflict",
        record=pending_adjudication(),
    )
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.PENDING
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.ABSTAIN
    )
    assert receipt.predecessor_witness_outcome is None
    assert receipt.revocation_outcome is None
    assert receipt.credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.predecessor_witness_receipt is None
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_resolution_preserves_later_revocation_abstention(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="resolved-current-conflict-later-suspension",
        revocation_evaluated_at="2027-01-01T00:00:00Z",
        credential_evaluated_at="2027-01-01T00:00:01Z",
        inherited_adjudication_evaluated_at="2027-01-01T00:00:02Z",
        inherited_adjudication_completed_at="2027-01-01T00:00:03Z",
        credential_completed_at="2027-01-01T00:00:04Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        checkpoint_completed_at="2027-01-01T00:00:06Z",
        prior_completed_at="2027-01-01T00:00:07Z",
        completed_at="2027-01-01T00:00:08Z",
    )
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.predecessor_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.predecessor_witness_receipt is not None
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_adjudication_before_witness_evaluation_fails_preflight(tmp_path: Path) -> None:
    with pytest.raises(AdjudicatedCheckpointWitnessConflictExperimentError) as captured:
        execute(
            tmp_path,
            run_id="adjudication-before-witness",
            conflict_adjudication_evaluated_at="2026-08-03T19:57:21Z",
        )
    assert captured.value.stage is AdjudicatedCheckpointWitnessConflictRunnerStage.PREFLIGHT
