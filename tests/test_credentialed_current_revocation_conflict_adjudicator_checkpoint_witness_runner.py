from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

credential_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential"
)
pr51_fx = import_module(
    "test_adjudicated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)
runner_module = import_module(
    "ctrt.credentialed_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)

Runner = vars(runner_module)[
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentRunner"
]
RunnerError = vars(runner_module)[
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentError"
]
RunnerStage = vars(runner_module)[
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStage"
]
RunnerStatus = vars(runner_module)[
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStatus"
]
VERIFIED_CHECKS = vars(runner_module)[
    "CREDENTIALED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_VERIFIED_CHECKS"
]
ADJUDICATION_OUTCOME_FIELDS = runner_module.ADJUDICATION_OUTCOME_FIELDS

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "credentialed-current-revocation-conflict-adjudicator-checkpoint-"
    "witness-final.schema.json"
)


class StubAdjudicationRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_adjudication_receipt(
    tmp_path: Path,
    *,
    run_id: str,
) -> Any:
    witness_receipt = pr51_fx.active_witness_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr51_fx.execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
        conflict_witness_evaluated_at="2026-08-03T19:59:15Z",
        conflict_adjudication_evaluated_at="2026-08-03T19:59:16Z",
        checkpoint_reverified_at="2026-08-03T19:59:17Z",
        canonical_witness_evaluated_at="2026-08-03T19:59:18Z",
        delegated_checkpoint_verified_at="2026-08-03T19:59:19Z",
        completed_at="2026-08-04T00:00:36Z",
    )
    return receipt


def later_abstaining_adjudication_receipt(
    tmp_path: Path,
    *,
    run_id: str,
) -> Any:
    witness_receipt = pr51_fx.later_abstaining_witness_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr51_fx.execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
        conflict_witness_evaluated_at="2026-08-03T19:59:15Z",
        conflict_adjudication_evaluated_at="2026-08-03T19:59:16Z",
        checkpoint_reverified_at="2026-08-03T19:59:17Z",
        canonical_witness_evaluated_at="2026-08-03T19:59:18Z",
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        witness_completed_at="2027-01-01T00:00:18Z",
        completed_at="2027-01-01T00:00:19Z",
    )
    return receipt


def final_document(
    receipt: Any,
    store: FileSystemArtifactStore,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            store.get(receipt.final_manifest_ref.artifact_id).text
        ),
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    adjudication_receipt: Any,
    credential_evaluated_at: str = "2026-08-03T19:59:14Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:59:15Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:59:16Z",
    checkpoint_reverified_at: str = "2026-08-03T19:59:17Z",
    canonical_witness_evaluated_at: str = "2026-08-03T19:59:18Z",
    delegated_checkpoint_verified_at: str = "2026-08-03T19:59:19Z",
    revocation_evaluated_at: str = "2026-08-04T00:00:01Z",
    revocation_completed_at: str = "2026-08-04T00:00:33Z",
    checkpoint_completed_at: str = "2026-08-04T00:00:34Z",
    witness_completed_at: str = "2026-08-04T00:00:35Z",
    adjudication_completed_at: str = "2026-08-04T00:00:36Z",
    completed_at: str = "2026-08-04T00:00:37Z",
):
    prepared = credential_fx.prepare_credential_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = Runner(artifact_store=store)
    stub = StubAdjudicationRunner(adjudication_receipt)
    cast(Any, runner)._runner = stub
    adjudication_fx = credential_fx.adjudication_fx
    witness_fx = pr51_fx.witness_fx
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        adjudication_corpus=prepared[3],
        conflict_adjudicator_registry=(
            adjudication_fx.conflict_adjudicator_registry()
        ),
        credential_issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        credentials=(credential_fx.credential(),),
        conflict_adjudication_policy=(
            adjudication_fx.conflict_adjudication_policy()
        ),
        conflict_adjudication=adjudication_fx.conflict_adjudication(),
        experiment_run_id=run_id,
        credential_evaluated_at=credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        conflict_adjudication_evaluated_at=(
            conflict_adjudication_evaluated_at
        ),
        checkpoint_reverified_at=checkpoint_reverified_at,
        canonical_witness_evaluated_at=canonical_witness_evaluated_at,
        delegated_checkpoint_verified_at=delegated_checkpoint_verified_at,
        current_revocation_evaluated_at=revocation_evaluated_at,
        revocation_completed_at=revocation_completed_at,
        checkpoint_completed_at=checkpoint_completed_at,
        witness_completed_at=witness_completed_at,
        adjudication_completed_at=adjudication_completed_at,
        completed_at=completed_at,
        witness_predecessor=prepared[4],
        checkpoint_predecessor=prepared[5],
        current_revocation_corpus=prepared[6],
        current_checkpoint_policy=(
            witness_fx.checkpoint_fx.checkpoint_policy()
        ),
        current_checkpoint_log=witness_fx.checkpoint_fx.checkpoint_log(),
        current_checkpoints=(witness_fx.checkpoint_fx.checkpoint(),),
        current_revocation_ledger=(
            witness_fx.checkpoint_fx.revocation_fx.revocation_ledger()
        ),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        conflict_witness_attestations=(
            adjudication_fx.conflict_attestations()
        ),
        canonical_witness_attestations=witness_fx.witness_attestations(),
    )
    return receipt, store, stub, prepared


def test_active_credential_delegates_exact_pr51(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudicator-credential-active"
    adjudication_receipt = active_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
    )
    assert receipt.status is RunnerStatus.VERIFIED
    credential_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_outcome"
    )
    assert (
        getattr(receipt, credential_field)
        is CredentialDecisionOutcome.EXECUTE
    )
    conflict_field = (
        "conflicting_current_revocation_conflict_adjudicator_checkpoint_"
        "witness_outcome"
    )
    assert (
        getattr(receipt, conflict_field)
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_resolution_status
        is WitnessConflictResolutionStatus.RESOLVED
    )
    adjudication_field = (
        "current_revocation_conflict_adjudicator_checkpoint_"
        "conflict_adjudication_outcome"
    )
    assert (
        getattr(receipt, adjudication_field)
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.adjudication_receipt is adjudication_receipt
    assert receipt.verified_checks == VERIFIED_CHECKS
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_expired_credential_stops_before_pr51(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudicator-credential-expired"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=None,
        credential_evaluated_at="2027-08-03T19:59:12Z",
        conflict_witness_evaluated_at="2027-08-03T19:59:13Z",
        conflict_adjudication_evaluated_at="2027-08-03T19:59:14Z",
        checkpoint_reverified_at="2027-08-03T19:59:15Z",
        canonical_witness_evaluated_at="2027-08-03T19:59:16Z",
        delegated_checkpoint_verified_at="2027-08-03T19:59:17Z",
        revocation_evaluated_at="2027-08-03T19:59:18Z",
        revocation_completed_at="2027-08-03T19:59:19Z",
        checkpoint_completed_at="2027-08-03T19:59:20Z",
        witness_completed_at="2027-08-03T19:59:21Z",
        adjudication_completed_at="2027-08-03T19:59:22Z",
        completed_at="2027-08-03T19:59:23Z",
    )
    credential_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_outcome"
    )
    assert (
        getattr(receipt, credential_field)
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert all(
        getattr(receipt, name) is None
        for name in ADJUDICATION_OUTCOME_FIELDS
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudication_receipt is None
    assert not stub.calls
    pr51_final = (
        f"{run_id}:current-revocation-checkpoint-witness-conflict-"
        "adjudicator-credential-revocation-checkpoint-witness-"
        "conflict-adjudication-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr51_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_credential_execution_preserves_later_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudicator-credential-later-abstention"
    adjudication_receipt = later_abstaining_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        witness_completed_at="2027-01-01T00:00:18Z",
        adjudication_completed_at="2027-01-01T00:00:19Z",
        completed_at="2027-01-01T00:00:20Z",
    )
    credential_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_outcome"
    )
    assert (
        getattr(receipt, credential_field)
        is CredentialDecisionOutcome.EXECUTE
    )
    adjudication_field = (
        "current_revocation_conflict_adjudicator_checkpoint_"
        "conflict_adjudication_outcome"
    )
    assert (
        getattr(receipt, adjudication_field)
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudication_receipt is adjudication_receipt
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_conflict_before_credential_evaluation_fails_preflight(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudicator-credential-early"
    adjudication_receipt = active_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    with pytest.raises(RunnerError) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            adjudication_receipt=adjudication_receipt,
            credential_evaluated_at="2026-08-03T19:59:16Z",
            conflict_witness_evaluated_at="2026-08-03T19:59:15Z",
        )
    assert captured.value.stage is RunnerStage.PREFLIGHT
