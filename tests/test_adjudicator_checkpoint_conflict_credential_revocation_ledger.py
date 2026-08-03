from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from test_adjudicator_checkpoint_conflict_credential_attestation import (
    corpus as credential_corpus,
)
from test_adjudicator_checkpoint_conflict_credential_attestation import (
    credential,
    credential_policy,
    frozen_plan,
    issuer_registry,
    prepare_credential_store,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import (
    conflict_adjudication,
    conflict_adjudicator_registry,
    load_document,
)
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    load_adjudicator_checkpoint_conflict_credential_revocation_evidence,
    persist_adjudicator_checkpoint_conflict_credential_revocation_bound_corpus,
    validate_adjudicator_checkpoint_conflict_credential_revocation_ledger,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-conflict-adjudicator-"
    "credential-revocation-policy.v0.1.0.json"
)
EVENT_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-checkpoints"
    / "adjudicator-checkpoint-fork-suspension-event.json"
)
LEDGER_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-checkpoints"
    / "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-ledger.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.6.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-policy.schema.json"
EVENT_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-event.schema.json"
LEDGER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-ledger.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-bound-corpus.schema.json"
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
    predecessor: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot | None = None,
) -> RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot:
    return RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or credential_corpus(),
    )


def revocation_plan():
    selected = revocation_corpus()
    return replace(
        frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )


def validate(*, evaluated_at: str = "2026-08-03T18:23:00Z"):
    return validate_adjudicator_checkpoint_conflict_credential_revocation_ledger(
        plan=revocation_plan(),
        corpus=revocation_corpus(),
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential(),),
        adjudication=conflict_adjudication(),
        events=(suspension_event(),),
        evaluated_at=evaluated_at,
    )


def test_fixed_graph_and_schemas() -> None:
    selected = revocation_corpus()
    report = validate()
    assert selected.reference().artifact_hash == (
        "sha256:d8c50b7a6ef0250df9bd2b2cc4830aadb45bdf4b8c7ec6696b8e316124822123"
    )
    assert selected.predecessor_corpus_ref == credential_corpus().reference()
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
        "event.synthetic.adjudicator-checkpoint-fork.suspension.v0.1.0",
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
    document = deepcopy(load_document(EVENT_PATH))
    document["issuer_revision"] = "synthetic-issuer@9.9.9"
    altered = suspension_event(document)
    with pytest.raises(AdjudicatorCredentialRevocationError, match="issuer"):
        validate_adjudicator_checkpoint_conflict_credential_revocation_ledger(
            plan=revocation_plan(),
            corpus=revocation_corpus(),
            adjudicator_registry=conflict_adjudicator_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=revocation_ledger(),
            attestations=(credential(),),
            adjudication=conflict_adjudication(),
            events=(altered,),
            evaluated_at="2026-08-03T18:23:00Z",
        )


def test_manifest_last_persistence_and_exact_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = cast(
        CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
        prepared[-1],
    )
    selected = revocation_corpus(predecessor=predecessor)
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    first = persist_adjudicator_checkpoint_conflict_credential_revocation_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential(),),
        adjudication=conflict_adjudication(),
        events=(suspension_event(),),
        evaluated_at="2026-08-03T18:23:00Z",
    )
    second = load_adjudicator_checkpoint_conflict_credential_revocation_evidence(
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
