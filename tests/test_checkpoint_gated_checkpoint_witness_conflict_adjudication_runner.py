from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_gated_checkpoint_witness_conflict_adjudication_runner import (
    CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS,
    CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner,
    CheckpointWitnessConflictRevocationCheckpointExperimentError,
    CheckpointWitnessConflictRevocationCheckpointRunnerStage,
    CheckpointWitnessConflictRevocationCheckpointRunnerStatus,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

current_checkpoint_fx = import_module(
    "test_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints"
)
current_revocation_fx = current_checkpoint_fx.lower_fx
credential_fx = current_revocation_fx.credential_fx
credential_runner_fx = current_revocation_fx.credential_runner_fx
conflict_fx = current_revocation_fx.conflict_fx
witness_fx = current_revocation_fx.witness_fx
inherited_checkpoint_fx = current_revocation_fx.checkpoint_fx
lower_fx = current_revocation_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "checkpoint-gated-checkpoint-witness-conflict-revocation-final.schema.json"
)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    current_checkpoint_verified_at: str = "2026-08-03T19:57:45Z",
    current_revocation_evaluated_at: str = "2026-08-03T19:57:46Z",
    current_credential_evaluated_at: str = "2026-08-03T19:57:47Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:57:48Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:57:49Z",
    checkpoint_verified_at: str = "2026-08-03T19:57:50Z",
    predecessor_witness_evaluated_at: str = "2026-08-03T19:57:51Z",
    inherited_witness_evaluated_at: str = "2026-08-03T19:57:51Z",
    inherited_revocation_evaluated_at: str = "2026-08-03T19:57:52Z",
    inherited_credential_evaluated_at: str = "2026-08-03T19:57:57Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:58:02Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:12Z",
    inherited_credential_completed_at: str = "2026-08-03T19:58:27Z",
    inherited_revocation_completed_at: str = "2026-08-03T19:58:42Z",
    checkpoint_completed_at: str = "2026-08-03T19:58:57Z",
    prior_completed_at: str = "2026-08-03T19:59:12Z",
    current_revocation_completed_at: str = "2026-08-03T19:59:27Z",
    completed_at: str = "2026-08-03T19:59:42Z",
):
    prepared = current_checkpoint_fx.prepare_checkpoint_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        current_revocation_corpus=prepared[3],
        credential_corpus=prepared[4],
        adjudication_corpus=prepared[5],
        witness_predecessor=prepared[6],
        checkpoint_corpus=prepared[7],
        revocation_corpus=prepared[8],
        inherited_credential_corpus=prepared[9],
        inherited_adjudication_corpus=prepared[10],
        current_checkpoint_policy=current_checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=current_checkpoint_fx.checkpoint_log(),
        current_checkpoints=(current_checkpoint_fx.checkpoint(),),
        checkpoint_policy=inherited_checkpoint_fx.checkpoint_policy(),
        checkpoint_log=inherited_checkpoint_fx.checkpoint_log(),
        checkpoints=(inherited_checkpoint_fx.checkpoint(),),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        conflict_witness_attestations=conflict_fx.conflict_attestations(),
        predecessor_witness_attestations=witness_fx.witness_attestations(),
        conflict_adjudicator_registry=conflict_fx.conflict_adjudicator_registry(),
        conflict_adjudication_policy=conflict_fx.conflict_adjudication_policy(),
        conflict_adjudication=conflict_fx.conflict_adjudication(),
        current_issuer_registry=credential_fx.issuer_registry(),
        current_credential_policy=credential_fx.credential_policy(),
        current_revocation_policy=current_revocation_fx.revocation_fx.revocation_policy(),
        current_revocation_ledger=current_revocation_fx.revocation_fx.revocation_ledger(),
        current_revocation_events=(
            current_revocation_fx.revocation_fx.suspension_event(),
        ),
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
        inherited_issuer_registry=(
            lower_fx.credential_runner_fx.credential_fx.issuer_registry()
        ),
        inherited_credential_policy=(
            lower_fx.credential_runner_fx.credential_fx.credential_policy()
        ),
        revocation_policy=lower_fx.revocation_fx.revocation_policy(),
        revocation_ledger=lower_fx.revocation_fx.revocation_ledger(),
        revocation_events=(lower_fx.revocation_fx.suspension_event(),),
        inherited_witness_receipt=prepared[11],
        checkpoint_executor=None,
        experiment_run_id=run_id,
        current_checkpoint_verified_at=current_checkpoint_verified_at,
        current_revocation_evaluated_at=current_revocation_evaluated_at,
        current_credential_evaluated_at=current_credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        conflict_adjudication_evaluated_at=conflict_adjudication_evaluated_at,
        checkpoint_verified_at=checkpoint_verified_at,
        predecessor_witness_evaluated_at=predecessor_witness_evaluated_at,
        inherited_witness_evaluated_at=inherited_witness_evaluated_at,
        revocation_evaluated_at=inherited_revocation_evaluated_at,
        inherited_credential_evaluated_at=inherited_credential_evaluated_at,
        inherited_adjudication_evaluated_at=(
            inherited_adjudication_evaluated_at
        ),
        inherited_adjudication_completed_at=(
            inherited_adjudication_completed_at
        ),
        inherited_credential_completed_at=inherited_credential_completed_at,
        revocation_completed_at=inherited_revocation_completed_at,
        checkpoint_completed_at=checkpoint_completed_at,
        prior_completed_at=prior_completed_at,
        current_revocation_completed_at=current_revocation_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_verified_checkpoint_delegates_exact_pr38_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-checkpoint-active")
    expected = CheckpointWitnessConflictRevocationCheckpointRunnerStatus.VERIFIED
    assert receipt.status is expected
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.predecessor_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.inherited_revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.inherited_credential_outcome is CredentialDecisionOutcome.EXECUTE
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
    assert receipt.revocation_receipt.experiment_run_id == receipt.experiment_run_id
    assert receipt.checkpoint_head_ref == current_checkpoint_fx.checkpoint().reference()
    assert receipt.verified_checks == (
        CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
    )
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_verified_checkpoint_preserves_current_suspension(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-checkpoint-current-suspension",
        current_revocation_evaluated_at="2027-01-01T00:00:00Z",
        current_credential_evaluated_at="2027-01-01T00:00:01Z",
        conflict_witness_evaluated_at="2027-01-01T00:00:02Z",
        prior_completed_at="2027-01-01T00:00:03Z",
        current_revocation_completed_at="2027-01-01T00:00:04Z",
        completed_at="2027-01-01T00:00:05Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.conflict_adjudication_outcome is None
    assert receipt.predecessor_witness_outcome is None
    assert receipt.inherited_revocation_outcome is None
    assert receipt.inherited_credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_head_ref == current_checkpoint_fx.checkpoint().reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_verified_checkpoint_preserves_inherited_suspension(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-checkpoint-inherited-suspension",
        inherited_revocation_evaluated_at="2027-01-01T00:00:00Z",
        inherited_credential_evaluated_at="2027-01-01T00:00:01Z",
        inherited_adjudication_evaluated_at="2027-01-01T00:00:02Z",
        inherited_adjudication_completed_at="2027-01-01T00:00:03Z",
        inherited_credential_completed_at="2027-01-01T00:00:04Z",
        inherited_revocation_completed_at="2027-01-01T00:00:05Z",
        checkpoint_completed_at="2027-01-01T00:00:06Z",
        prior_completed_at="2027-01-01T00:00:07Z",
        current_revocation_completed_at="2027-01-01T00:00:08Z",
        completed_at="2027-01-01T00:00:09Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.predecessor_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.inherited_revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.inherited_credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_checkpoint_after_revocation_fails_preflight(tmp_path: Path) -> None:
    with pytest.raises(
        CheckpointWitnessConflictRevocationCheckpointExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id="checkpoint-after-current-revocation",
            current_checkpoint_verified_at="2026-08-03T19:57:47Z",
            current_revocation_evaluated_at="2026-08-03T19:57:46Z",
        )
    expected = CheckpointWitnessConflictRevocationCheckpointRunnerStage.PREFLIGHT
    assert captured.value.stage is expected
