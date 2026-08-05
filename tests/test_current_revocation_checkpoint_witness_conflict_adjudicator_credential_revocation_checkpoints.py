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
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.serialization import canonical_sha256

contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
)
CheckpointCorpus = vars(contract)[
    "CheckpointBoundCurrentRevocationCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationCorpusSnapshot"
]
load_checkpoint_evidence = vars(contract)[
    "load_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_evidence"
]
persist_checkpoint_corpus = vars(contract)[
    "persist_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "revocation_checkpoint_corpus"
]
validate_current_checkpoints = vars(contract)[
    "validate_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
]
revocation_fx = import_module(
    "test_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_ledger"
)
persist_revocation_corpus = vars(revocation_fx)[
    "persist_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_bound_corpus"
]

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-policy.v0.1.0.json"
)
CHECKPOINT_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-checkpoint-"
    "witness-conflict-adjudicator-credential-revocation/checkpoints/witnesses/"
    "current-revocation-conflict-adjudicator-revocation-checkpoints"
)
CHECKPOINT_PATH = CHECKPOINT_ROOT / (
    "current-revocation-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-genesis-checkpoint.json"
)
LOG_PATH = CHECKPOINT_ROOT / (
    "current-revocation-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.27.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-checkpoint-policy.schema.json"
)
CHECKPOINT_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-ledger-checkpoint.schema.json"
)
LOG_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-checkpoint-log.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-revocation-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-bound-corpus.schema.json"
)


def checkpoint_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationCheckpointPolicySnapshot:
    return AdjudicatorCredentialRevocationCheckpointPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


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


def checkpoint_corpus(
    document: dict[str, Any] | None = None,
    *,
    predecessor: Any | None = None,
) -> Any:
    selected = predecessor or revocation_fx.revocation_corpus()
    return CheckpointCorpus.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=selected,
    )


def checkpoint_plan(selected: Any | None = None):
    bound = selected or checkpoint_corpus()
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


def verify(*, verified_at: str = "2026-08-03T19:58:53Z"):
    return validate_current_checkpoints(
        plan=checkpoint_plan(),
        corpus=checkpoint_corpus(),
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_fx.revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at=verified_at,
        revocation_evaluated_at="2026-08-03T19:58:54Z",
    )


def prepare_checkpoint_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    prepared = revocation_fx.credential_fx.prepare_credential_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = revocation_fx.revocation_corpus(predecessor=prepared[2])
    predecessor_plan = replace(
        prepared[1],
        corpus_ref=predecessor.reference(),
        content_ids=predecessor.content_ids,
    )
    persist_revocation_corpus(
        store,
        plan=predecessor_plan,
        corpus=predecessor,
        predecessor_corpus=prepared[2],
        adjudicator_registry=revocation_fx.adjudication_fx.conflict_adjudicator_registry(),
        issuer_registry=revocation_fx.credential_fx.issuer_registry(),
        credential_policy=revocation_fx.credential_fx.credential_policy(),
        revocation_policy=revocation_fx.revocation_policy(),
        ledger=revocation_fx.revocation_ledger(),
        attestations=(revocation_fx.credential_fx.credential(),),
        adjudication=revocation_fx.adjudication_fx.conflict_adjudication(),
        events=(revocation_fx.suspension_event(),),
        evaluated_at="2026-08-03T19:58:46Z",
    )
    selected = checkpoint_corpus(predecessor=predecessor)
    plan = replace(
        predecessor_plan,
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_fx.revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T19:58:53Z",
    )
    return (store, plan, selected, predecessor, *prepared[2:])


def test_fixed_checkpoint_graph_and_schemas() -> None:
    selected = checkpoint_corpus()
    report = verify()
    assert checkpoint_policy().artifact_hash == (
        "sha256:330a38347de9c667b784e04f8dc58e219066d482f9370b0ccb06c2191aa4139f"
    )
    assert checkpoint().artifact_hash == (
        "sha256:4e8e7c6366d806ff51c7acad75050e3245e02067c1106d867cd2d8dc981c6e12"
    )
    assert checkpoint_log().artifact_hash == (
        "sha256:c3a20a2895b80e4cba990842dc9229984fa03399040ba4192dd90f1b4ff42670"
    )
    assert selected.artifact_hash == (
        "sha256:e3e288981f17b308bf5f844cd84633b2e79c67103f6c31b6f13dc89fca672e21"
    )
    assert report.checkpoint_count == 1
    assert report.head_sequence_number == 0
    assert report.head_event_count == 1
    assert report.head_checkpoint_ref == checkpoint().reference()
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(CHECKPOINT_SCHEMA, load_document(CHECKPOINT_PATH))
    validate_schema(LOG_SCHEMA, load_document(LOG_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_checkpoint_omission_is_rejected() -> None:
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
    with pytest.raises(AdjudicatorCredentialRevocationCheckpointError):
        validate_current_checkpoints(
            plan=checkpoint_plan(),
            corpus=checkpoint_corpus(),
            policy=checkpoint_policy(),
            log=changed_log,
            ledger=revocation_fx.revocation_ledger(),
            checkpoints=(changed,),
            verified_at="2026-08-03T19:58:53Z",
            revocation_evaluated_at="2026-08-03T19:58:54Z",
        )


def test_checkpoint_after_revocation_evaluation_is_rejected() -> None:
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="no later than revocation evaluation",
    ):
        verify(verified_at="2026-08-03T19:58:55Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_checkpoint_store(tmp_path, run_id="checkpoint-rebuild")
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = prepared[2]
    first = load_checkpoint_evidence(
        store,
        corpus=selected,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    second = load_checkpoint_evidence(
        store,
        corpus=selected,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    assert first == second
    assert first.checkpoints == (checkpoint(),)


def test_schema_rejects_extra_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
