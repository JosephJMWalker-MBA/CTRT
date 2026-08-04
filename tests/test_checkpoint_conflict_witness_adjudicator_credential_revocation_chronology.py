from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module

import pytest
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document

from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationError,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger,
)

credential_fx = import_module(
    "test_checkpoint_conflict_revocation_witness_conflict_"
    "adjudicator_credential_attestation"
)
revocation_fx = import_module(
    "test_checkpoint_conflict_witness_adjudicator_credential_"
    "revocation_ledger"
)


def test_event_recorded_after_ledger_freeze_is_structural_failure() -> None:
    event_document = deepcopy(load_document(revocation_fx.EVENT_PATH))
    event_document["recorded_at"] = "2026-08-03T19:54:44Z"
    altered_event = revocation_fx.suspension_event(event_document)

    ledger_document = deepcopy(load_document(revocation_fx.LEDGER_PATH))
    ledger_document["event_refs"] = [
        revocation_fx.stored_ref_document(altered_event.reference())
    ]
    altered_ledger = revocation_fx.revocation_ledger(ledger_document)

    corpus_document = deepcopy(load_document(revocation_fx.CORPUS_PATH))
    corpus_document[
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_ledger_ref"
    ] = revocation_fx.versioned_ref_document(altered_ledger.reference())
    altered_corpus = revocation_fx.revocation_corpus(corpus_document)
    altered_plan = replace(
        revocation_fx.revocation_plan(),
        corpus_ref=altered_corpus.reference(),
        content_ids=altered_corpus.content_ids,
    )

    with pytest.raises(
        AdjudicatorCredentialRevocationError,
        match="event recording chronology",
    ):
        validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger(
            plan=altered_plan,
            corpus=altered_corpus,
            adjudicator_registry=credential_fx.adjudication_fx.adjudicator_registry(),
            issuer_registry=credential_fx.issuer_registry(),
            credential_policy=credential_fx.credential_policy(),
            revocation_policy=revocation_fx.revocation_policy(),
            ledger=altered_ledger,
            attestations=(credential_fx.credential(),),
            adjudication=credential_fx.adjudication_fx.adjudication(),
            events=(altered_event,),
            evaluated_at="2026-08-03T19:54:50Z",
        )


def test_evaluation_before_successor_publication_is_structural_failure() -> None:
    with pytest.raises(
        AdjudicatorCredentialRevocationError,
        match="policy, ledger, corpus, and evaluation chronology",
    ):
        revocation_fx.validate(evaluated_at="2026-08-03T19:54:47Z")
