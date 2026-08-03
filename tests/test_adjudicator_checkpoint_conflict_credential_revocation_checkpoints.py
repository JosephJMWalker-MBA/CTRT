from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import test_adjudicator_checkpoint_conflict_credential_attestation as credential_fx
from jsonschema import ValidationError
from test_adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    revocation_corpus,
    revocation_ledger,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema
from test_revocation_gated_adjudicator_checkpoint_conflict_runner import (
    prepare_revocation_store,
)

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence,
    persist_checkpoint_bound_adjudicator_checkpoint_conflict_credential_revocation_corpus,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.serialization import canonical_sha256

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-checkpoint-policy.v0.1.0.json"
)
CHECKPOINT_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoints/"
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-genesis-checkpoint.json"
)
LOG_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoints/"
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.7.0.json"
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
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
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
) -> CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot:
    snapshot = (
        CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot
    )
    return snapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or revocation_corpus(),
    )


def checkpoint_plan():
    selected = checkpoint_corpus()
    base = replace(
        credential_fx.frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    return base


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def verify(*, verified_at: str = "2026-08-03T19:27:00Z"):
    return validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
        plan=checkpoint_plan(),
        corpus=checkpoint_corpus(),
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at=verified_at,
    )


def prepare_checkpoint_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_revocation_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[-1]
    selected = checkpoint_corpus(predecessor=predecessor)
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_bound_adjudicator_checkpoint_conflict_credential_revocation_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T19:27:00Z",
    )
    return (*prepared[:-2], plan, selected)


def test_fixed_checkpoint_graph_and_schemas() -> None:
    selected = checkpoint_corpus()
    report = verify()
    assert selected.reference().artifact_hash == (
        "sha256:26311c6a5da00c7e6ea3986406be48ca8d3087ccf3f41f07c783cd8db88635fb"
    )
    assert selected.predecessor_corpus_ref == revocation_corpus().reference()
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
        validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
            plan=checkpoint_plan(),
            corpus=checkpoint_corpus(),
            policy=checkpoint_policy(),
            log=changed_log,
            ledger=revocation_ledger(),
            checkpoints=(changed,),
            verified_at="2026-08-03T19:27:00Z",
        )


def test_future_checkpoint_verification_is_rejected() -> None:
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="before publication",
    ):
        verify(verified_at="2026-08-03T19:25:00Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_checkpoint_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(
        CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
        prepared[-1],
    )
    first = load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
        store,
        corpus=selected,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    second = load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
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
