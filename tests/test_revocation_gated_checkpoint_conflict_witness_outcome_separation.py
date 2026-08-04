from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_checkpoint_conflict_witness_adjudication_runner import (
    RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner,
)

credential_runner_fx = import_module(
    "test_credentialed_checkpoint_conflict_witness_adjudication_runner"
)
revocation_fx = import_module(
    "test_checkpoint_conflict_witness_adjudicator_credential_"
    "revocation_ledger"
)

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-checkpoint-conflict-witness-adjudication-final.schema.json"
)


def test_revocation_execute_preserves_later_credential_abstention(
    tmp_path: Path,
) -> None:
    run_id = "witness-conflict-revocation-credential-expired"
    store, credential_plan, credential_corpus, adjudication_corpus, witness_receipt = (
        credential_runner_fx.prepare_runner_store(tmp_path, run_id=run_id)
    )
    store = cast(FileSystemArtifactStore, store)

    event_document = deepcopy(load_document(revocation_fx.EVENT_PATH))
    event_document["effective_at"] = "2028-01-01T00:00:00Z"
    future_event = revocation_fx.suspension_event(event_document)

    ledger_document = deepcopy(load_document(revocation_fx.LEDGER_PATH))
    ledger_document["event_refs"] = [
        revocation_fx.stored_ref_document(future_event.reference())
    ]
    future_ledger = revocation_fx.revocation_ledger(ledger_document)

    corpus_document = deepcopy(load_document(revocation_fx.CORPUS_PATH))
    corpus_document[
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_ledger_ref"
    ] = revocation_fx.versioned_ref_document(future_ledger.reference())
    selected = revocation_fx.revocation_corpus(
        corpus_document,
        predecessor=credential_corpus,
    )
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
        ledger=future_ledger,
        attestations=(credential_runner_fx.credential_fx.credential(),),
        adjudication=credential_runner_fx.adjudication_fx.adjudication(),
        events=(future_event,),
        evaluated_at="2026-08-03T19:54:50Z",
    )

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
        revocation_ledger=future_ledger,
        revocation_events=(future_event,),
        witness_receipt=witness_receipt,
        checkpoint_executor=None,
        experiment_run_id=run_id,
        witness_evaluated_at="2026-08-03T19:53:30Z",
        revocation_evaluated_at="2027-08-03T19:54:29Z",
        credential_evaluated_at="2027-08-03T19:54:30Z",
        adjudication_evaluated_at="2027-08-03T19:54:31Z",
        adjudication_completed_at="2027-08-03T19:54:32Z",
        credential_completed_at="2027-08-03T19:54:33Z",
        completed_at="2027-08-03T19:54:34Z",
    )

    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_witness_outcome is None
    assert receipt.resolution_status is None
    assert receipt.adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credential_receipt is not None
    assert (
        receipt.credential_receipt.credential_outcome
        is CredentialDecisionOutcome.ABSTAIN
    )
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
