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

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
    load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence,
    persist_checkpoint_bound_checkpoint_witness_conflict_adjudicator_credential_revocation_corpus,
    validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints,
)
from ctrt.serialization import canonical_sha256

lower_fx = import_module(
    "test_revocation_gated_checkpoint_witness_conflict_adjudication_runner"
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-checkpoint-policy.v0.1.0.json"
)
CHECKPOINT_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoints/"
    "witness-conflict-adjudicator-checkpoint-fork-credential-revocation-"
    "genesis-checkpoint.json"
)
LOG_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoints/"
    "witness-conflict-adjudicator-checkpoint-fork-credential-revocation-"
    "checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.17.0.json"
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
    "checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint-bound-corpus.schema.json"
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
) -> (
    CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
):
    selected_predecessor = predecessor or lower_fx.revocation_fx.revocation_corpus()
    snapshot = (
        CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
    )
    return snapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=selected_predecessor,
    )


def checkpoint_plan():
    selected = checkpoint_corpus()
    return replace(
        lower_fx.credential_fx.frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def verify(*, verified_at: str = "2026-08-03T19:57:45Z"):
    return (
        validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints(
            plan=checkpoint_plan(),
            corpus=checkpoint_corpus(),
            policy=checkpoint_policy(),
            log=checkpoint_log(),
            ledger=lower_fx.revocation_fx.revocation_ledger(),
            checkpoints=(checkpoint(),),
            verified_at=verified_at,
            revocation_evaluated_at="2026-08-03T19:57:46Z",
        )
    )


def prepare_checkpoint_store(
    tmp_path: Path,
    *,
    run_id: str,
) -> tuple[Any, ...]:
    prepared = lower_fx.prepare_revocation_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = checkpoint_corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_bound_checkpoint_witness_conflict_adjudicator_credential_revocation_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=lower_fx.revocation_fx.revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T19:57:45Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_checkpoint_graph_and_schemas() -> None:
    selected = checkpoint_corpus()
    report = verify()
    assert checkpoint_policy().artifact_hash == (
        "sha256:ce8fe8e454f9563a613eaeac66b528bf3e2800076e5f47cb0f2a91d11f9daf7f"
    )
    assert checkpoint().artifact_hash == (
        "sha256:245efb3279bc1b10c5ffafa337665a947a8dd86e9693590cccf09a6021d829a2"
    )
    assert checkpoint_log().artifact_hash == (
        "sha256:45e9330da82ddf1295a07cd0f763c1447a9cbfccc716b20f590d94113409aa24"
    )
    assert selected.artifact_hash == (
        "sha256:e801447e9d897baa442effd11f2a1d059624e05d7286ad7ec2bc3761e328849d"
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
        validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints(
            plan=checkpoint_plan(),
            corpus=checkpoint_corpus(),
            policy=checkpoint_policy(),
            log=changed_log,
            ledger=lower_fx.revocation_fx.revocation_ledger(),
            checkpoints=(changed,),
            verified_at="2026-08-03T19:57:45Z",
            revocation_evaluated_at="2026-08-03T19:57:46Z",
        )


def test_checkpoint_after_revocation_evaluation_is_rejected() -> None:
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="no later than revocation evaluation",
    ):
        verify(verified_at="2026-08-03T19:57:47Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_checkpoint_store(tmp_path, run_id="current-checkpoint-rebuild")
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(
        CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
        prepared[2],
    )
    first = (
        load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence(
            store,
            corpus=selected,
            policy=checkpoint_policy(),
            log=checkpoint_log(),
        )
    )
    second = (
        load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence(
            store,
            corpus=selected,
            policy=checkpoint_policy(),
            log=checkpoint_log(),
        )
    )
    assert first == second
    assert first.checkpoints == (checkpoint(),)


def test_schema_rejects_extra_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
