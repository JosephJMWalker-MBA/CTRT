from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicated_current_checkpoint_witness_runner import (
    ADJUDICATED_CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
    AdjudicatedCurrentCheckpointWitnessExperimentError,
    AdjudicatedCurrentCheckpointWitnessExperimentRunner,
    AdjudicatedCurrentCheckpointWitnessRunnerStage,
    AdjudicatedCurrentCheckpointWitnessRunnerStatus,
)
from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictResolutionStatus,
)

current_fx = import_module("test_current_checkpoint_witness_conflict_adjudication")
pr40_fx = import_module("test_witness_gated_current_checkpoint_runner")
current_witness_fx = current_fx.witness_fx
current_checkpoint_fx = current_fx.checkpoint_fx
current_revocation_fx = pr40_fx.current_revocation_fx
credential_fx = pr40_fx.credential_fx
lower_conflict_fx = pr40_fx.conflict_fx
lower_witness_fx = pr40_fx.prior_witness_fx
inherited_checkpoint_fx = pr40_fx.inherited_checkpoint_fx
lower_fx = pr40_fx.lower_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "adjudicated-current-checkpoint-witness-final.schema.json"
)


def prepare(
    tmp_path: Path,
    *,
    run_id: str,
    record: WitnessConflictAdjudicationSnapshot | None = None,
) -> tuple[Any, ...]:
    if record is None:
        return current_fx.prepare_adjudication_store(
            tmp_path,
            run_id=run_id,
        )

    prepared = current_witness_fx.prepare_witness_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    witness_predecessor = prepared[2]
    checkpoint_predecessor = prepared[3]
    document = deepcopy(current_fx.load_document(current_fx.CORPUS_PATH))
    document[current_fx.ADJUDICATION_REF_KEY] = current_fx.stored_ref_document(
        record.reference()
    )
    document["corpus_id"] = (
        "corpus.synthetic-three-items.current-checkpoint-witness-conflict-"
        f"adjudication-bound.{record.status.value}-runner-test"
    )
    document["corpus_version"] = f"1.19.1-runner-{record.status.value}"
    selected = current_fx.adjudication_corpus(
        document,
        checkpoint_predecessor=checkpoint_predecessor,
        witness_predecessor=witness_predecessor,
    )
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    current_fx.persist_current_checkpoint_adjudication_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        witness_predecessor=witness_predecessor,
        witness_registry=current_witness_fx.witness_registry(),
        witness_policy=current_witness_fx.witness_policy(),
        head_checkpoint=current_checkpoint_fx.checkpoint(),
        witness_attestations=current_fx.conflict_attestations(),
        adjudicator_registry=current_fx.conflict_adjudicator_registry(),
        adjudication_policy=current_fx.conflict_adjudication_policy(),
        adjudication=record,
        evaluated_at="2026-08-03T19:58:01Z",
    )
    return (store, plan, selected, *prepared[2:])


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    record: WitnessConflictAdjudicationSnapshot | None = None,
    conflict_witness_evaluated_at: str = "2026-08-03T19:58:01Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:58:02Z",
    current_checkpoint_verified_at: str = "2026-08-03T19:58:03Z",
    current_witness_evaluated_at: str = "2026-08-03T19:58:04Z",
    current_revocation_evaluated_at: str = "2026-08-03T19:58:05Z",
    current_credential_evaluated_at: str = "2026-08-03T19:58:06Z",
    lower_conflict_witness_evaluated_at: str = "2026-08-03T19:58:07Z",
    lower_conflict_adjudication_evaluated_at: str = "2026-08-03T19:58:08Z",
    checkpoint_verified_at: str = "2026-08-03T19:58:09Z",
    lower_predecessor_witness_evaluated_at: str = "2026-08-03T19:58:10Z",
    inherited_witness_evaluated_at: str = "2026-08-03T19:58:10Z",
    inherited_revocation_evaluated_at: str = "2026-08-03T19:58:11Z",
    inherited_credential_evaluated_at: str = "2026-08-03T19:58:16Z",
    inherited_adjudication_evaluated_at: str = "2026-08-03T19:58:21Z",
    inherited_adjudication_completed_at: str = "2026-08-03T19:58:31Z",
    inherited_credential_completed_at: str = "2026-08-03T19:58:46Z",
    inherited_revocation_completed_at: str = "2026-08-03T19:59:01Z",
    checkpoint_completed_at: str = "2026-08-03T19:59:16Z",
    lower_completed_at: str = "2026-08-03T19:59:31Z",
    current_revocation_completed_at: str = "2026-08-03T19:59:46Z",
    current_checkpoint_completed_at: str = "2026-08-03T20:00:01Z",
    prior_completed_at: str = "2026-08-03T20:00:16Z",
    completed_at: str = "2026-08-03T20:00:31Z",
):
    prepared = prepare(
        tmp_path,
        run_id=run_id,
        record=record,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = AdjudicatedCurrentCheckpointWitnessExperimentRunner(
        artifact_store=store
    )
    selected_record = record or current_fx.conflict_adjudication()
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        witness_predecessor=prepared[3],
        current_checkpoint_corpus=prepared[4],
        current_checkpoint_policy=current_checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=current_checkpoint_fx.checkpoint_log(),
        current_checkpoints=(current_checkpoint_fx.checkpoint(),),
        witness_registry=current_witness_fx.witness_registry(),
        witness_policy=current_witness_fx.witness_policy(),
        conflict_witness_attestations=current_fx.conflict_attestations(),
        canonical_witness_attestations=current_witness_fx.witness_attestations(),
        conflict_adjudicator_registry=current_fx.conflict_adjudicator_registry(),
        conflict_adjudication_policy=current_fx.conflict_adjudication_policy(),
        conflict_adjudication=selected_record,
        current_revocation_corpus=prepared[5],
        credential_corpus=prepared[6],
        adjudication_corpus=prepared[7],
        lower_witness_predecessor=prepared[8],
        inherited_checkpoint_corpus=prepared[9],
        inherited_revocation_corpus=prepared[10],
        inherited_credential_corpus=prepared[11],
        inherited_adjudication_corpus=prepared[12],
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
        current_issuer_registry=credential_fx.issuer_registry(),
        current_credential_policy=credential_fx.credential_policy(),
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
        inherited_witness_receipt=prepared[13],
        checkpoint_executor=None,
        experiment_run_id=run_id,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
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
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_resolved_conflict_delegates_exact_pr40(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="current-conflict-resolved")
    expected_status = AdjudicatedCurrentCheckpointWitnessRunnerStatus.VERIFIED
    assert receipt.status is expected_status
    assert (
        receipt.conflicting_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
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
    assert (
        receipt.lower_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
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
    assert receipt.predecessor_witness_receipt is not None
    assert (
        receipt.predecessor_witness_receipt.experiment_run_id
        == receipt.experiment_run_id
    )
    assert receipt.verified_checks == (
        ADJUDICATED_CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS
    )
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


@pytest.mark.parametrize("status", ["pending", "unresolved"])
def test_nonresolved_conflict_stops_before_pr40(
    tmp_path: Path,
    status: str,
) -> None:
    document = deepcopy(current_fx.load_document(current_fx.ADJUDICATION_PATH))
    document["status"] = status
    document["selected_head_ref"] = None
    document["rationale"] = f"Synthetic conflict remains {status}."
    if status == "pending":
        document["adjudicator_id"] = None
        document["adjudicator_identity_revision"] = None
        document["preserved_dissent"] = []
    record = current_fx.conflict_adjudication(document)
    run_id = f"current-conflict-{status}"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        record=record,
    )
    expected_resolution = WitnessConflictResolutionStatus(status)
    assert (
        receipt.conflicting_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.current_resolution_status is expected_resolution
    assert (
        receipt.current_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.ABSTAIN
    )
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
    assert receipt.predecessor_witness_receipt is None
    pr40_final_id = (
        f"{run_id}:checkpoint-conflict-revocation-witness-conflict-adjudicator-"
        "credential-revocation-checkpoint-witness-conflict-adjudicator-"
        "credential-revocation-checkpoint-witness-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr40_final_id)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_resolution_remains_execute_when_current_revocation_later_abstains(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="current-conflict-later-suspension",
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
    assert receipt.predecessor_witness_receipt is not None
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_delegated_checkpoint_before_adjudication_fails_preflight(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        AdjudicatedCurrentCheckpointWitnessExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id="current-conflict-checkpoint-before-adjudication",
            current_checkpoint_verified_at="2026-08-03T19:58:01Z",
        )
    expected = AdjudicatedCurrentCheckpointWitnessRunnerStage.PREFLIGHT
    assert captured.value.stage is expected
