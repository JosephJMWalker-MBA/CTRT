from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_checkpoint_conflict_witness_adjudication_runner import (
    CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS,
    CheckpointConflictWitnessRevocationExperimentError,
    CheckpointConflictWitnessRevocationRunnerStage,
    CheckpointConflictWitnessRevocationRunnerStatus,
    RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

credential_runner_fx = import_module(
    "test_credentialed_checkpoint_conflict_witness_adjudication_runner"
)
revocation_fx = import_module(
    "test_checkpoint_conflict_witness_adjudicator_credential_"
    "revocation_ledger"
)

ROOT = Path(__file__).parents[1]
DECISION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-decision.schema.json"
)
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-checkpoint-conflict-witness-adjudication-final.schema.json"
)


def prepare_revocation_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    store, credential_plan, credential_corpus, adjudication_corpus, witness_receipt = (
        credential_runner_fx.prepare_runner_store(tmp_path, run_id=run_id)
    )
    store = cast(FileSystemArtifactStore, store)
    selected = revocation_fx.revocation_corpus(predecessor=credential_corpus)
    plan = replace(
        credential_plan,
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=credential_corpus,
        adjudicator_registry=(
            credential_runner_fx.adjudication_fx.adjudicator_registry()
        ),
        issuer_registry=credential_runner_fx.credential_fx.issuer_registry(),
        credential_policy=credential_runner_fx.credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        ledger=revocation_fx.revocation_ledger(),
        attestations=(credential_runner_fx.credential_fx.credential(),),
        adjudication=credential_runner_fx.adjudication_fx.adjudication(),
        events=(revocation_fx.suspension_event(),),
        evaluated_at="2026-08-03T19:54:50Z",
    )
    return (
        store,
        plan,
        selected,
        credential_corpus,
        adjudication_corpus,
        witness_receipt,
    )


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    revocation_evaluated_at: str = "2026-08-03T19:54:50Z",
    credential_evaluated_at: str = "2026-08-03T19:55:00Z",
    adjudication_evaluated_at: str = "2026-08-03T19:55:30Z",
    adjudication_completed_at: str = "2026-08-03T19:56:00Z",
    credential_completed_at: str = "2026-08-03T19:56:30Z",
    completed_at: str = "2026-08-03T19:56:45Z",
):
    (
        store,
        plan,
        selected,
        credential_corpus,
        adjudication_corpus,
        witness_receipt,
    ) = prepare_revocation_store(tmp_path, run_id=run_id)
    runner = RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=plan,
        corpus=selected,
        credential_corpus=credential_corpus,
        adjudication_corpus=adjudication_corpus,
        witness_registry=credential_runner_fx.witness_fx.witness_registry(),
        witness_policy=credential_runner_fx.witness_fx.witness_policy(),
        witness_attestations=credential_runner_fx.witness_fx.witness_attestations(),
        head_checkpoint=credential_runner_fx.checkpoint(),
        adjudicator_registry=(
            credential_runner_fx.adjudication_fx.adjudicator_registry()
        ),
        adjudication_policy=(
            credential_runner_fx.adjudication_fx.adjudication_policy()
        ),
        adjudication=credential_runner_fx.adjudication_fx.adjudication(),
        issuer_registry=credential_runner_fx.credential_fx.issuer_registry(),
        credential_policy=credential_runner_fx.credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        revocation_ledger=revocation_fx.revocation_ledger(),
        revocation_events=(revocation_fx.suspension_event(),),
        witness_receipt=witness_receipt,
        checkpoint_executor=None,
        experiment_run_id=run_id,
        witness_evaluated_at="2026-08-03T19:53:30Z",
        revocation_evaluated_at=revocation_evaluated_at,
        credential_evaluated_at=credential_evaluated_at,
        adjudication_evaluated_at=adjudication_evaluated_at,
        adjudication_completed_at=adjudication_completed_at,
        credential_completed_at=credential_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def test_active_status_delegates_exact_pr32_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="witness-conflict-revocation-execute",
    )
    assert receipt.status is CheckpointConflictWitnessRevocationRunnerStatus.VERIFIED
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.credential_receipt is not None
    assert receipt.credential_receipt.adjudication_receipt is not None
    assert (
        receipt.verified_checks
        == CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS
    )
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    validate_schema(FINAL_SCHEMA, final)


def test_effective_suspension_abstains_before_pr32_or_pr31(tmp_path: Path) -> None:
    run_id = "witness-conflict-revocation-suspended"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        revocation_evaluated_at="2027-01-01T00:00:00Z",
        credential_evaluated_at="2027-01-01T00:00:01Z",
        adjudication_evaluated_at="2027-01-01T00:00:02Z",
        adjudication_completed_at="2027-01-01T00:00:03Z",
        credential_completed_at="2027-01-01T00:00:04Z",
        completed_at="2027-01-01T00:00:05Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.adjudication_outcome is None
    assert receipt.credential_receipt is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    for artifact_id in (
        (
            f"{run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-decision"
        ),
        (
            f"{run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudication-decision"
        ),
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(artifact_id)
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    validate_schema(FINAL_SCHEMA, final)


def test_revocation_evaluation_after_credential_is_structural_failure(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        CheckpointConflictWitnessRevocationExperimentError,
    ) as captured:
        execute(
            tmp_path,
            run_id="witness-conflict-revocation-late",
            revocation_evaluated_at="2026-08-03T19:55:01Z",
        )
    assert captured.value.stage is CheckpointConflictWitnessRevocationRunnerStage.PREFLIGHT
