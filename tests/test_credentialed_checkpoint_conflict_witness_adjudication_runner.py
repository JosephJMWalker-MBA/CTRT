from __future__ import annotations

import json
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import test_adjudicator_checkpoint_conflict_revocation_checkpoint_witness_attestation as witness_fx
from test_adjudicator_checkpoint_conflict_credential_attestation import frozen_plan
from test_adjudicator_checkpoint_conflict_credential_revocation_checkpoints import checkpoint
from test_credential_revocation_checkpoints import validate_schema
from test_witness_gated_adjudicator_checkpoint_conflict_runner import (
    execute as execute_witness,
)

from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.credentialed_checkpoint_conflict_witness_adjudication_runner import (
    CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS,
    CheckpointConflictWitnessCredentialExperimentError,
    CheckpointConflictWitnessCredentialRunnerStage,
    CheckpointConflictWitnessCredentialRunnerStatus,
    CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

adjudication_fx = import_module(
    "test_adjudicator_checkpoint_conflict_revocation_checkpoint_"
    "witness_conflict_adjudication"
)
credential_fx = import_module(
    "test_checkpoint_conflict_revocation_witness_conflict_"
    "adjudicator_credential_attestation"
)

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "credentialed-checkpoint-conflict-witness-adjudication-final.schema.json"
)


def prepare_runner_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    witness_receipt, store = execute_witness(
        tmp_path,
        run_id=run_id,
        revocation_evaluated_at="2026-12-31T23:59:59Z",
    )
    store = cast(FileSystemArtifactStore, store)
    adjudication_corpus = adjudication_fx.corpus()
    adjudication_plan = replace(
        frozen_plan(),
        corpus_ref=adjudication_corpus.reference(),
        content_ids=adjudication_corpus.content_ids,
    )
    adjudication_fx.persist_adjudication_corpus(
        store,
        plan=adjudication_plan,
        corpus=adjudication_corpus,
        predecessor_corpus=witness_fx.witness_corpus(),
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint(),
        witness_attestations=witness_fx.witness_attestations(),
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        adjudication_policy=adjudication_fx.adjudication_policy(),
        adjudication=adjudication_fx.adjudication(),
        evaluated_at="2026-08-03T19:55:30Z",
    )
    selected = credential_fx.corpus()
    plan = replace(
        adjudication_plan,
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    credential_fx.persist_checkpoint_conflict_witness_adjudicator_credential_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=adjudication_corpus,
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        attestations=(credential_fx.credential(),),
        adjudication=adjudication_fx.adjudication(),
        evaluated_at="2026-08-03T19:55:00Z",
    )
    return store, plan, selected, adjudication_corpus, witness_receipt


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    credential_evaluated_at: str = "2026-08-03T19:55:00Z",
    adjudication_evaluated_at: str = "2026-08-03T19:55:30Z",
    adjudication_completed_at: str = "2026-08-03T19:56:00Z",
    completed_at: str = "2026-08-03T19:56:30Z",
):
    store, plan, selected, adjudication_corpus, witness_receipt = (
        prepare_runner_store(tmp_path, run_id=run_id)
    )
    runner = CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner(
        artifact_store=store
    )
    receipt = runner.run(
        plan=plan,
        corpus=selected,
        adjudication_corpus=adjudication_corpus,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        witness_attestations=witness_fx.witness_attestations(),
        head_checkpoint=checkpoint(),
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        adjudication_policy=adjudication_fx.adjudication_policy(),
        adjudication=adjudication_fx.adjudication(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        credentials=(credential_fx.credential(),),
        witness_receipt=witness_receipt,
        checkpoint_executor=None,
        experiment_run_id=run_id,
        witness_evaluated_at="2026-08-03T19:53:30Z",
        credential_evaluated_at=credential_evaluated_at,
        adjudication_evaluated_at=adjudication_evaluated_at,
        adjudication_completed_at=adjudication_completed_at,
        completed_at=completed_at,
    )
    return receipt, store


def test_active_credential_delegates_exact_pr31_lifecycle(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="witness-conflict-credential-execute",
    )
    assert receipt.status is CheckpointConflictWitnessCredentialRunnerStatus.VERIFIED
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.adjudication_receipt is not None
    assert receipt.adjudication_receipt.checkpoint_receipt is not None
    assert (
        receipt.verified_checks
        == CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_expired_credential_abstains_before_pr31_execution(tmp_path: Path) -> None:
    run_id = "witness-conflict-credential-expired"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        credential_evaluated_at="2027-08-03T19:54:30Z",
        adjudication_evaluated_at="2027-08-03T19:55:00Z",
        adjudication_completed_at="2027-08-03T19:56:00Z",
        completed_at="2027-08-03T19:56:30Z",
    )
    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.adjudication_outcome is None
    assert receipt.adjudication_receipt is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert store.get(receipt.credential_decision_ref.artifact_id)
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            f"{run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudication-decision"
        )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_not_yet_valid_credential_abstains_before_pr31_execution(
    tmp_path: Path,
) -> None:
    receipt, _ = execute(
        tmp_path,
        run_id="witness-conflict-credential-not-yet-valid",
        credential_evaluated_at="2026-08-03T19:54:20Z",
    )
    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.adjudication_receipt is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN


def test_credential_evaluation_after_adjudication_is_structural_failure(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        CheckpointConflictWitnessCredentialExperimentError,
    ) as captured:
        execute(
            tmp_path,
            run_id="witness-conflict-credential-late",
            credential_evaluated_at="2026-08-03T19:55:45Z",
        )
    assert captured.value.stage is CheckpointConflictWitnessCredentialRunnerStage.PREFLIGHT
