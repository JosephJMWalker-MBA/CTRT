from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome

checkpoint_fx = import_module(
    "test_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
)
pr48_fx = import_module(
    "test_revocation_gated_current_revocation_checkpoint_witness_conflict_runner"
)
runner_module = import_module(
    "ctrt.checkpoint_gated_current_revocation_checkpoint_witness_conflict_runner"
)

Runner = vars(runner_module)[
    "CheckpointGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner"
]
RunnerError = vars(runner_module)[
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointExperimentError"
]
RunnerStage = vars(runner_module)[
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointRunnerStage"
]
RunnerStatus = vars(runner_module)[
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
    "CheckpointRunnerStatus"
]
VERIFIED_CHECKS = vars(runner_module)[
    "CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_"
    "REVOCATION_CHECKPOINT_VERIFIED_CHECKS"
]

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "checkpoint-gated-current-revocation-checkpoint-witness-conflict-"
    "final.schema.json"
)


class StubRevocationRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def _persist_checkpoint(
    store: FileSystemArtifactStore,
    *,
    predecessor_plan: Any,
    predecessor: Any,
) -> tuple[Any, Any]:
    selected = checkpoint_fx.checkpoint_corpus(predecessor=predecessor)
    plan = replace(
        predecessor_plan,
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    checkpoint_fx.persist_checkpoint_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        policy=checkpoint_fx.checkpoint_policy(),
        log=checkpoint_fx.checkpoint_log(),
        ledger=checkpoint_fx.revocation_fx.revocation_ledger(),
        checkpoints=(checkpoint_fx.checkpoint(),),
        verified_at="2026-08-03T19:58:53Z",
    )
    return plan, selected


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    delegated_receipt: Any,
    delegated_store: FileSystemArtifactStore,
    delegated_prepared: tuple[Any, ...],
    checkpoint_verified_at: str = "2026-08-03T19:58:53Z",
    revocation_evaluated_at: str = "2026-08-03T19:58:54Z",
    revocation_completed_at: str,
    completed_at: str,
):
    plan, selected = _persist_checkpoint(
        delegated_store,
        predecessor_plan=delegated_prepared[1],
        predecessor=delegated_prepared[2],
    )
    runner = Runner(artifact_store=delegated_store)
    stub = StubRevocationRunner(delegated_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=plan,
        corpus=selected,
        current_revocation_corpus=delegated_prepared[2],
        current_checkpoint_policy=checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=checkpoint_fx.checkpoint_log(),
        current_checkpoints=(checkpoint_fx.checkpoint(),),
        current_revocation_ledger=checkpoint_fx.revocation_fx.revocation_ledger(),
        experiment_run_id=run_id,
        current_checkpoint_verified_at=checkpoint_verified_at,
        current_revocation_evaluated_at=revocation_evaluated_at,
        revocation_completed_at=revocation_completed_at,
        completed_at=completed_at,
    )
    return receipt, stub


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_checkpoint_delegates_exact_pr48_execute(tmp_path: Path) -> None:
    run_id = "current-revocation-checkpoint-active"
    credential_receipt = pr48_fx.active_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    delegated, store, _, prepared = pr48_fx.execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
    )
    receipt, stub = execute(
        tmp_path,
        run_id=run_id,
        delegated_receipt=delegated,
        delegated_store=store,
        delegated_prepared=prepared,
        revocation_completed_at=delegated.completed_at,
        completed_at="2026-08-04T00:00:34Z",
    )
    assert receipt.status is RunnerStatus.VERIFIED
    assert receipt.revocation_receipt is delegated
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.verified_checks == VERIFIED_CHECKS
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[2].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_checkpoint_preserves_later_pr48_abstention(tmp_path: Path) -> None:
    run_id = "current-revocation-checkpoint-later-abstention"
    credential_receipt = pr48_fx.later_abstaining_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    delegated, store, _, prepared = pr48_fx.execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
        prior_completed_at="2027-01-01T00:00:11Z",
        completed_at="2027-01-01T00:00:12Z",
    )
    receipt, stub = execute(
        tmp_path,
        run_id=run_id,
        delegated_receipt=delegated,
        delegated_store=store,
        delegated_prepared=prepared,
        revocation_completed_at=delegated.completed_at,
        completed_at="2027-01-01T00:00:13Z",
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_checkpoint_after_revocation_fails_preflight(tmp_path: Path) -> None:
    run_id = "current-revocation-checkpoint-late"
    credential_receipt = pr48_fx.active_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    delegated, store, _, prepared = pr48_fx.execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
    )
    with pytest.raises(RunnerError) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            delegated_receipt=delegated,
            delegated_store=store,
            delegated_prepared=prepared,
            checkpoint_verified_at="2026-08-03T19:58:55Z",
            revocation_evaluated_at="2026-08-03T19:58:54Z",
            revocation_completed_at=delegated.completed_at,
            completed_at="2026-08-04T00:00:34Z",
        )
    assert captured.value.stage is RunnerStage.PREFLIGHT
