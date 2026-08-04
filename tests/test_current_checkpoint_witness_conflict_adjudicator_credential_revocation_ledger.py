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
from ctrt.current_checkpoint_witness_conflict_adjudicator_credential import (
    CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
)
from ctrt.current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger import (
    RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
    load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence,
    persist_current_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus,
    validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger,
)
from ctrt.experiments import VersionedArtifactRef
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome

credential_fx = import_module(
    "test_current_checkpoint_witness_conflict_adjudicator_credential"
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-policy.v0.1.0.json"
)
EVIDENCE_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-"
    "checkpoint-witness-conflict-adjudicator-credential-revocation"
)
EVENT_PATH = EVIDENCE_ROOT / (
    "current-checkpoint-witness-conflict-adjudicator-credential-suspension-event.json"
)
LEDGER_PATH = EVIDENCE_ROOT / (
    "current-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "ledger.v0.1.0.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.21.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-policy.schema.json"
EVENT_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-event.schema.json"
LEDGER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-ledger.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "bound-corpus.schema.json"
)
PREFIX = "current_checkpoint_witness_conflict_adjudicator_credential_revocation"


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
    predecessor: CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot
    | None = None,
) -> RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot:
    snapshot = (
        RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
    )
    return snapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or credential_fx.corpus(),
    )


def revocation_plan(
    selected: RevocationBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
    | None = None,
):
    bound = selected or revocation_corpus()
    return replace(
        credential_fx.frozen_plan(),
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
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


def validate(*, evaluated_at: str = "2026-08-03T19:58:16Z"):
    return validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger(
        plan=revocation_plan(),
        corpus=revocation_corpus(),
        adjudicator_registry=credential_fx.conflict_adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=credential_fx.conflict_adjudication(),
        events=(suspension_event(),),
        evaluated_at=evaluated_at,
    )


def test_fixed_graph_and_schemas() -> None:
    selected = revocation_corpus()
    report = validate()
    assert revocation_policy().artifact_hash == (
        "sha256:04430a4444d931e9e7e1793c3d3e05bbb9f18912d0e5daa15224ea1c261181a8"
    )
    assert suspension_event().artifact_hash == (
        "sha256:86fe5a56df406791385c432080c36cdc84620686a359d7edfd155ed41d3ec720"
    )
    assert revocation_ledger().artifact_hash == (
        "sha256:38345155c8550fa4d5bdb16b786039c5aac6904071862ec09a770e09f25d7960"
    )
    assert selected.reference().artifact_hash == (
        "sha256:b6a3065ffb517dda9fb498404021371f7d5b320af144842c3f7d2453c99ace1e"
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
        "event.synthetic.current-checkpoint-witness-conflict-adjudicator."
        "suspension.v0.1.0",
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
    corpus_document[f"{PREFIX}_ledger_ref"] = versioned_ref_document(
        altered_ledger.reference()
    )
    altered_corpus = revocation_corpus(corpus_document)
    altered_plan = replace(
        revocation_plan(),
        corpus_ref=altered_corpus.reference(),
        content_ids=altered_corpus.content_ids,
    )
    with pytest.raises(AdjudicatorCredentialRevocationError, match="issuer"):
        validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger(
            plan=altered_plan,
            corpus=altered_corpus,
            adjudicator_registry=credential_fx.conflict_adjudicator_registry(),
            issuer_registry=credential_fx.issuer_registry(),
            credential_policy=credential_fx.credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=altered_ledger,
            attestations=(credential_fx.credential(),),
            adjudication=credential_fx.conflict_adjudication(),
            events=(altered_event,),
            evaluated_at="2026-08-03T19:58:16Z",
        )


def test_event_recorded_after_ledger_freeze_is_rejected() -> None:
    event_document = deepcopy(load_document(EVENT_PATH))
    event_document["recorded_at"] = "2026-08-03T19:58:15Z"
    altered_event = suspension_event(event_document)
    with pytest.raises(AdjudicatorCredentialRevocationError, match="recording chronology"):
        validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger(
            plan=revocation_plan(),
            corpus=revocation_corpus(),
            adjudicator_registry=credential_fx.conflict_adjudicator_registry(),
            issuer_registry=credential_fx.issuer_registry(),
            credential_policy=credential_fx.credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=revocation_ledger(),
            attestations=(credential_fx.credential(),),
            adjudication=credential_fx.conflict_adjudication(),
            events=(altered_event,),
            evaluated_at="2026-08-03T19:58:16Z",
        )


def test_manifest_last_persistence_and_exact_reconstruction(tmp_path: Path) -> None:
    prepared = credential_fx.prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = cast(
        CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
        prepared[2],
    )
    selected = revocation_corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist = (
        persist_current_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus
    )
    first = persist(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=credential_fx.conflict_adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=credential_fx.conflict_adjudication(),
        events=(suspension_event(),),
        evaluated_at="2026-08-03T19:58:16Z",
    )
    second = load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence(
        store,
        corpus=selected,
        policy=revocation_policy(),
        ledger=revocation_ledger(),
    )
    assert first == second
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
