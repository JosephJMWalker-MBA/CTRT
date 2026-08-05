from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import test_adjudicated_current_revocation_checkpoint_witness_runner as pr46_fx
import test_current_revocation_checkpoint_witness_conflict_adjudicator_credential as credential_fx
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.credentialed_current_revocation_checkpoint_witness_conflict_runner import (
    CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
    CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError,
    CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner,
    CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage,
    CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "credentialed-current-revocation-checkpoint-witness-conflict-final.schema.json"
)


class StubAdjudicationRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_adjudication_receipt(tmp_path: Path, *, run_id: str):
    witness_receipt = pr46_fx.active_witness_receipt(tmp_path, run_id=run_id)
    receipt, _, _, _ = pr46_fx.execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
    )
    return receipt


def suspended_adjudication_receipt(tmp_path: Path, *, run_id: str):
    witness_receipt = pr46_fx.suspended_witness_receipt(tmp_path, run_id=run_id)
    receipt, _, _, _ = pr46_fx.execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
        current_checkpoint_verified_at="2027-01-01T00:00:00Z",
        revocation_evaluated_at="2027-01-01T00:00:01Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        current_checkpoint_completed_at="2027-01-01T00:00:06Z",
        prior_completed_at="2027-01-01T00:00:08Z",
        completed_at="2027-01-01T00:00:09Z",
    )
    return receipt


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    adjudication_receipt: Any,
    credential_evaluated_at: str = "2026-08-03T19:58:42Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:58:43Z",
    prior_completed_at: str = "2026-08-04T00:00:30Z",
    completed_at: str = "2026-08-04T00:00:31Z",
):
    prepared = credential_fx.prepare_credential_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner(
        artifact_store=store
    )
    stub = StubAdjudicationRunner(adjudication_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        adjudication_corpus=prepared[3],
        conflict_adjudicator_registry=(
            credential_fx.adjudication_fx.conflict_adjudicator_registry()
        ),
        credential_issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        credentials=(credential_fx.credential(),),
        conflict_adjudication=(
            credential_fx.adjudication_fx.conflict_adjudication()
        ),
        experiment_run_id=run_id,
        credential_evaluated_at=credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_active_credential_delegates_exact_pr46(tmp_path: Path) -> None:
    run_id = "current-revocation-conflict-credential-active"
    adjudication_receipt = active_adjudication_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
    )
    assert (
        receipt.status
        is CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus.VERIFIED
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_checkpoint_resolution_status
        is WitnessConflictResolutionStatus.RESOLVED
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.adjudication_receipt is adjudication_receipt
    assert receipt.verified_checks == (
        CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
    )
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_expired_credential_stops_before_pr46(tmp_path: Path) -> None:
    run_id = "current-revocation-conflict-credential-expired"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=None,
        credential_evaluated_at="2027-08-03T19:58:40Z",
        conflict_witness_evaluated_at="2027-08-03T19:58:41Z",
        prior_completed_at="2027-08-03T20:00:00Z",
        completed_at="2027-08-03T20:00:01Z",
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.current_revocation_checkpoint_resolution_status is None
    assert receipt.current_conflict_adjudicator_revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudication_receipt is None
    assert not stub.calls
    pr46_final = (
        f"{run_id}:current-checkpoint-witness-conflict-adjudicator-credential-"
        "revocation-checkpoint-witness-conflict-adjudication-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr46_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_credential_execution_preserves_later_revocation_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-conflict-credential-later-suspension"
    adjudication_receipt = suspended_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
        prior_completed_at="2027-01-01T00:00:09Z",
        completed_at="2027-01-01T00:00:10Z",
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_credential_after_delegated_witness_fails_preflight(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-conflict-credential-late"
    with pytest.raises(
        CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            adjudication_receipt=None,
            credential_evaluated_at="2026-08-03T19:58:44Z",
            conflict_witness_evaluated_at="2026-08-03T19:58:43Z",
        )
    assert (
        captured.value.stage
        is CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.PREFLIGHT
    )
