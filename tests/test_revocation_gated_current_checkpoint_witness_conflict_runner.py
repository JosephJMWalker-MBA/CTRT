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
from ctrt.revocation_gated_current_checkpoint_witness_conflict_runner import (
    CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationExperimentError,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationRunnerStage,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus,
    RevocationGatedCurrentCheckpointWitnessConflictExperimentRunner,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

revocation_fx = import_module(
    "test_current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_ledger"
)
credential_runner_fx = import_module(
    "test_credentialed_current_checkpoint_witness_conflict_runner"
)
credential_fx = revocation_fx.credential_fx
current_fx = credential_runner_fx.current_fx
current_witness_fx = credential_runner_fx.current_witness_fx
current_checkpoint_fx = credential_runner_fx.current_checkpoint_fx
current_revocation_fx = credential_runner_fx.current_revocation_fx
current_credential_fx = credential_runner_fx.current_credential_fx
lower_conflict_fx = credential_runner_fx.lower_conflict_fx
lower_witness_fx = credential_runner_fx.lower_witness_fx
inherited_checkpoint_fx = credential_runner_fx.inherited_checkpoint_fx
lower_fx = credential_runner_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-current-checkpoint-witness-conflict-final.schema.json"
)


def prepare_revocation_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    prepared = credential_fx.prepare_credential_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    credential_corpus = prepared[2]
    selected = revocation_fx.revocation_corpus(predecessor=credential_corpus)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist = (
        revocation_fx.persist_current_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus
    )
    persist(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=credential_corpus,
        adjudicator_registry=current_fx.conflict_adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        ledger=revocation_fx.revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=current_fx.conflict_adjudication(),
        events=(revocation_fx.suspension_event(),),
        evaluated_at="2026-08-03T19:58:16Z",
    )
    return (store, plan, selected, *prepared[2:])


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    current_conflict_adjudicator_revocation_evaluated_at: str = (
        "2026-08-03T19:58:16Z"
    ),
    conflict_credential_evaluated_at: str = "2026-08-03T19:58:17Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:58:18Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:58:19Z",
    current_checkpoint_verified_at: str = "2026-08-03T19:58:20Z",
    current_witness_evaluated_at: str = "2026-08-03T19:58:21Z",
    current_revocation_evaluated_at: str = "2026-08-03T19:58:22Z",
    current_credential_evaluated_at: str = "2026-08-03T19:58:23Z",
    lower_conflict_witness_evaluated_at: str = "2026-08-03T19:58:24Z",
    lower_conflict_adjudication_evaluated_at: str = "2026-08-03T19:58:25Z",
    checkpoint_verified_at: str = "2026-08-03T19:58:26Z",
    lower_predecessor_witness_evaluated_at: str = "2026-08-03T19:58:27Z",
    inherited_witness_evaluated_at: str = "2026-08-03T19:58:27Z",
    inherited_revocation_evaluated_at: str = "2026-08-03T19:58:28Z",
    inherited_credential_evaluated_at: str = "2026-08-03T19:58:33Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:58:38Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:48Z",
    inherited_credential_completed_at: str = "2026-08-03T19:59:03Z",
    inherited_revocation_completed_at: str = "2026-08-03T19:59:18Z",
    checkpoint_completed_at: str = "2026-08-03T19:59:33Z",
    lower_completed_at: str = "2026-08-03T19:59:48Z",
    current_revocation_completed_at: str = "2026-08-03T20:00:03Z",
    current_checkpoint_completed_at: str = "2026-08-03T20:00:18Z",
    prior_completed_at: str = "2026-08-03T20:00:33Z",
    completed_at: str = "2026-08-03T20:00:48Z",
):
    prepared = prepare_revocation_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = RevocationGatedCurrentCheckpointWitnessConflictExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        credential_corpus=prepared[3],
        conflict_adjudicator_registry=current_fx.conflict_adjudicator_registry(),
        conflict_credential_issuer_registry=credential_fx.issuer_registry(),
        conflict_credential_policy=credential_fx.credential_policy(),
        conflict_credentials=(credential_fx.credential(),),
        conflict_adjudication=current_fx.conflict_adjudication(),
        current_revocation_policy=revocation_fx.revocation_policy(),
        current_revocation_ledger=revocation_fx.revocation_ledger(),
        current_revocation_events=(revocation_fx.suspension_event(),),
        experiment_run_id=run_id,
        current_conflict_adjudicator_revocation_evaluated_at=(
            current_conflict_adjudicator_revocation_evaluated_at
        ),
        conflict_credential_evaluated_at=conflict_credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
        adjudication_corpus=prepared[4],
        witness_predecessor=prepared[5],
        current_checkpoint_corpus=prepared[6],
        current_checkpoint_policy=current_checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=current_checkpoint_fx.checkpoint_log(),
        current_checkpoints=(current_checkpoint_fx.checkpoint(),),
        witness_registry=current_witness_fx.witness_registry(),
        witness_policy=current_witness_fx.witness_policy(),
        conflict_witness_attestations=current_fx.conflict_attestations(),
        canonical_witness_attestations=current_witness_fx.witness_attestations(),
        conflict_adjudication_policy=current_fx.conflict_adjudication_policy(),
        current_revocation_corpus=prepared[7],
        credential_corpus=prepared[8],
        lower_adjudication_corpus=prepared[9],
        lower_witness_predecessor=prepared[10],
        inherited_checkpoint_corpus=prepared[11],
        inherited_revocation_corpus=prepared[12],
        inherited_credential_corpus=prepared[13],
        inherited_adjudication_corpus=prepared[14],
        inherited_checkpoint_policy=inherited_checkpoint_fx.checkpoint_policy(),
        inherited_checkpoint_log=inherited_checkpoint_fx.checkpoint_log(),
        inherited_checkpoints=(inherited_checkpoint_fx.checkpoint(),),
        lower_witness_registry=lower_witness_fx.witness_registry(),
        lower_witness_policy=lower_witness_fx.witness_policy(),
        lower_conflict_witness_attestations=(
            lower_conflict_fx.conflict_attestations()
        ),
        lower_predecessor_witness_attestations=(
            lower_witness_fx.witness_attestations()
        ),
        lower_conflict_adjudicator_registry=(
            lower_conflict_fx.conflict_adjudicator_registry()
        ),
        lower_conflict_adjudication_policy=(
            lower_conflict_fx.conflict_adjudication_policy()
        ),
        lower_conflict_adjudication=lower_conflict_fx.conflict_adjudication(),
        current_issuer_registry=current_credential_fx.issuer_registry(),
        current_credential_policy=current_credential_fx.credential_policy(),
        current_revocation_policy=(
            current_revocation_fx.revocation_fx.revocation_policy()
        ),
        current_revocation_ledger=(
            current_revocation_fx.revocation_fx.revocation_ledger()
        ),
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
        inherited_witness_receipt=prepared[15],
        checkpoint_executor=None,
        conflict_adjudication_evaluated_at=(
            conflict_adjudication_evaluated_at
        ),
        current_checkpoint_verified_at=current_checkpoint_verified_at,
        current_witness_evaluated_at=current_witness_evaluated_at,
        current_revocation_evaluated_at=current_revocation_evaluated_at,
        current_credential_evaluated_at=current_credential_evaluated_at,
        lower_conflict_witness_evaluated_at=(
            lower_conflict_witness_evaluated_at
        ),
        lower_conflict_adjudication_evaluated_at=(
            lower_conflict_adjudication_evaluated_at
        ),
        checkpoint_verified_at=checkpoint_verified_at,
        lower_predecessor_witness_evaluated_at=(
            lower_predecessor_witness_evaluated_at
        ),
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
        lower_completed_at=lower_completed_at,
        current_revocation_completed_at=current_revocation_completed_at,
        current_checkpoint_completed_at=current_checkpoint_completed_at,
    )
    return receipt, store


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_active_revocation_status_delegates_exact_pr42(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-conflict-revocation-active")
    expected_status = (
        CurrentCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus.VERIFIED
    )
    assert receipt.status is expected_status
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.conflicting_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.current_resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.current_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.resolved_current_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.current_revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.current_credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.lower_checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.lower_resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.lower_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.lower_predecessor_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
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
    assert receipt.credential_receipt.experiment_run_id == receipt.experiment_run_id
    assert receipt.verified_checks == (
        CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
    )
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_effective_suspension_stops_before_pr42(tmp_path: Path) -> None:
    run_id = "current-conflict-revocation-suspended"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        current_conflict_adjudicator_revocation_evaluated_at=(
            "2027-01-01T00:00:00Z"
        ),
        conflict_credential_evaluated_at="2027-01-01T00:00:01Z",
        conflict_witness_evaluated_at="2027-01-01T00:00:02Z",
        prior_completed_at="2027-01-01T00:00:03Z",
        completed_at="2027-01-01T00:00:04Z",
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.current_conflict_adjudicator_credential_outcome is None
    assert receipt.conflicting_witness_outcome is None
    assert receipt.current_resolution_status is None
    assert receipt.current_conflict_adjudication_outcome is None
    assert receipt.resolved_current_witness_outcome is None
    assert receipt.current_revocation_outcome is None
    assert receipt.current_credential_outcome is None
    assert receipt.lower_checkpoint_witness_outcome is None
    assert receipt.lower_resolution_status is None
    assert receipt.lower_conflict_adjudication_outcome is None
    assert receipt.lower_predecessor_witness_outcome is None
    assert receipt.inherited_revocation_outcome is None
    assert receipt.inherited_credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credential_receipt is None
    pr42_decision_id = (
        f"{run_id}:current-checkpoint-witness-conflict-adjudicator-"
        "credential-decision"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr42_decision_id)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_new_revocation_execute_survives_later_current_suspension(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-conflict-revocation-later-suspension",
        current_revocation_evaluated_at="2027-01-01T00:00:00Z",
        current_credential_evaluated_at="2027-01-01T00:00:01Z",
        lower_conflict_witness_evaluated_at="2027-01-01T00:00:02Z",
        lower_conflict_adjudication_evaluated_at="2027-01-01T00:00:03Z",
        checkpoint_verified_at="2027-01-01T00:00:04Z",
        lower_predecessor_witness_evaluated_at="2027-01-01T00:00:05Z",
        inherited_witness_evaluated_at="2027-01-01T00:00:05Z",
        inherited_revocation_evaluated_at="2027-01-01T00:00:06Z",
        inherited_credential_evaluated_at="2027-01-01T00:00:07Z",
        inherited_adjudication_evaluated_at="2027-01-01T00:00:08Z",
        inherited_adjudication_completed_at="2027-01-01T00:00:09Z",
        inherited_credential_completed_at="2027-01-01T00:00:10Z",
        inherited_revocation_completed_at="2027-01-01T00:00:11Z",
        checkpoint_completed_at="2027-01-01T00:00:12Z",
        lower_completed_at="2027-01-01T00:00:13Z",
        current_revocation_completed_at="2027-01-01T00:00:14Z",
        current_checkpoint_completed_at="2027-01-01T00:00:15Z",
        prior_completed_at="2027-01-01T00:00:16Z",
        completed_at="2027-01-01T00:00:17Z",
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.conflicting_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.current_resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert (
        receipt.current_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.resolved_current_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.current_revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.current_credential_outcome is None
    assert receipt.lower_checkpoint_witness_outcome is None
    assert receipt.lower_resolution_status is None
    assert receipt.lower_conflict_adjudication_outcome is None
    assert receipt.lower_predecessor_witness_outcome is None
    assert receipt.inherited_revocation_outcome is None
    assert receipt.inherited_credential_outcome is None
    assert receipt.inherited_checkpoint_witness_outcome is None
    assert receipt.inherited_resolution_status is None
    assert receipt.inherited_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credential_receipt is not None
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_credential_before_revocation_fails_preflight(tmp_path: Path) -> None:
    with pytest.raises(
        CurrentCheckpointWitnessConflictAdjudicatorRevocationExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id="current-conflict-revocation-after-credential",
            current_conflict_adjudicator_revocation_evaluated_at=(
                "2026-08-03T19:58:18Z"
            ),
            conflict_credential_evaluated_at="2026-08-03T19:58:17Z",
        )
    expected = CurrentCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.PREFLIGHT
    assert captured.value.stage is expected
