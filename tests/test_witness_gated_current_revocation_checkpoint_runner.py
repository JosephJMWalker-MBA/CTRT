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
from ctrt.witness_gated_current_revocation_checkpoint_runner import (
    CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
    CurrentRevocationCheckpointWitnessExperimentError,
    CurrentRevocationCheckpointWitnessRunnerStage,
    CurrentRevocationCheckpointWitnessRunnerStatus,
    WitnessGatedCurrentRevocationCheckpointExperimentRunner,
)

witness_fx = import_module("test_current_revocation_checkpoint_witness")
pr44_fx = import_module(
    "test_checkpoint_gated_current_checkpoint_witness_conflict_runner"
)

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "witness-gated-current-revocation-checkpoint-final.schema.json"
)


class StubCheckpointRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_checkpoint_receipt(tmp_path: Path, *, run_id: str):
    lower_receipt, _ = pr44_fx.active_lower_receipt(tmp_path, run_id=run_id)
    receipt, _, _, _ = pr44_fx.execute_outer(
        tmp_path,
        run_id=run_id,
        lower_receipt=lower_receipt,
        checkpoint_verified_at="2026-08-04T00:00:00Z",
        revocation_evaluated_at="2026-08-04T00:00:01Z",
        revocation_completed_at="2026-08-04T00:00:24Z",
        completed_at="2026-08-04T00:00:25Z",
    )
    return receipt


def suspended_checkpoint_receipt(tmp_path: Path, *, run_id: str):
    lower_receipt, _ = pr44_fx.suspended_lower_receipt(tmp_path, run_id=run_id)
    receipt, _, _, _ = pr44_fx.execute_outer(
        tmp_path,
        run_id=run_id,
        lower_receipt=lower_receipt,
        checkpoint_verified_at="2027-01-01T00:00:00Z",
        revocation_evaluated_at="2027-01-01T00:00:01Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        completed_at="2027-01-01T00:00:06Z",
    )
    return receipt


def prepare(
    tmp_path: Path,
    *,
    run_id: str,
    conflict: bool = False,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    if not conflict:
        return (
            witness_fx.prepare_witness_store(tmp_path, run_id=run_id),
            witness_fx.witness_attestations(),
        )

    checkpoint_prepared = witness_fx.checkpoint_fx.prepare_checkpoint_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, checkpoint_prepared[0])
    predecessor = checkpoint_prepared[2]
    documents = tuple(
        deepcopy(witness_fx.load_document(path))
        for path in witness_fx.ATTESTATION_PATHS
    )
    documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    documents[2]["observation_kind"] = "conflicting_head"
    attestations = witness_fx.witness_attestations(documents)
    corpus_document = deepcopy(witness_fx.load_document(witness_fx.CORPUS_PATH))
    corpus_document[witness_fx.ATTESTATION_KEY][2] = (
        witness_fx.stored_ref_document(attestations[2].reference())
    )
    selected = witness_fx.witness_corpus(
        corpus_document,
        predecessor=predecessor,
    )
    plan = replace(
        checkpoint_prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    witness_fx.contract.persist_current_conflict_adjudicator_revocation_checkpoint_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        registry=witness_fx.witness_registry(),
        policy=witness_fx.witness_policy(),
        head_checkpoint=witness_fx.checkpoint_fx.checkpoint(),
        attestations=attestations,
        evaluated_at="2026-08-03T19:58:31Z",
    )
    return (
        (store, plan, selected, *checkpoint_prepared[2:]),
        attestations,
    )


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    checkpoint_receipt: Any,
    conflict: bool = False,
    witness_checkpoint_verified_at: str = "2026-08-03T19:58:30Z",
    current_witness_evaluated_at: str = "2026-08-03T19:58:31Z",
    current_checkpoint_verified_at: str = "2026-08-04T00:00:00Z",
    revocation_evaluated_at: str = "2026-08-04T00:00:01Z",
    revocation_completed_at: str = "2026-08-04T00:00:24Z",
    current_checkpoint_completed_at: str = "2026-08-04T00:00:25Z",
    completed_at: str = "2026-08-04T00:00:26Z",
):
    prepared, attestations = prepare(
        tmp_path,
        run_id=run_id,
        conflict=conflict,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = WitnessGatedCurrentRevocationCheckpointExperimentRunner(
        artifact_store=store
    )
    stub = StubCheckpointRunner(checkpoint_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        checkpoint_corpus=prepared[3],
        current_checkpoint_policy=witness_fx.checkpoint_fx.checkpoint_policy(),
        current_checkpoint_log=witness_fx.checkpoint_fx.checkpoint_log(),
        current_checkpoints=(witness_fx.checkpoint_fx.checkpoint(),),
        current_witness_registry=witness_fx.witness_registry(),
        current_witness_policy=witness_fx.witness_policy(),
        current_witness_attestations=attestations,
        current_conflict_adjudicator_revocation_ledger=(
            pr44_fx.lower_fx.revocation_fx.revocation_ledger()
        ),
        experiment_run_id=run_id,
        witness_checkpoint_verified_at=witness_checkpoint_verified_at,
        current_witness_evaluated_at=current_witness_evaluated_at,
        current_checkpoint_verified_at=current_checkpoint_verified_at,
        current_conflict_adjudicator_revocation_evaluated_at=(
            revocation_evaluated_at
        ),
        revocation_completed_at=revocation_completed_at,
        current_checkpoint_completed_at=current_checkpoint_completed_at,
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_all_named_witnesses_delegate_exact_pr44(tmp_path: Path) -> None:
    run_id = "current-revocation-checkpoint-witness-active"
    checkpoint_receipt = active_checkpoint_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=checkpoint_receipt,
    )
    assert receipt.status is CurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED
    assert (
        receipt.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.checkpoint_receipt is checkpoint_receipt
    assert receipt.verified_checks == (
        CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS
    )
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_one_required_conflict_stops_before_pr44(tmp_path: Path) -> None:
    run_id = "current-revocation-checkpoint-witness-conflict"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=None,
        conflict=True,
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.current_conflict_adjudicator_revocation_outcome is None
    assert receipt.current_conflict_adjudicator_credential_outcome is None
    assert receipt.conflicting_witness_outcome is None
    assert receipt.current_resolution_status is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    assert not stub.calls
    pr44_final = (
        f"{run_id}:current-checkpoint-witness-conflict-adjudicator-credential-"
        "revocation-checkpoint-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr44_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_witness_execution_preserves_pr44_revocation_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-checkpoint-witness-suspended"
    checkpoint_receipt = suspended_checkpoint_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        checkpoint_receipt=checkpoint_receipt,
        current_checkpoint_verified_at="2027-01-01T00:00:00Z",
        revocation_evaluated_at="2027-01-01T00:00:01Z",
        revocation_completed_at="2027-01-01T00:00:05Z",
        current_checkpoint_completed_at="2027-01-01T00:00:06Z",
        completed_at="2027-01-01T00:00:07Z",
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.current_conflict_adjudicator_credential_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is checkpoint_receipt
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_witness_before_checkpoint_reverification_fails_preflight(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-checkpoint-witness-early"
    checkpoint_receipt = active_checkpoint_receipt(tmp_path, run_id=run_id)
    with pytest.raises(
        CurrentRevocationCheckpointWitnessExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            checkpoint_receipt=checkpoint_receipt,
            witness_checkpoint_verified_at="2026-08-03T19:58:32Z",
            current_witness_evaluated_at="2026-08-03T19:58:31Z",
        )
    assert captured.value.stage is CurrentRevocationCheckpointWitnessRunnerStage.PREFLIGHT
