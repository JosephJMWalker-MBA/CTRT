from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.serialization import canonical_sha256

contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_closure_checkpoints"
)
ClosurePolicy = vars(contract)[
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointPolicySnapshot"
]
ClosureCorpus = vars(contract)[
    "ClosureCheckpointBoundCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot"
]
load_checkpoint_evidence = vars(contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_conflict_"
    "adjudicator_credential_revocation_closure_checkpoint_evidence"
]
persist_checkpoint_corpus = vars(contract)[
    "persist_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_closure_checkpoint_corpus"
]
validate_closure_checkpoints = vars(contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_closure_checkpoints"
]
revocation_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_ledger"
)
revocation_runner_fx = import_module(
    "test_revocation_gated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_conflict_adjudicator_credential_runner"
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-"
    "conflict-adjudicator-credential-revocation-closure-checkpoint-policy."
    "v0.1.0.json"
)
CLOSURE_ROOT = revocation_fx.EVENT_PATH.parent / (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-checkpoints"
)
CHECKPOINT_PATH = CLOSURE_ROOT / (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-genesis-checkpoint.json"
)
LOG_PATH = CLOSURE_ROOT / (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.32.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-checkpoint-policy.schema.json"
)
CHECKPOINT_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-ledger-checkpoint.schema.json"
)
LOG_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-checkpoint-log.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-checkpoint-bound-corpus."
    "schema.json"
)


def closure_policy(document: dict[str, Any] | None = None) -> Any:
    return ClosurePolicy.from_document(document or load_document(POLICY_PATH))


def checkpoint(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationLedgerCheckpointSnapshot:
    return AdjudicatorCredentialRevocationLedgerCheckpointSnapshot.from_document(
        document or load_document(CHECKPOINT_PATH)
    )


def checkpoint_log(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationCheckpointLogSnapshot:
    return AdjudicatorCredentialRevocationCheckpointLogSnapshot.from_document(
        document or load_document(LOG_PATH)
    )


def closure_corpus(
    document: dict[str, Any] | None = None,
    *,
    predecessor: Any | None = None,
) -> Any:
    selected = predecessor or revocation_fx.revocation_corpus()
    return ClosureCorpus.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=selected,
    )


def closure_plan(selected: Any | None = None):
    bound = selected or closure_corpus()
    return replace(
        revocation_fx.revocation_plan(),
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def verify(*, verified_at: str = "2026-08-03T19:59:22Z"):
    return validate_closure_checkpoints(
        plan=closure_plan(),
        corpus=closure_corpus(),
        policy=closure_policy(),
        log=checkpoint_log(),
        ledger=revocation_fx.revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at=verified_at,
        revocation_evaluated_at="2026-08-03T19:59:23Z",
    )


def prepare_closure_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    prepared = revocation_runner_fx.prepare_revocation_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = closure_corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        policy=closure_policy(),
        log=checkpoint_log(),
        ledger=revocation_fx.revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T19:59:22Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_closure_graph_and_schemas() -> None:
    selected = closure_corpus()
    report = verify()
    policy = closure_policy()
    assert policy.artifact_hash == (
        "sha256:9fe6e27c52e86225f99403eb455cd3dbe631974cf0e0aecd402a21125889274c"
    )
    assert checkpoint().artifact_hash == (
        "sha256:0af1e06a2171d441783c1f34fdbaad43ca294276a80b4851792bc21a5d4c0443"
    )
    assert checkpoint_log().artifact_hash == (
        "sha256:0ba849b730ae32155d7c726ea5999af1208587fe16d336b769c6eeba7ac8b784"
    )
    assert selected.artifact_hash == (
        "sha256:5a33f77334c305a2dfa2dc43711decf08afd68cdb87504d29e897c25f9c512d0"
    )
    assert policy.protected_predecessor_ref == (
        revocation_fx.revocation_corpus().reference()
    )
    assert policy.branch_state == "closed"
    assert policy.automatic_successor_layers_allowed is False
    assert policy.reopen_requires_documented_failure is True
    assert policy.permitted_reopen_trigger == "concrete-unrepresented-failure"
    assert report.checkpoint_count == 1
    assert report.head_sequence_number == 0
    assert report.head_event_count == 1
    assert report.head_event_population_hash == (
        "sha256:72fe6000b56ef23f788f84745b8a873da0a85be038e0baf3cd35e683f8533391"
    )
    assert report.head_checkpoint_ref == checkpoint().reference()
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(CHECKPOINT_SCHEMA, load_document(CHECKPOINT_PATH))
    validate_schema(LOG_SCHEMA, load_document(LOG_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_automatic_successor_layers_are_rejected() -> None:
    document = deepcopy(load_document(POLICY_PATH))
    document["automatic_successor_layers_allowed"] = True
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="forbids automatic successor",
    ):
        closure_policy(document)


def test_closure_checkpoint_event_omission_is_rejected() -> None:
    document = deepcopy(load_document(CHECKPOINT_PATH))
    document["event_refs"] = []
    document["event_count"] = 0
    document["event_population_hash"] = canonical_sha256({"event_refs": []})
    changed = checkpoint(document)
    log_document = deepcopy(load_document(LOG_PATH))
    changed_ref = stored_ref_document(changed.reference())
    log_document["checkpoint_refs"] = [changed_ref]
    log_document["head_checkpoint_ref"] = changed_ref
    changed_log = checkpoint_log(log_document)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[
        "current_revocation_conflict_adjudicator_checkpoint_witness_conflict_"
        "adjudicator_credential_revocation_closure_checkpoint_log_ref"
    ]["artifact_hash"] = changed_log.artifact_hash
    corpus_document[
        "current_revocation_conflict_adjudicator_checkpoint_witness_conflict_"
        "adjudicator_credential_revocation_closure_checkpoint_head_ref"
    ] = changed_ref
    changed_corpus = closure_corpus(corpus_document)
    changed_plan = closure_plan(changed_corpus)
    with pytest.raises(AdjudicatorCredentialRevocationCheckpointError):
        validate_closure_checkpoints(
            plan=changed_plan,
            corpus=changed_corpus,
            policy=closure_policy(),
            log=changed_log,
            ledger=revocation_fx.revocation_ledger(),
            checkpoints=(changed,),
            verified_at="2026-08-03T19:59:22Z",
            revocation_evaluated_at="2026-08-03T19:59:23Z",
        )


def test_checkpoint_after_revocation_evaluation_is_rejected() -> None:
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="no later than revocation evaluation",
    ):
        verify(verified_at="2026-08-03T19:59:24Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_closure_store(tmp_path, run_id="closure-rebuild")
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = prepared[2]
    first = load_checkpoint_evidence(
        store,
        corpus=selected,
        policy=closure_policy(),
        log=checkpoint_log(),
    )
    second = load_checkpoint_evidence(
        store,
        corpus=selected,
        policy=closure_policy(),
        log=checkpoint_log(),
    )
    assert first == second
    assert first.checkpoints == (checkpoint(),)
    assert store.get(selected.corpus_id).payload == selected.canonical_payload


def test_schema_rejects_extra_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
