from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactStoreError, FileSystemArtifactStore
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

revocation_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_ledger"
)
credential_fx = revocation_fx.credential_fx
pr52_fx = import_module(
    "test_credentialed_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)
runner_module = import_module(
    "ctrt.revocation_gated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_conflict_adjudicator_credential_runner"
)

Runner = vars(runner_module)[
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialExperimentRunner"
]
RunnerError = vars(runner_module)[
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialExperimentError"
]
RunnerStage = vars(runner_module)[
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialRunnerStage"
]
RunnerStatus = vars(runner_module)[
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialRunnerStatus"
]
VERIFIED_CHECKS = vars(runner_module)[
    "REVOCATION_GATED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_CONFLICT_ADJUDICATOR_CREDENTIAL_VERIFIED_CHECKS"
]
PR52_OUTCOME_FIELDS = runner_module.PR52_OUTCOME_FIELDS

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-current-revocation-conflict-adjudicator-checkpoint-"
    "witness-conflict-adjudicator-credential-final.schema.json"
)


class StubCredentialRunner:
    def __init__(self, receipt: Any) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.receipt


def active_credential_receipt(tmp_path: Path, *, run_id: str) -> Any:
    adjudication_receipt = pr52_fx.active_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr52_fx.execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
    )
    return receipt


def later_abstaining_credential_receipt(
    tmp_path: Path,
    *,
    run_id: str,
) -> Any:
    adjudication_receipt = pr52_fx.later_abstaining_adjudication_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, _, _, _ = pr52_fx.execute(
        tmp_path,
        run_id=run_id,
        adjudication_receipt=adjudication_receipt,
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        witness_completed_at="2027-01-01T00:00:18Z",
        adjudication_completed_at="2027-01-01T00:00:19Z",
        completed_at="2027-01-01T00:00:20Z",
    )
    return receipt


def prepare_revocation_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    prepared = credential_fx.prepare_credential_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    credential_corpus = prepared[2]
    selected = revocation_fx.revocation_corpus(
        predecessor=credential_corpus
    )
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    revocation_fx.persist_revocation_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=credential_corpus,
        adjudicator_registry=(
            credential_fx.adjudication_fx.conflict_adjudicator_registry()
        ),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        ledger=revocation_fx.revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=(
            credential_fx.adjudication_fx.conflict_adjudication()
        ),
        events=(revocation_fx.suspension_event(),),
        evaluated_at="2026-08-03T19:59:18Z",
    )
    return (store, plan, selected, *prepared[2:])


def final_document(
    receipt: Any,
    store: FileSystemArtifactStore,
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    credential_receipt: Any,
    revocation_evaluated_at: str = "2026-08-03T19:59:18Z",
    credential_evaluated_at: str = "2026-08-03T19:59:19Z",
    conflict_witness_evaluated_at: str = "2026-08-03T19:59:20Z",
    conflict_adjudication_evaluated_at: str = "2026-08-03T19:59:21Z",
    checkpoint_reverified_at: str = "2026-08-03T19:59:22Z",
    canonical_witness_evaluated_at: str = "2026-08-03T19:59:23Z",
    delegated_checkpoint_verified_at: str = "2026-08-04T00:00:01Z",
    current_revocation_evaluated_at: str = "2026-08-04T00:00:02Z",
    revocation_completed_at: str = "2026-08-04T00:00:33Z",
    checkpoint_completed_at: str = "2026-08-04T00:00:34Z",
    witness_completed_at: str = "2026-08-04T00:00:35Z",
    adjudication_completed_at: str = "2026-08-04T00:00:36Z",
    credential_completed_at: str = "2026-08-04T00:00:37Z",
    completed_at: str = "2026-08-04T00:00:38Z",
):
    prepared = prepare_revocation_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    runner = Runner(artifact_store=store)
    stub = StubCredentialRunner(credential_receipt)
    cast(Any, runner)._runner = stub
    adjudication_fx = credential_fx.adjudication_fx
    receipt = runner.run(
        plan=prepared[1],
        corpus=prepared[2],
        credential_corpus=prepared[3],
        adjudication_corpus=prepared[4],
        conflict_adjudicator_registry=(
            adjudication_fx.conflict_adjudicator_registry()
        ),
        credential_issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        credentials=(credential_fx.credential(),),
        conflict_adjudication_policy=(
            adjudication_fx.conflict_adjudication_policy()
        ),
        conflict_adjudication=adjudication_fx.conflict_adjudication(),
        revocation_policy=revocation_fx.revocation_policy(),
        revocation_ledger=revocation_fx.revocation_ledger(),
        revocation_events=(revocation_fx.suspension_event(),),
        experiment_run_id=run_id,
        revocation_evaluated_at=revocation_evaluated_at,
        credential_evaluated_at=credential_evaluated_at,
        conflict_witness_evaluated_at=conflict_witness_evaluated_at,
        conflict_adjudication_evaluated_at=(
            conflict_adjudication_evaluated_at
        ),
        checkpoint_reverified_at=checkpoint_reverified_at,
        canonical_witness_evaluated_at=canonical_witness_evaluated_at,
        delegated_checkpoint_verified_at=delegated_checkpoint_verified_at,
        current_revocation_evaluated_at=(
            current_revocation_evaluated_at
        ),
        revocation_completed_at=revocation_completed_at,
        checkpoint_completed_at=checkpoint_completed_at,
        witness_completed_at=witness_completed_at,
        adjudication_completed_at=adjudication_completed_at,
        credential_completed_at=credential_completed_at,
        completed_at=completed_at,
    )
    return receipt, store, stub, prepared


def test_active_status_delegates_exact_pr52(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudicator-credential-revocation-active"
    credential_receipt = active_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, prepared = execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
    )
    assert receipt.status is RunnerStatus.VERIFIED
    revocation_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_revocation_outcome"
    )
    credential_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_outcome"
    )
    assert (
        getattr(receipt, revocation_field)
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        getattr(receipt, credential_field)
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_revocation_conflict_adjudicator_checkpoint_resolution_status
        is WitnessConflictResolutionStatus.RESOLVED
    )
    adjudication_field = (
        "current_revocation_conflict_adjudicator_checkpoint_"
        "conflict_adjudication_outcome"
    )
    assert (
        getattr(receipt, adjudication_field)
        is WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.credential_receipt is credential_receipt
    assert receipt.verified_checks == VERIFIED_CHECKS
    assert len(stub.calls) == 1
    assert stub.calls[0]["experiment_run_id"] == run_id
    assert stub.calls[0]["plan"].corpus_ref == prepared[3].reference()
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_effective_suspension_stops_before_pr52(tmp_path: Path) -> None:
    run_id = "current-conflict-adjudicator-credential-revocation-suspended"
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=None,
        revocation_evaluated_at="2027-02-01T00:00:00Z",
        credential_evaluated_at="2027-02-01T00:00:01Z",
        conflict_witness_evaluated_at="2027-02-01T00:00:02Z",
        conflict_adjudication_evaluated_at="2027-02-01T00:00:03Z",
        checkpoint_reverified_at="2027-02-01T00:00:04Z",
        canonical_witness_evaluated_at="2027-02-01T00:00:05Z",
        delegated_checkpoint_verified_at="2027-02-01T00:00:06Z",
        current_revocation_evaluated_at="2027-02-01T00:00:07Z",
        revocation_completed_at="2027-02-01T00:00:08Z",
        checkpoint_completed_at="2027-02-01T00:00:09Z",
        witness_completed_at="2027-02-01T00:00:10Z",
        adjudication_completed_at="2027-02-01T00:00:11Z",
        credential_completed_at="2027-02-01T00:00:12Z",
        completed_at="2027-02-01T00:00:13Z",
    )
    revocation_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_revocation_outcome"
    )
    assert (
        getattr(receipt, revocation_field)
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert all(
        getattr(receipt, name) is None for name in PR52_OUTCOME_FIELDS
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credential_receipt is None
    assert not stub.calls
    pr52_final = (
        f"{run_id}:current-revocation-conflict-adjudicator-checkpoint-"
        "witness-conflict-adjudicator-credential-completion"
    )
    with pytest.raises(ArtifactStoreError):
        store.get(pr52_final)
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_revocation_execution_preserves_later_abstention(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudicator-revocation-later-abstention"
    credential_receipt = later_abstaining_credential_receipt(
        tmp_path,
        run_id=run_id,
    )
    receipt, store, stub, _ = execute(
        tmp_path,
        run_id=run_id,
        credential_receipt=credential_receipt,
        delegated_checkpoint_verified_at="2027-01-01T00:00:14Z",
        current_revocation_evaluated_at="2027-01-01T00:00:15Z",
        revocation_completed_at="2027-01-01T00:00:16Z",
        checkpoint_completed_at="2027-01-01T00:00:17Z",
        witness_completed_at="2027-01-01T00:00:18Z",
        adjudication_completed_at="2027-01-01T00:00:19Z",
        credential_completed_at="2027-01-01T00:00:20Z",
        completed_at="2027-01-01T00:00:21Z",
    )
    revocation_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_revocation_outcome"
    )
    credential_field = (
        "current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_outcome"
    )
    assert (
        getattr(receipt, revocation_field)
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        getattr(receipt, credential_field)
        is CredentialDecisionOutcome.EXECUTE
    )
    assert (
        receipt.current_conflict_adjudicator_revocation_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert len(stub.calls) == 1
    validate_schema(FINAL_SCHEMA, final_document(receipt, store))


def test_revocation_after_credential_fails_preflight(
    tmp_path: Path,
) -> None:
    run_id = "current-conflict-adjudicator-credential-revocation-late"
    with pytest.raises(RunnerError) as captured:
        execute(
            tmp_path,
            run_id=run_id,
            credential_receipt=None,
            revocation_evaluated_at="2026-08-03T19:59:20Z",
            credential_evaluated_at="2026-08-03T19:59:19Z",
        )
    assert captured.value.stage is RunnerStage.PREFLIGHT
