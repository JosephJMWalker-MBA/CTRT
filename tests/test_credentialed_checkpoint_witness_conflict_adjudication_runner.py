from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.credentialed_checkpoint_witness_conflict_adjudication_runner import (
    CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
    CredentialedCheckpointWitnessConflictExperimentError,
    CredentialedCheckpointWitnessConflictExperimentRunner,
    CredentialedCheckpointWitnessConflictRunnerStage,
    CredentialedCheckpointWitnessConflictRunnerStatus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

credential_fx = import_module(
    "test_checkpoint_witness_conflict_adjudicator_credential"
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
    "credentialed-checkpoint-witness-conflict-adjudication-final.schema.json"
)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    current_credential_evaluated_at: str = "2026-08-03T19:57:35Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:57:36Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:57:37Z",
    checkpoint_verified_at: str = "2026-08-03T19:57:38Z",
    predecessor_witness_evaluated_at: str = "2026-08-03T19:57:39Z",
    revocation_evaluated_at: str = "2026-08-03T19:57:40Z",
    inherited_credential_evaluated_at: str = "2026-08-03T19:57:45Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:57:50Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:00Z",
    inherited_credential_completed_at: str = "2026-08-03T19:58:15Z",
    revocation_completed_at: str = "2026-08-03T19:58:30Z",
    checkpoint_completed_at: str = "2026-08-03T19:58:45Z",
    prior_completed_at: str = "2026-08-03T19:59:00Z",
    completed_at: str = "2026-08-03T19:59:15Z",
):
    prepared = credential_fx.prepare_credential_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = CredentialedCheckpointWitnessConflictExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        adjudication_corpus=prepared[3],
        witness_predecessor=prepared[4],
        checkpoint_corpus=prepared[5],
        revocation_corpus=prepared[6],
        inherited_credential_corpus=prepared[7],
        inherited_adjudication_corpus=prepared[8],
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
        conflict_adjudication=conflict_fx.conflict_adjudication(),
        current_issuer_registry=credential_fx.issuer_registry(),
        current_credential_policy=credential_fx.credential_policy(),
        current_credentials=(credential_fx.credential(),),
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
        inherited_witness_receipt=prepared[9],
        checkpoint_executor=None,
        experiment_run_id=run_id,
        current_credential_evaluated_at=current_credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        conflict_adjudication_evaluated_at=(
            conflict_adjudication_evaluated_at
        ),
        checkpoint_verified_at=checkpoint_verified_at,
        predecessor_witness_evaluated_at=predecessor_witness_evaluated_at,
        inherited_witness_evaluated_at="2026-08-03T19:57:39Z",
        revocation_evaluated_at=revocation_evaluated_at,
        inherited_credential_evaluated_at=inherited_credential_evaluated_at,
        inherited_adjudication_evaluated_at=(
            inherited_adjudication_evaluated_at
        ),
        inherited_adjudication_completed_at=(
            inherited_adjudication_completed_at
        ),
        inherited_credential_completed_at=(
            inherited_credential_completed_at
        ),
        revocation_completed_at=revocation_completed_at,
        checkpoint_completed_at=checkpoint_completed_at,
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_active_credential_delegates_exact_pr36_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-credential-active")
    assert receipt.status is CredentialedCheckpointWitnessConflictRunnerStatus.VERIFIED
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.predecessor_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
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
    assert receipt.adjudication_receipt is not None
    assert receipt.verified_checks == (
        CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
    )
    decision = store.get(receipt.credential_decision_ref.artifact_id)
    assert decision.artifact_hash == receipt.credential_decision_ref.artifact_hash
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_expired_current_credential_abstains_before_pr36(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-credential-expired",
        current_credential_evaluated_at="2027-08-03T19:57:33Z",
        conflict_witness_evaluated_at="2027-08-03T19:57:34Z",
        prior_completed_at="2027-08-03T19:58:00Z",
        completed_at="2027-08-03T19:58:01Z",
    )
    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.conflict_adjudication_outcome is None
    assert receipt.predecessor_witness_outcome is None
    assert receipt.revocation_outcome is None
    assert receipt.inherited_credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudication_receipt is None
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_current_credential_execute_preserves_later_revocation_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-credential-later-suspension",
        revocation_evaluated_at="2027-01-01T00:00:00Z",
        inherited_credential_evaluated_at="2027-01-01T00:00:01Z",
        inherited_adjudication_evaluated_at="2027-01-01T00:00:02Z",
        inherited_adjudication_completed_at="2027-01-01T00:00:03Z",
        inherited_credential_completed_at="2027-01-01T00:00:04Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        checkpoint_completed_at="2027-01-01T00:00:06Z",
        prior_completed_at="2027-01-01T00:00:07Z",
        completed_at="2027-01-01T00:00:08Z",
    )
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.predecessor_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.inherited_credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudication_receipt is not None
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_current_credential_after_witness_evaluation_fails_preflight(
    tmp_path: Path,
) -> None:
    with pytest.raises(CredentialedCheckpointWitnessConflictExperimentError) as captured:
        execute(
            tmp_path,
            run_id="credential-after-witness",
            current_credential_evaluated_at="2026-08-03T19:57:37Z",
            conflict_witness_evaluated_at="2026-08-03T19:57:36Z",
        )
    assert captured.value.stage is CredentialedCheckpointWitnessConflictRunnerStage.PREFLIGHT
