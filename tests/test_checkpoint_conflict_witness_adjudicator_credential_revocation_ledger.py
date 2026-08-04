from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore, StoredArtifactRef
from ctrt.checkpoint_conflict_witness_adjudicator_credential import (
    CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
    load_checkpoint_conflict_witness_adjudicator_credential_revocation_evidence,
    persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus,
    validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger,
)
from ctrt.experiments import VersionedArtifactRef
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome

credential_fx = import_module(
    "test_checkpoint_conflict_revocation_witness_conflict_"
    "adjudicator_credential_attestation"
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-revocation-witness-conflict-"
    "adjudicator-credential-revocation-policy.v0.1.0.json"
)
EVENT_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation/"
    "witness-conflict-adjudicator-credential-suspension-event.json"
)
LEDGER_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation/"
    "witness-conflict-adjudicator-credential-revocation-ledger.v0.1.0.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.11.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-policy.schema.json"
EVENT_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-event.schema.json"
LEDGER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-ledger.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / (
    "checkpoint-conflict-revocation-witness-conflict-adjudicator-"
    "credential-revocation-bound-corpus.schema.json"
)


def revocation_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationPolicySnapshot:
    return AdjudicatorCredentialRevocationPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def suspension_event(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationEventSnapshot:
    return AdjudicatorCredentialRevocationEventSnapshot.from_document(
        document or load_document(EVENT_PATH)
    )


def revocation_ledger(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationLedgerSnapshot:
    return AdjudicatorCredentialRevocationLedgerSnapshot.from_document(
        document or load_document(LEDGER_PATH)
    )


def revocation_corpus(
    document: dict[str, Any] | None = None,
    *,
    predecessor: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
    | None = None,
) -> RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot:
    return (
        RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot.from_document(
            document or load_document(CORPUS_PATH),
            predecessor=predecessor or credential_fx.corpus(),
        )
    )


def revocation_plan():
    selected = revocation_corpus()
    return replace(
        credential_fx.plan_for(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )


def stored_ref_document(reference: StoredArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def versioned_ref_document(reference: VersionedArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


def validate(*, evaluated_at: str = "2026-08-03T19:54:50Z"):
    return validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger(
        plan=revocation_plan(),
        corpus=revocation_corpus(),
        adjudicator_registry=credential_fx.adjudication_fx.adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=credential_fx.adjudication_fx.adjudication(),
        events=(suspension_event(),),
        evaluated_at=evaluated_at,
    )


def test_fixed_graph_and_schemas() -> None:
    selected = revocation_corpus()
    report = validate()
    assert selected.reference().artifact_hash == (
        "sha256:33b05c3429a0d8f58bb12a4ad497c1c885a4e23386fc80fa017f8cbe9ccaf280"
    )
    assert selected.predecessor_corpus_ref == credential_fx.corpus().reference()
    assert report.outcome is CredentialDecisionOutcome.EXECUTE
    assert report.credentials[0].effective_status.value == "active"
    assert report.credentials[0].applied_event_ids == ()
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(EVENT_SCHEMA, load_document(EVENT_PATH))
    validate_schema(LEDGER_SCHEMA, load_document(LEDGER_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_future_effective_suspension_preserves_as_of_history() -> None:
    before = validate(evaluated_at="2026-12-31T23:59:59Z")
    after = validate(evaluated_at="2027-01-01T00:00:00Z")
    assert before.outcome is CredentialDecisionOutcome.EXECUTE
    assert before.credentials[0].effective_status.value == "active"
    assert after.outcome is CredentialDecisionOutcome.ABSTAIN
    assert after.credentials[0].base_status.value == "active"
    assert after.credentials[0].effective_status.value == "suspended"
    assert after.credentials[0].applied_event_ids == (
        "event.synthetic.checkpoint-conflict-revocation-witness-conflict-"
        "adjudicator.suspension.v0.1.0",
    )
    assert after.credentials[0].abstention.reasons == (
        "adjudicator-credential-ledger-status:suspended",
    )


def test_manifest_content_order_drift_is_rejected() -> None:
    document = load_document(CORPUS_PATH)
    document["content_ids"] = ["content-003", "content-002", "content-001"]
    with pytest.raises(AdjudicatorCredentialRevocationError, match="content order"):
        revocation_corpus(document)


def test_event_issuer_drift_is_structural_failure() -> None:
    event_document = deepcopy(load_document(EVENT_PATH))
    event_document["issuer_revision"] = "synthetic-issuer@9.9.9"
    altered_event = suspension_event(event_document)

    ledger_document = deepcopy(load_document(LEDGER_PATH))
    ledger_document["event_refs"] = [stored_ref_document(altered_event.reference())]
    altered_ledger = revocation_ledger(ledger_document)

    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_ledger_ref"
    ] = versioned_ref_document(altered_ledger.reference())
    altered_corpus = revocation_corpus(corpus_document)
    altered_plan = replace(
        revocation_plan(),
        corpus_ref=altered_corpus.reference(),
        content_ids=altered_corpus.content_ids,
    )

    with pytest.raises(AdjudicatorCredentialRevocationError, match="issuer"):
        validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger(
            plan=altered_plan,
            corpus=altered_corpus,
            adjudicator_registry=credential_fx.adjudication_fx.adjudicator_registry(),
            issuer_registry=credential_fx.issuer_registry(),
            credential_policy=credential_fx.credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=altered_ledger,
            attestations=(credential_fx.credential(),),
            adjudication=credential_fx.adjudication_fx.adjudication(),
            events=(altered_event,),
            evaluated_at="2026-08-03T19:54:50Z",
        )


def test_manifest_last_persistence_and_exact_reconstruction(tmp_path: Path) -> None:
    prepared = credential_fx.prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = cast(
        CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        prepared[-1],
    )
    selected = revocation_corpus(predecessor=predecessor)
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    first = persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=credential_fx.adjudication_fx.adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=credential_fx.adjudication_fx.adjudication(),
        events=(suspension_event(),),
        evaluated_at="2026-08-03T19:54:50Z",
    )
    second = load_checkpoint_conflict_witness_adjudicator_credential_revocation_evidence(
        store,
        corpus=selected,
        policy=revocation_policy(),
        ledger=revocation_ledger(),
    )
    assert first == second
    assert second.corpus_ref == store.reference(selected.corpus_id)
    assert second.revocation_policy_ref == store.reference(
        revocation_policy().policy_id
    )
    assert second.revocation_ledger_ref == store.reference(
        revocation_ledger().ledger_id
    )
    assert second.event_refs == (suspension_event().reference(),)
    assert store.get(selected.corpus_id).payload == selected.canonical_payload


def test_contract_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(
        AdjudicatorCredentialRevocationError,
        match="unsupported fields",
    ):
        revocation_corpus(document)
