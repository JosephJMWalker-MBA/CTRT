from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema
from test_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_log,
    checkpoint_policy,
    prepare_checkpoint_store,
)

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_gated_current_checkpoint_witness_conflict_runner import (
    CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS,
    CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome

lower_fx = import_module(
    "test_revocation_gated_current_checkpoint_witness_conflict_runner"
)

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "checkpoint-gated-current-checkpoint-witness-conflict-final.schema.json"
)


class StubRevocationRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_lower_receipt(tmp_path: Path, *, run_id: str):
    return lower_fx.execute(
        tmp_path,
        run_id=run_id,
        current_conflict_adjudicator_revocation_evaluated_at=(
            "2026-08-04T00:00:01Z"
        ),
        conflict_credential_evaluated_at="2026-08-04T00:00:02Z",
        conflict_witness_evaluated_at="2026-08-04T00:00:03Z",
        conflict_adjudication_evaluated_at="2026-08-04T00:00:04Z",
        current_checkpoint_verified_at="2026-08-04T00:00:05Z",
        current_witness_evaluated_at="2026-08-04T00:00:06Z",
        current_revocation_evaluated_at="2026-08-04T00:00:07Z",
        current_credential_evaluated_at="2026-08-04T00:00:08Z",
        lower_conflict_witness_evaluated_at="2026-08-04T00:00:09Z",
        lower_conflict_adjudication_evaluated_at="2026-08-04T00:00:10Z",
        checkpoint_verified_at="2026-08-04T00:00:11Z",
        lower_predecessor_witness_evaluated_at="2026-08-04T00:00:12Z",
        inherited_witness_evaluated_at="2026-08-04T00:00:12Z",
        inherited_revocation_evaluated_at="2026-08-04T00:00:13Z",
        inherited_credential_evaluated_at="2026-08-04T00:00:14Z",
        inherited_adjudication_evaluated_at="2026-08-04T00:00:15Z",
        inherited_adjudication_completed_at="2026-08-04T00:00:16Z",
        inherited_credential_completed_at="2026-08-04T00:00:17Z",
        inherited_revocation_completed_at="2026-08-04T00:00:18Z",
        checkpoint_completed_at="2026-08-04T00:00:19Z",
        lower_completed_at="2026-08-04T00:00:20Z",
        current_revocation_completed_at="2026-08-04T00:00:21Z",
        current_checkpoint_completed_at="2026-08-04T00:00:22Z",
        prior_completed_at="2026-08-04T00:00:23Z",
        completed_at="2026-08-04T00:00:24Z",
    )


def suspended_lower_receipt(tmp_path: Path, *, run_id: str):
    return lower_fx.execute(
        tmp_path,
        run_id=run_id,
        current_conflict_adjudicator_revocation_evaluated_at=(
            "2027-01-01T00:00:01Z"
        ),
        conflict_credential_evaluated_at="2027-01-01T00:00:02Z",
        conflict_witness_evaluated_at="2027-01-01T00:00:03Z",
        prior_completed_at="2027-01-01T00:00:04Z",
        completed_at="2027-01-01T00:00:05Z",
    )


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def execute_outer(
    tmp_path: Path,
    *,
    run_id: str,
    lower_receipt: Any,
    checkpoint_verified_at: str,
    revocation_evaluated_at: str,
    revocation_completed_at: str,
    completed_at: str,
):
    prepared = prepare_checkpoint_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner(
        artifact_store=store
    )
    stub = StubRevocationRunner(lower_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        current_revocation_corpus=prepared[3],
        current_checkpoint_policy=checkpoint_policy(),
        current_checkpoint_log=checkpoint_log(),
        current_checkpoints=(checkpoint(),),
        current_conflict_adjudicator_revocation_ledger=(
            lower_fx.revocation_fx.revocation_ledger()
        ),
        experiment_run_id=run_id,
        current_checkpoint_verified_at=checkpoint_verified_at,
        current_conflict_adjudicator_revocation_evaluated_at=(
            revocation_evaluated_at
        ),
        revocation_completed_at=revocation_completed_at,
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_verified_checkpoint_delegates_exact_pr43(tmp_path: Path) -> None:
    run_id = "current-conflict-revocation-checkpoint-active"
    lower_receipt, _ = active_lower_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute_outer(
        tmp_path,
        run_id=run_id,
        lower_receipt=lower_receipt,
        checkpoint_verified_at="2026-08-04T00:00:00Z",
        revocation_evaluated_at="2026-08-04T00:00:01Z",
        revocation_completed_at="2026-08-04T00:00:24Z",
        completed_at="2026-08-04T00:00:25Z",
    )
    expected_status = (
        CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
    )
    assert receipt.status is expected_status
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.revocation_receipt is lower_receipt
    assert receipt.checkpoint_head_ref == checkpoint().reference()
    assert receipt.verified_checks == (
        CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
    )
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_verified_checkpoint_preserves_pr43_revocation_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-revocation-checkpoint-suspended"
    lower_receipt, _ = suspended_lower_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, _ = execute_outer(
        tmp_path,
        run_id=run_id,
        lower_receipt=lower_receipt,
        checkpoint_verified_at="2027-01-01T00:00:00Z",
        revocation_evaluated_at="2027-01-01T00:00:01Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        completed_at="2027-01-01T00:00:06Z",
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.current_conflict_adjudicator_credential_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.revocation_receipt is lower_receipt
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_checkpoint_after_revocation_fails_before_delegation(tmp_path: Path) -> None:
    run_id = "current-conflict-revocation-checkpoint-late"
    lower_receipt, _ = active_lower_receipt(tmp_path, run_id=run_id)
    with pytest.raises(
        CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError
    ) as captured:
        execute_outer(
            tmp_path,
            run_id=run_id,
            lower_receipt=lower_receipt,
            checkpoint_verified_at="2026-08-04T00:00:02Z",
            revocation_evaluated_at="2026-08-04T00:00:01Z",
            revocation_completed_at="2026-08-04T00:00:24Z",
            completed_at="2026-08-04T00:00:25Z",
        )
    expected = (
        CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage.PREFLIGHT
    )
    assert captured.value.stage is expected