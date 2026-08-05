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
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictResolutionStatus,
)

witness_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness"
)
contract_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudication"
)
pr50_fx = import_module(
    "test_witness_gated_current_revocation_checkpoint_witness_conflict_runner"
)
runner_module = import_module(
    "ctrt.adjudicated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)

Runner = vars(runner_module)[
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentRunner"
]
RunnerError = vars(runner_module)[
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentError"
]
RunnerStage = vars(runner_module)[
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStage"
]
RunnerStatus = vars(runner_module)[
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStatus"
]
VERIFIED_CHECKS = vars(runner_module)[
    "ADJUDICATED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_VERIFIED_CHECKS"
]
DELEGATED_OUTCOME_FIELDS = runner_module.DELEGATED_OUTCOME_FIELDS

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "adjudicated-current-revocation-conflict-adjudicator-checkpoint-witness-"
    "final.schema.json"
)


class StubWitnessRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_witness_receipt(tmp_path: Path, *, run_id: str) -> Any:
    checkpoint_receipt = pr50_fx.active_checkpoint_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr50_fx.execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=checkpoint_receipt,
    )
    return receipt


def later_abstaining_witness_receipt(tmp_path: Path, *, run_id: str) -> Any:
    checkpoint_receipt = pr50_fx.later_abstaining_checkpoint_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr50_fx.execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=checkpoint_receipt,
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        completed_at="2027-01-01T00:00:18Z",
    )
    return receipt


def prepare(
    tmp_path: Path,
    *,
    run_id: str,
    record: WitnessConflictAdjudicationSnapshot | None = None,
) -> tuple[Any, ...]:
    if record is None:
        return contract_fx.prepare_adjudication_store(
            tmp_path,
            run_id=run_id,
        )

    prepared = witness_fx.prepare_witness_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    witness_predecessor = prepared[2]
    checkpoint_predecessor = prepared[3]
    document = deepcopy(contract_fx.load_document(contract_fx.CORPUS_PATH))
    document[contract_fx.ADJUDICATION_REF_KEY] = (
        contract_fx.stored_ref_document(record.reference())
    )
    document["corpus_id"] = (
        "corpus.synthetic-three-items.current-revocation-conflict-"
        f"adjudicator-checkpoint-witness-adjudication.{record.status.value}-"
        "runner-test"
    )
    document["corpus_version"] = f"1.29.1-runner-{record.status.value}"
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
    contract_fx.persist_corpus(
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
        evaluated_at="2026-08-03T19:59:09Z",
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
    conflict_witness_evaluated_at: str = "2026-08-03T19:59:09Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:59:10Z",
    checkpoint_reverified_at: str = "2026-08-03T19:59:11Z",
    canonical_witness_evaluated_at: str = "2026-08-03T19:59:12Z",
    delegated_checkpoint_verified_at: str = "2026-08-03T19:59:13Z",
    revocation_evaluated_at: str = "2026-08-04T00:00:01Z",
    revocation_completed_at: str = "2026-08-04T00:00:33Z",
    checkpoint_completed_at: str = "2026-08-04T00:00:34Z",
    witness_completed_at: str = "2026-08-04T00:00:35Z",
    completed_at: str = "2026-08-04T00:00:36Z",
):
    prepared = prepare(tmp_path, run_id=run_id, record=record)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = Runner(artifact_store=store)
    stub = StubWitnessRunner(witness_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        witness_predecessor=prepared[3],
        checkpoint_predecessor=prepared[4],
        current_revocation_corpus=prepared[5],
        current_checkpoint_policy=witness_fx.checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=witness_fx.checkpoint_fx.checkpoint_log(),
        current_checkpoints=(witness_fx.checkpoint_fx.checkpoint(),),
        current_revocation_ledger=(
            witness_fx.checkpoint_fx.revocation_fx.revocation_ledger()
        ),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        conflict_witness_attestations=contract_fx.conflict_attestations(),
        canonical_witness_attestations=witness_fx.witness_attestations(),
        conflict_adjudicator_registry=(
            contract_fx.conflict_adjudicator_registry()
        ),
        conflict_adjudication_policy=(
            contract_fx.conflict_adjudication_policy()
        ),
        conflict_adjudication=record or contract_fx.conflict_adjudication(),
        experiment_run_id=run_id,
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
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_resolved_adjudication_delegates_exact_pr50(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudication-resolved"
    witness_receipt = active_witness_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
    )
    assert receipt.status is RunnerStatus.VERIFIED
    assert (
        receipt.conflicting_current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_resolution_status
        is WitnessConflictResolutionStatus.RESOLVED
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.resolved_current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.predecessor_witness_receipt is witness_receipt
    assert receipt.verified_checks == VERIFIED_CHECKS
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


@pytest.mark.parametrize("status", ["pending", "unresolved"])
def test_unresolved_authority_stops_before_pr50(
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
    run_id = f"current-conflict-adjudication-{status}"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=None,
        record=record,
    )
    assert (
        receipt.conflicting_current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_resolution_status.value
        == status
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.ABSTAIN
    )
    assert (
        receipt.resolved_current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is None
    )
    assert all(
        getattr(receipt, name) is None
        for name in DELEGATED_OUTCOME_FIELDS
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.predecessor_witness_receipt is None
    assert not stub.calls
    pr50_final = (
        f"{run_id}:current-revocation-checkpoint-witness-conflict-"
        "adjudicator-credential-revocation-checkpoint-witness-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr50_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_resolved_adjudication_preserves_later_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudication-later-abstention"
    witness_receipt = later_abstaining_witness_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        witness_receipt=witness_receipt,
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        witness_completed_at="2027-01-01T00:00:18Z",
        completed_at="2027-01-01T00:00:19Z",
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert (
        receipt.resolved_current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.predecessor_witness_receipt is witness_receipt
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_adjudication_before_conflict_evaluation_fails_preflight(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudication-early"
    witness_receipt = active_witness_receipt(tmp_path, run_id=run_id)
    with pytest.raises(RunnerError) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            witness_receipt=witness_receipt,
            conflict_witness_evaluated_at="2026-08-03T19:59:11Z",
            conflict_adjudication_evaluated_at="2026-08-03T19:59:10Z",
        )
    assert captured.value.stage is RunnerStage.PREFLIGHT
