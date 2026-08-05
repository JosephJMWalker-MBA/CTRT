from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicated_current_revocation_checkpoint_witness_runner import (
    ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
    AdjudicatedCurrentRevocationCheckpointWitnessExperimentError,
    AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner,
    AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage,
    AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus,
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

import test_current_revocation_checkpoint_witness as witness_fx
import test_current_revocation_checkpoint_witness_conflict_adjudication as contract_fx
import test_witness_gated_current_revocation_checkpoint_runner as pr45_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "adjudicated-current-revocation-checkpoint-witness-final.schema.json"
)


class StubWitnessRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_witness_receipt(tmp_path: Path, *, run_id: str):
    checkpoint_receipt = pr45_fx.active_checkpoint_receipt(tmp_path, run_id=run_id)
    receipt, _, _, _ = pr45_fx.execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=checkpoint_receipt,
    )
    return receipt


def suspended_witness_receipt(tmp_path: Path, *, run_id: str):
    checkpoint_receipt = pr45_fx.suspended_checkpoint_receipt(tmp_path, run_id=run_id)
    receipt, _, _, _ = pr45_fx.execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=checkpoint_receipt,
        current_checkpoint_verified_at="2027-01-01T00:00:00Z",
        revocation_evaluated_at="2027-01-01T00:00:01Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        current_checkpoint_completed_at="2027-01-01T00:00:06Z",
        completed_at="2027-01-01T00:00:07Z",
    )
    return receipt


def prepare(
    tmp_path: Path,
    *,
    run_id: str,
    record: WitnessConflictAdjudicationSnapshot | None = None,
) -> tuple[Any, ...]:
    if record is None:
        return contract_fx.prepare_adjudication_store(tmp_path, run_id=run_id)

    prepared = witness_fx.prepare_witness_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    witness_predecessor = prepared[2]
    checkpoint_predecessor = prepared[3]
    document = deepcopy(contract_fx.load_document(contract_fx.CORPUS_PATH))
    document[contract_fx.ADJUDICATION_REF_KEY] = contract_fx.stored_ref_document(
        record.reference()
    )
    document["corpus_id"] = (
        "corpus.synthetic-three-items.current-revocation-checkpoint-witness-"
        f"conflict-adjudication-bound.{record.status.value}-runner-test"
    )
    document["corpus_version"] = f"1.24.1-runner-{record.status.value}"
    selected = contract_fx.adjudication_corpus(
        document,
        checkpoint_predecessor=checkpoint_predecessor,
        witness_predecessor=witness_predecessor,
    )
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    contract_fx.persist_current_revocation_checkpoint_adjudication_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        witness_predecessor=witness_predecessor,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        head_checkpoint=witness_fx.checkpoint_fx.checkpoint(),
        witness_attestations=contract_fx.conflict_attestations(),
        adjudicator_registry=contract_fx.conflict_adjudicator_registry(),
        adjudication_policy=contract_fx.conflict_adjudication_policy(),
        adjudication=record,
        evaluated_at="2026-08-03T19:58:37Z",
    )
    return (store, plan, selected, *prepared[2:])


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    witness_receipt: Any,
    record: WitnessConflictAdjudicationSnapshot | None = None,
    conflict_witness_evaluated_at: str = "2026-08-03T19:58:37Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:58:38Z",
    witness_checkpoint_verified_at: str = "2026-08-03T19:58:39Z",
    canonical_witness_evaluated_at: str = "2026-08-03T19:58:40Z",
    current_checkpoint_verified_at: str = "2026-08-04T00:00:00Z",
    revocation_evaluated_at: str = "2026-08-04T00:00:01Z",
    revocation_completed_at: str = "2026-08-04T00:00:24Z",
    current_checkpoint_completed_at: str = "2026-08-04T00:00:25Z",
    prior_completed_at: str = "2026-08-04T00:00:27Z",
    completed_at: str = "2026-08-04T00:00:28Z",
):
    prepared = prepare(tmp_path, run_id=run_id, record=record)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner(
        artifact_store=store
    )
    stub = StubWitnessRunner(witness_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        witness_predecessor=prepared[3],
        current_checkpoint_corpus=prepared[4],
        current_checkpoint_policy=witness_fx.checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=witness_fx.checkpoint_fx.checkpoint_log(),
        current_checkpoints=(witness_fx.checkpoint_fx.checkpoint(),),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        conflict_witness_attestations=contract_fx.conflict_attestations(),
        canonical_witness_attestations=witness_fx.witness_attestations(),
        conflict_adjudicator_registry=contract_fx.conflict_adjudicator_registry(),
        conflict_adjudication_policy=contract_fx.conflict_adjudication_policy(),
        conflict_adjudication=record or contract_fx.conflict_adjudication(),
        current_conflict_adjudicator_revocation_ledger=(
            pr45_fx.pr44_fx.lower_fx.revocation_fx.revocation_ledger()
        ),
        experiment_run_id=run_id,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        conflict_adjudication_evaluated_at=(
            conflict_adjudication_evaluated_at
        ),
        witness_checkpoint_verified_at=witness_checkpoint_verified_at,
        canonical_witness_evaluated_at=canonical_witness_evaluated_at,
        current_checkpoint_verified_at=current_checkpoint_verified_at,
        current_conflict_adjudicator_revocation_evaluated_at=(
            revocation_evaluated_at
        ),
        revocation_completed_at=revocation_completed_at,
        current_checkpoint_completed_at=current_checkpoint_completed_at,
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_resolved_adjudication_delegates_exact_pr45(tmp_path: Path) -> None:
    run_id = "current-revocation-checkpoint-adjudication-resolved"
    witness_receipt = active_witness_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
    )
    assert (
        receipt.status
        is AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED
    )
    assert (
        receipt.conflicting_current_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert (
        receipt.current_revocation_checkpoint_resolution_status
        is WitnessConflictResolutionStatus.RESOLVED
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.resolved_current_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.predecessor_witness_receipt is witness_receipt
    assert receipt.verified_checks == (
        ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS
    )
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


@pytest.mark.parametrize("status", ["pending", "unresolved"])
def test_unresolved_authority_stops_before_pr45(
    tmp_path: Path,
    status: str,
) -> None:
    document = deepcopy(contract_fx.load_document(contract_fx.ADJUDICATION_PATH))
    document["status"] = status
    document["selected_head_ref"] = None
    document["rationale"] = f"Synthetic conflict remains {status}."
    if status == "pending":
        document["adjudicator_id"] = None
        document["adjudicator_identity_revision"] = None
        document["preserved_dissent"] = []
    record = contract_fx.conflict_adjudication(document)
    run_id = f"current-revocation-checkpoint-adjudication-{status}"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=None,
        record=record,
    )
    assert (
        receipt.conflicting_current_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.current_revocation_checkpoint_resolution_status.value == status
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.ABSTAIN
    )
    assert receipt.resolved_current_revocation_checkpoint_witness_outcome is None
    assert receipt.current_conflict_adjudicator_revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.predecessor_witness_receipt is None
    assert not stub.calls
    pr45_final = (
        f"{run_id}:current-checkpoint-witness-conflict-adjudicator-credential-"
        "revocation-checkpoint-witness-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr45_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_resolved_adjudication_preserves_later_revocation_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-checkpoint-adjudication-suspended"
    witness_receipt = suspended_witness_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, _ = execute(
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
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.resolved_current_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.current_conflict_adjudicator_credential_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.predecessor_witness_receipt is witness_receipt
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_adjudication_before_conflict_evaluation_fails_preflight(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-checkpoint-adjudication-early"
    witness_receipt = active_witness_receipt(tmp_path, run_id=run_id)
    with pytest.raises(
        AdjudicatedCurrentRevocationCheckpointWitnessExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            witness_receipt=witness_receipt,
            conflict_witness_evaluated_at="2026-08-03T19:58:39Z",
            conflict_adjudication_evaluated_at="2026-08-03T19:58:38Z",
        )
    assert (
        captured.value.stage
        is AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage.PREFLIGHT
    )
