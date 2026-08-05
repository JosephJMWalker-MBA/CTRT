from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import test_credentialed_current_revocation_checkpoint_witness_conflict_runner as pr47_fx
import test_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger as revocation_fx
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_current_revocation_checkpoint_witness_conflict_runner import (
    CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS,
    CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError,
    CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage,
    CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus,
    RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

credential_fx = revocation_fx.credential_fx
adjudication_fx = credential_fx.adjudication_fx

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-current-revocation-checkpoint-witness-conflict-"
    "final.schema.json"
)


class StubCredentialRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_credential_receipt(tmp_path: Path, *, run_id: str):
    adjudication_receipt = pr47_fx.active_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr47_fx.execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
    )
    return receipt


def later_abstaining_credential_receipt(tmp_path: Path, *, run_id: str):
    adjudication_receipt = pr47_fx.suspended_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr47_fx.execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
        prior_completed_at="2027-01-01T00:00:09Z",
        completed_at="2027-01-01T00:00:10Z",
    )
    return receipt


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
    revocation_fx.persist_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=credential_corpus,
        adjudicator_registry=adjudication_fx.conflict_adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        ledger=revocation_fx.revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=adjudication_fx.conflict_adjudication(),
        events=(revocation_fx.suspension_event(),),
        evaluated_at="2026-08-03T19:58:46Z",
    )
    return (store, plan, selected, *prepared[2:])


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    credential_receipt: Any,
    revocation_evaluated_at: str = "2026-08-03T19:58:46Z",
    credential_evaluated_at: str = "2026-08-03T19:58:47Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:58:48Z",
    prior_completed_at: str = "2026-08-04T00:00:32Z",
    completed_at: str = "2026-08-04T00:00:33Z",
):
    prepared = prepare_revocation_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner(
        artifact_store=store
    )
    stub = StubCredentialRunner(credential_receipt)
    cast(Any, runner)._runner = stub
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        credential_corpus=prepared[3],
        adjudication_corpus=prepared[4],
        conflict_adjudicator_registry=adjudication_fx.conflict_adjudicator_registry(),
        credential_issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        credentials=(credential_fx.credential(),),
        conflict_adjudication=adjudication_fx.conflict_adjudication(),
        revocation_policy=revocation_fx.revocation_policy(),
        revocation_ledger=revocation_fx.revocation_ledger(),
        revocation_events=(revocation_fx.suspension_event(),),
        experiment_run_id=run_id,
        revocation_evaluated_at=revocation_evaluated_at,
        credential_evaluated_at=credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        prior_completed_at=prior_completed_at,
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def final_document(receipt: Any, store: FileSystemArtifactStore) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def test_active_revocation_status_delegates_exact_pr47(tmp_path: Path) -> None:
    run_id = "current-revocation-conflict-revocation-active"
    credential_receipt = active_credential_receipt(tmp_path, run_id=run_id)
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
    )
    assert (
        receipt.status
        is CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus.VERIFIED
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_checkpoint_resolution_status
        is WitnessConflictResolutionStatus.RESOLVED
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudication_outcome
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.credential_receipt is credential_receipt
    assert receipt.verified_checks == (
        CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
    )
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_effective_suspension_stops_before_pr47(tmp_path: Path) -> None:
    run_id = "current-revocation-conflict-revocation-suspended"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=None,
        revocation_evaluated_at="2027-02-01T00:00:00Z",
        credential_evaluated_at="2027-02-01T00:00:01Z",
        conflict_witness_evaluated_at="2027-02-01T00:00:02Z",
        prior_completed_at="2027-02-01T00:00:03Z",
        completed_at="2027-02-01T00:00:04Z",
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
        is None
    )
    assert receipt.current_revocation_checkpoint_resolution_status is None
    assert receipt.current_conflict_adjudicator_revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credential_receipt is None
    assert not stub.calls
    pr47_final = (
        f"{run_id}:current-revocation-checkpoint-witness-conflict-adjudicator-"
        "credential-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr47_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_revocation_execution_preserves_later_pr47_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-revocation-conflict-revocation-later-abstention"
    credential_receipt = later_abstaining_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
        prior_completed_at="2027-01-01T00:00:11Z",
        completed_at="2027-01-01T00:00:12Z",
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_revocation_after_credential_fails_preflight(tmp_path: Path) -> None:
    run_id = "current-revocation-conflict-revocation-late"
    with pytest.raises(
        CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError
    ) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            credential_receipt=None,
            revocation_evaluated_at="2026-08-03T19:58:48Z",
            credential_evaluated_at="2026-08-03T19:58:47Z",
        )
    assert (
        captured.value.stage
        is CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.PREFLIGHT
    )
