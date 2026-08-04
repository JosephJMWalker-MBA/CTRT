from __future__ import annotations

import json
from copy import deepcopy
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
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_gated_current_checkpoint_runner import (
    CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
    CurrentCheckpointWitnessExperimentError,
    CurrentCheckpointWitnessRunnerStage,
    CurrentCheckpointWitnessRunnerStatus,
    WitnessGatedCurrentCheckpointExperimentRunner,
)

current_witness_fx = import_module(
    "test_checkpoint_witness_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness"
)
lower_runner_fx = import_module(
    "test_checkpoint_gated_checkpoint_witness_conflict_adjudication_runner"
)
current_checkpoint_fx = current_witness_fx.checkpoint_fx
current_revocation_fx = lower_runner_fx.current_revocation_fx
credential_fx = lower_runner_fx.credential_fx
conflict_fx = lower_runner_fx.conflict_fx
prior_witness_fx = lower_runner_fx.witness_fx
inherited_checkpoint_fx = lower_runner_fx.inherited_checkpoint_fx
lower_fx = lower_runner_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / "witness-gated-current-checkpoint-final.schema.json"


def prepare(
    tmp_path: Path,
    *,
    run_id: str,
    conflict: bool = False,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    if not conflict:
        return (
            current_witness_fx.prepare_witness_store(tmp_path, run_id=run_id),
            current_witness_fx.witness_attestations(),
        )

    checkpoint_prepared = current_checkpoint_fx.prepare_checkpoint_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, checkpoint_prepared[0])
    predecessor = checkpoint_prepared[2]
    documents = tuple(
        deepcopy(current_witness_fx.load_document(path))
        for path in current_witness_fx.ATTESTATION_PATHS
    )
    documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    documents[2]["observation_kind"] = "conflicting_head"
    attestations = current_witness_fx.witness_attestations(documents)
    corpus_document = deepcopy(
        current_witness_fx.load_document(current_witness_fx.CORPUS_PATH)
    )
    corpus_document[current_witness_fx.ATTESTATION_KEY][2] = (
        current_witness_fx.stored_ref_document(attestations[2].reference())
    )
    selected = current_witness_fx.witness_corpus(
        corpus_document,
        predecessor=predecessor,
    )
    plan = replace(
        checkpoint_prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    current_witness_fx.persist_current_checkpoint_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        registry=current_witness_fx.witness_registry(),
        policy=current_witness_fx.witness_policy(),
        head_checkpoint=current_checkpoint_fx.checkpoint(),
        attestations=attestations,
        evaluated_at="2026-08-03T19:57:54Z",
    )
    return (
        (store, plan, selected, *checkpoint_prepared[2:]),
        attestations,
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    conflict: bool = False,
    current_checkpoint_verified_at: str = "2026-08-03T19:57:53Z",
    current_witness_evaluated_at: str = "2026-08-03T19:57:54Z",
    current_revocation_evaluated_at: str = "2026-08-03T19:57:55Z",
    current_credential_evaluated_at: str = "2026-08-03T19:57:56Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:57:57Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:57:58Z",
    checkpoint_verified_at: str = "2026-08-03T19:57:59Z",
    predecessor_witness_evaluated_at: str = "2026-08-03T19:58:00Z",
    inherited_witness_evaluated_at: str = "2026-08-03T19:58:00Z",
    inherited_revocation_evaluated_at: str = "2026-08-03T19:58:01Z",
    inherited_credential_evaluated_at: str = "2026-08-03T19:58:06Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:58:11Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:21Z",
    inherited_credential_completed_at: str = "2026-08-03T19:58:36Z",
    inherited_revocation_completed_at: str = "2026-08-03T19:58:51Z",
    checkpoint_completed_at: str = "2026-08-03T19:59:06Z",
    prior_completed_at: str = "2026-08-03T19:59:21Z",
    current_revocation_completed_at: str = "2026-08-03T19:59:36Z",
    current_checkpoint_completed_at: str = "2026-08-03T19:59:51Z",
    completed_at: str = "2026-08-03T20:00:06Z",
):
    prepared, current_attestations = prepare(
        tmp_path,
        run_id=run_id,
        conflict=conflict,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = WitnessGatedCurrentCheckpointExperimentRunner(artifact_store=store)
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        checkpoint_corpus=prepared[3],
        current_checkpoint_policy=current_checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=current_checkpoint_fx.checkpoint_log(),
        current_checkpoints=(current_checkpoint_fx.checkpoint(),),
        current_witness_registry=current_witness_fx.witness_registry(),
        current_witness_policy=current_witness_fx.witness_policy(),
        current_witness_attestations=current_attestations,
        current_revocation_corpus=prepared[4],
        credential_corpus=prepared[5],
        adjudication_corpus=prepared[6],
        witness_predecessor=prepared[7],
        inherited_checkpoint_corpus=prepared[8],
        inherited_revocation_corpus=prepared[9],
        inherited_credential_corpus=prepared[10],
        inherited_adjudication_corpus=prepared[11],
        inherited_checkpoint_policy=inherited_checkpoint_fx.checkpoint_policy(),
        inherited_checkpoint_log=inherited_checkpoint_fx.checkpoint_log(),
        inherited_checkpoints=(inherited_checkpoint_fx.checkpoint(),),
        witness_registry=prior_witness_fx.witness_registry(),
        witness_policy=prior_witness_fx.witness_policy(),
        conflict_witness_attestations=conflict_fx.conflict_attestations(),
        predecessor_witness_attestations=prior_witness_fx.witness_attestations(),
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
        inherited_witness_receipt=prepared[12],
        checkpoint_executor=None,
        experiment_run_id=run_id,
        current_checkpoint_verified_at=current_checkpoint_verified_at,
        current_witness_evaluated_at=current_witness_evaluated_at,
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
        current_checkpoint_completed_at=current_checkpoint_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_unanimous_current_witnesses_delegate_exact_pr39(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-witness-unanimous")
    assert receipt.status is CurrentCheckpointWitnessRunnerStatus.VERIFIED
    assert (
        receipt.current_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
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
    assert receipt.checkpoint_receipt is not None
    assert receipt.checkpoint_receipt.experiment_run_id == receipt.experiment_run_id
    assert receipt.verified_checks == CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_one_required_current_conflict_abstains_before_pr39(tmp_path: Path) -> None:
    run_id = "current-witness-conflict"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        conflict=True,
    )
    assert (
        receipt.current_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.revocation_outcome is None
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
    assert receipt.checkpoint_receipt is None
    lower_final_id = (
        f"{run_id}:checkpoint-conflict-revocation-witness-conflict-adjudicator-"
        "credential-revocation-checkpoint-witness-conflict-adjudicator-"
        "credential-revocation-checkpoint-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(lower_final_id)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_unanimous_witnesses_preserve_later_current_suspension(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-witness-later-suspension",
        current_revocation_evaluated_at="2027-01-01T00:00:00Z",
        current_credential_evaluated_at="2027-01-01T00:00:01Z",
        conflict_witness_evaluated_at="2027-01-01T00:00:02Z",
        prior_completed_at="2027-01-01T00:00:03Z",
        current_revocation_completed_at="2027-01-01T00:00:04Z",
        current_checkpoint_completed_at="2027-01-01T00:00:05Z",
        completed_at="2027-01-01T00:00:06Z",
    )
    assert (
        receipt.current_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
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
    assert receipt.checkpoint_receipt is not None
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_witness_before_checkpoint_verification_fails_preflight(
    tmp_path: Path,
) -> None:
    with pytest.raises(CurrentCheckpointWitnessExperimentError) as captured:
        execute(
            tmp_path,
            run_id="current-witness-before-checkpoint",
            current_checkpoint_verified_at="2026-08-03T19:57:55Z",
            current_witness_evaluated_at="2026-08-03T19:57:54Z",
        )
    assert captured.value.stage is CurrentCheckpointWitnessRunnerStage.PREFLIGHT
