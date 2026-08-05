from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome

closure_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness_conflict_"
    "adjudicator_credential_revocation_closure_checkpoints"
)
pr53_fx = import_module(
    "test_revocation_gated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_conflict_adjudicator_credential_runner"
)
runner_module = import_module(
    "ctrt.closure_checkpoint_gated_current_revocation_conflict_adjudicator_"
    "checkpoint_witness_conflict_adjudicator_credential_revocation_runner"
)

Runner = vars(runner_module)[
    "ClosureCheckpointGatedCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessConflictAdjudicatorCredentialRevocationExperimentRunner"
]
RunnerError = vars(runner_module)[
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointExperimentError"
]
RunnerStage = vars(runner_module)[
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointRunnerStage"
]
RunnerStatus = vars(runner_module)[
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointRunnerStatus"
]
VERIFIED_CHECKS = vars(runner_module)[
    "CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_WITNESS_CONFLICT_"
    "ADJUDICATOR_CREDENTIAL_REVOCATION_CLOSURE_CHECKPOINT_VERIFIED_CHECKS"
]
PR53_OUTCOME_FIELDS = runner_module.PR53_OUTCOME_FIELDS

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "closure-checkpoint-gated-current-revocation-conflict-adjudicator-"
    "checkpoint-witness-conflict-adjudicator-credential-revocation-final."
    "schema.json"
)
REPORT_SUFFIX = (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-checkpoint-verification"
)


class StubRevocationRunner:
    def __init__(
        self,
        receipt: Any,
        *,
        store: FileSystemArtifactStore,
        run_id: str,
    ) -> None:
        self.receipt = receipt
        self.store = store
        self.run_id = run_id
        self.calls: list[dict[str, Any]] = []
        self.report_existed_before_call = False

    def run(self, **kwargs: Any) -> Any:
        self.store.get(f"{self.run_id}:{REPORT_SUFFIX}")
        self.report_existed_before_call = True
        self.calls.append(kwargs)
        return self.receipt


def active_revocation_receipt(tmp_path: Path, *, run_id: str) -> Any:
    credential_receipt = pr53_fx.active_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr53_fx.execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
    )
    return receipt


def later_abstaining_revocation_receipt(
    tmp_path: Path,
    *,
    run_id: str,
) -> Any:
    credential_receipt = pr53_fx.later_abstaining_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr53_fx.execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        current_revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        witness_completed_at="2027-01-01T00:00:18Z",
        adjudication_completed_at="2027-01-01T00:00:19Z",
        credential_completed_at="2027-01-01T00:00:20Z",
        completed_at="2027-01-01T00:00:21Z",
    )
    return receipt


def final_document(
    receipt: Any,
    store: FileSystemArtifactStore,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    revocation_receipt: Any,
    closure_checkpoint_verified_at: str = "2026-08-03T19:59:22Z",
    current_credential_revocation_evaluated_at: str = (
        "2026-08-03T19:59:23Z"
    ),
    current_credential_revocation_completed_at: str = (
        "2026-08-04T00:00:39Z"
    ),
    completed_at: str = "2026-08-04T00:00:40Z",
):
    prepared = closure_fx.prepare_closure_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = Runner(artifact_store=store)
    stub = StubRevocationRunner(
        revocation_receipt,
        store=store,
        run_id=run_id,
    )
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        current_revocation_corpus=prepared[3],
        closure_checkpoint_policy=closure_fx.closure_policy(),
        closure_checkpoint_log=closure_fx.checkpoint_log(),
        closure_checkpoints=(closure_fx.checkpoint(),),
        current_revocation_ledger=closure_fx.revocation_fx.revocation_ledger(),
        experiment_run_id=run_id,
        closure_checkpoint_verified_at=closure_checkpoint_verified_at,
        current_credential_revocation_evaluated_at=(
            current_credential_revocation_evaluated_at
        ),
        current_credential_revocation_completed_at=(
            current_credential_revocation_completed_at
        ),
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_closure_checkpoint_delegates_exact_pr53(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudicator-credential-revocation-closure"
    delegated = active_revocation_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        revocation_receipt=delegated,
    )
    assert receipt.status is RunnerStatus.VERIFIED
    assert receipt.closure_state == "closed"
    assert receipt.automatic_successor_layers_allowed is False
    assert receipt.reopen_requires_documented_failure is True
    assert (
        receipt.permitted_reopen_trigger
        == "concrete-unrepresented-failure"
    )
    assert tuple(
        getattr(receipt, name) for name in PR53_OUTCOME_FIELDS
    ) == tuple(getattr(delegated, name) for name in PR53_OUTCOME_FIELDS)
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.revocation_receipt is delegated
    assert receipt.verified_checks == VERIFIED_CHECKS
    assert receipt.checkpoint_head_ref == closure_fx.checkpoint().reference()
    assert stub.report_existed_before_call is True
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_closure_checkpoint_preserves_delegated_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudicator-closure-later-abstention"
    delegated = later_abstaining_revocation_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = execute(
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
    assert receipt.status is RunnerStatus.VERIFIED
    assert receipt.closure_state == "closed"
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.revocation_receipt is delegated
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_late_closure_checkpoint_fails_before_pr53(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudicator-closure-late-checkpoint"
    delegated = active_revocation_receipt(tmp_path, run_id=run_id)
    with pytest.raises(RunnerError) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            revocation_receipt=delegated,
            closure_checkpoint_verified_at="2026-08-03T19:59:24Z",
            current_credential_revocation_evaluated_at=(
                "2026-08-03T19:59:23Z"
            ),
        )
    assert captured.value.stage is RunnerStage.PREFLIGHT


def test_structural_failure_creates_no_pr53_runtime_final(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudicator-closure-structural-failure"
    delegated = active_revocation_receipt(tmp_path, run_id=run_id)
    with pytest.raises(RunnerError):
        execute(
            tmp_path,
            run_id=run_id,
            revocation_receipt=delegated,
            closure_checkpoint_verified_at="2026-08-03T19:59:24Z",
            current_credential_revocation_evaluated_at=(
                "2026-08-03T19:59:23Z"
            ),
        )
    prepared = closure_fx.prepare_closure_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    closure_final = (
        f"{run_id}:current-revocation-conflict-adjudicator-checkpoint-"
        "witness-conflict-adjudicator-credential-revocation-closure-"
        "checkpoint-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(closure_final)
