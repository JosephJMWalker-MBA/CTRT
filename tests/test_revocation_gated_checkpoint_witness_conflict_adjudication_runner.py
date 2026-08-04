from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_checkpoint_witness_conflict_adjudication_runner import (
    CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS,
    CheckpointWitnessConflictRevocationExperimentError,
    CheckpointWitnessConflictRevocationRunnerStage,
    CheckpointWitnessConflictRevocationRunnerStatus,
    RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

revocation_fx = import_module(
    "test_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger"
)
credential_fx = import_module("test_checkpoint_witness_conflict_adjudicator_credential")
credential_runner_fx = import_module(
    "test_credentialed_checkpoint_witness_conflict_adjudication_runner"
)
conflict_fx = credential_runner_fx.conflict_fx
witness_fx = credential_runner_fx.witness_fx
checkpoint_fx = credential_runner_fx.checkpoint_fx
lower_fx = credential_runner_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-checkpoint-witness-conflict-adjudication-final.schema.json"
)


def prepare_revocation_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    prepared = credential_fx.prepare_credential_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = revocation_fx.revocation_corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    revocation_fx.persist_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=conflict_fx.conflict_adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        ledger=revocation_fx.revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=conflict_fx.conflict_adjudication(),
        events=(revocation_fx.suspension_event(),),
        evaluated_at="2026-08-03T19:57:39Z",
    )
    return (store, plan, selected, *prepared[2:])


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    current_revocation_evaluated_at: str = "2026-08-03T19:57:39Z",
    current_credential_evaluated_at: str = "2026-08-03T19:57:40Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:57:41Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:57:42Z",
    checkpoint_verified_at: str = "2026-08-03T19:57:43Z",
    predecessor_witness_evaluated_at: str = "2026-08-03T19:57:44Z",
    inherited_witness_evaluated_at: str = "2026-08-03T19:57:44Z",
    inherited_revocation_evaluated_at: str = "2026-08-03T19:57:45Z",
    inherited_credential_evaluated_at: str = "2026-08-03T19:57:50Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:57:55Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:05Z",
    inherited_credential_completed_at: str = "2026-08-03T19:58:20Z",
    inherited_revocation_completed_at: str = "2026-08-03T19:58:35Z",
    checkpoint_completed_at: str = "2026-08-03T19:58:50Z",
    prior_completed_at: str = "2026-08-03T19:59:05Z",
    completed_at: str = "2026-08-03T19:59:20Z",
):
    prepared = prepare_revocation_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        credential_corpus=prepared[3],
        adjudication_corpus=prepared[4],
        witness_predecessor=prepared[5],
        checkpoint_corpus=prepared[6],
        revocation_corpus=prepared[7],
        inherited_credential_corpus=prepared[8],
        inherited_adjudication_corpus=prepared[9],
        checkpoint_policy=checkpoint_fx.checkpoint_policy(),
        checkpoint_log=checkpoint_fx.checkpoint_log(),
        checkpoints=(checkpoint_fx.checkpoint(),),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        conflict_witness_attestations=conflict_fx.conflict_attestations(),
        predecessor_witness_attestations=witness_fx.witness_attestations(),
        conflict_adjudicator_registry=conflict_fx.conflict_adjudicator_registry(),
        conflict_adjudication_policy=conflict_fx.conflict_adjudication_policy(),
        conflict_adjudication=conflict_fx.conflict_adjudication(),
        current_issuer_registry=credential_fx.issuer_registry(),
        current_credential_policy=credential_fx.credential_policy(),
        current_revocation_policy=revocation_fx.revocation_policy(),
        current_revocation_ledger=revocation_fx.revocation_ledger(),
        current_revocation_events=(revocation_fx.suspension_event(),),
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
        inherited_witness_receipt=prepared[10],
        checkpoint_executor=None,
        experiment_run_id=run_id,
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
        inherited_credential_completed_at=(
            inherited_credential_completed_at
        ),
        revocation_completed_at=inherited_revocation_completed_at,
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


def test_active_revocation_delegates_exact_pr37_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-revocation-active")
    assert receipt.status is CheckpointWitnessConflictRevocationRunnerStatus.VERIFIED
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
    assert receipt.credential_receipt is not None
    assert receipt.verified_checks == (
        CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS
    )
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_effective_current_suspension_abstains_before_pr37(tmp_path: Path) -> None:
    run_id = "current-revocation-suspended"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        current_revocation_evaluated_at="2027-01-01T00:00:00Z",
        current_credential_evaluated_at="2027-01-01T00:00:01Z",
        conflict_witness_evaluated_at="2027-01-01T00:00:02Z",
        prior_completed_at="2027-01-01T00:00:03Z",
        completed_at="2027-01-01T00:00:04Z",
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
    assert receipt.credential_receipt is None
    credential_decision_id = (
        f"{run_id}:checkpoint-conflict-revocation-witness-conflict-adjudicator-"
        "credential-revocation-checkpoint-witness-conflict-adjudicator-"
        "credential-decision"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(credential_decision_id)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_current_revocation_execute_preserves_inherited_suspension(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-revocation-inherited-suspension",
        inherited_revocation_evaluated_at="2027-01-01T00:00:00Z",
        inherited_credential_evaluated_at="2027-01-01T00:00:01Z",
        inherited_adjudication_evaluated_at="2027-01-01T00:00:02Z",
        inherited_adjudication_completed_at="2027-01-01T00:00:03Z",
        inherited_credential_completed_at="2027-01-01T00:00:04Z",
        inherited_revocation_completed_at="2027-01-01T00:00:05Z",
        checkpoint_completed_at="2027-01-01T00:00:06Z",
        prior_completed_at="2027-01-01T00:00:07Z",
        completed_at="2027-01-01T00:00:08Z",
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
    assert receipt.credential_receipt is not None
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_current_revocation_after_credential_fails_preflight(tmp_path: Path) -> None:
    with pytest.raises(CheckpointWitnessConflictRevocationExperimentError) as captured:
        execute(
            tmp_path,
            run_id="revocation-after-credential",
            current_revocation_evaluated_at="2026-08-03T19:57:41Z",
            current_credential_evaluated_at="2026-08-03T19:57:40Z",
        )
    assert captured.value.stage is CheckpointWitnessConflictRevocationRunnerStage.PREFLIGHT
