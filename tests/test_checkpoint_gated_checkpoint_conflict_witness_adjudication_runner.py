from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_gated_checkpoint_conflict_witness_adjudication_runner import (
    CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS,
    CheckpointConflictWitnessRevocationCheckpointExperimentError,
    CheckpointConflictWitnessRevocationCheckpointRunnerStage,
    CheckpointConflictWitnessRevocationCheckpointRunnerStatus,
    CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

checkpoint_fx = import_module(
    "test_checkpoint_conflict_witness_adjudicator_credential_"
    "revocation_checkpoints"
)
lower_fx = checkpoint_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "checkpoint-gated-checkpoint-conflict-witness-revocation-final.schema.json"
)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    checkpoint_verified_at: str = "2026-08-03T19:54:55Z",
    revocation_evaluated_at: str = "2026-08-03T19:54:56Z",
    credential_evaluated_at: str = "2026-08-03T19:55:00Z",
    adjudication_evaluated_at: str = "2026-08-03T19:55:30Z",
    adjudication_completed_at: str = "2026-08-03T19:56:00Z",
    credential_completed_at: str = "2026-08-03T19:56:30Z",
    revocation_completed_at: str = "2026-08-03T19:56:45Z",
    completed_at: str = "2026-08-03T19:57:00Z",
):
    prepared = checkpoint_fx.prepare_checkpoint_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    plan = prepared[1]
    corpus = prepared[2]
    revocation_corpus = prepared[3]
    credential_corpus = prepared[4]
    adjudication_corpus = prepared[5]
    witness_receipt = prepared[6]
    runner = CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=plan,
        corpus=corpus,
        revocation_corpus=revocation_corpus,
        credential_corpus=credential_corpus,
        adjudication_corpus=adjudication_corpus,
        checkpoint_policy=checkpoint_fx.checkpoint_policy(),
        checkpoint_log=checkpoint_fx.checkpoint_log(),
        checkpoints=(checkpoint_fx.checkpoint(),),
        witness_registry=lower_fx.credential_runner_fx.witness_fx.witness_registry(),
        witness_policy=lower_fx.credential_runner_fx.witness_fx.witness_policy(),
        witness_attestations=(
            lower_fx.credential_runner_fx.witness_fx.witness_attestations()
        ),
        head_checkpoint=lower_fx.credential_runner_fx.checkpoint(),
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
        witness_receipt=witness_receipt,
        checkpoint_executor=None,
        experiment_run_id=run_id,
        checkpoint_verified_at=checkpoint_verified_at,
        witness_evaluated_at="2026-08-03T19:53:30Z",
        revocation_evaluated_at=revocation_evaluated_at,
        credential_evaluated_at=credential_evaluated_at,
        adjudication_evaluated_at=adjudication_evaluated_at,
        adjudication_completed_at=adjudication_completed_at,
        credential_completed_at=credential_completed_at,
        revocation_completed_at=revocation_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def test_valid_checkpoint_delegates_exact_pr33_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="checkpoint-gated-revocation-execute")
    expected_status = (
        CheckpointConflictWitnessRevocationCheckpointRunnerStatus.VERIFIED
    )
    assert receipt.status is expected_status
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.revocation_receipt.credential_receipt is not None
    assert (
        receipt.verified_checks
        == CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
    )
    report = store.get(receipt.checkpoint_verification_ref.artifact_id)
    assert report.artifact_hash == receipt.checkpoint_verification_ref.artifact_hash
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_valid_checkpoint_preserves_later_revocation_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="checkpoint-gated-revocation-suspended",
        revocation_evaluated_at="2027-01-01T00:00:00Z",
        credential_evaluated_at="2027-01-01T00:00:01Z",
        adjudication_evaluated_at="2027-01-01T00:00:02Z",
        adjudication_completed_at="2027-01-01T00:00:03Z",
        credential_completed_at="2027-01-01T00:00:04Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        completed_at="2027-01-01T00:00:06Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.revocation_receipt.credential_receipt is None
    report = store.get(receipt.checkpoint_verification_ref.artifact_id)
    assert report.artifact_hash == receipt.checkpoint_verification_ref.artifact_hash
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_checkpoint_after_revocation_stops_pr33_before_decision(
    tmp_path: Path,
) -> None:
    run_id = "checkpoint-gated-revocation-late"
    with pytest.raises(
        CheckpointConflictWitnessRevocationCheckpointExperimentError,
    ) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            checkpoint_verified_at="2026-08-03T19:54:57Z",
        )
    assert (
        captured.value.stage
        is CheckpointConflictWitnessRevocationCheckpointRunnerStage.PREFLIGHT
    )
    prepared = checkpoint_fx.prepare_checkpoint_store(
        tmp_path / "absence-check",
        run_id=f"{run_id}-absence",
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    decision_id = (
        f"{run_id}:checkpoint-conflict-revocation-"
        "witness-conflict-adjudicator-credential-revocation-decision"
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(decision_id)
