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

from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessError,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessObservationKind,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)

checkpoint_fx = import_module(
    "test_current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoints"
)
contract = import_module(
    "ctrt.current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_witness"
)

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-policy.v0.1.0.json"
)
ATTESTATION_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-checkpoint-"
    "witness-conflict-adjudicator-credential-revocation/checkpoints/witnesses"
)
ATTESTATION_PATHS = tuple(
    ATTESTATION_ROOT / f"{name}-attestation.json"
    for name in ("alpha", "beta", "gamma")
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.23.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-attestation.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint-witness-bound-corpus.schema.json"
)
ATTESTATION_KEY = (
    "current_checkpoint_witness_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness_attestation_refs"
)


def witness_registry(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessRegistrySnapshot:
    return CheckpointWitnessRegistrySnapshot.from_document(
        document or load_document(REGISTRY_PATH)
    )


def witness_policy(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessPolicySnapshot:
    return CheckpointWitnessPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def witness_attestations(
    documents: tuple[dict[str, Any], ...] | None = None,
) -> tuple[CheckpointWitnessAttestationSnapshot, ...]:
    selected = documents or tuple(load_document(path) for path in ATTESTATION_PATHS)
    return tuple(
        CheckpointWitnessAttestationSnapshot.from_document(document)
        for document in selected
    )


def witness_corpus(
    document: dict[str, Any] | None = None,
    *,
    predecessor: Any | None = None,
) -> Any:
    snapshot = contract.WitnessBoundCurrentConflictAdjudicatorRevocationCheckpointCorpusSnapshot
    return snapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or checkpoint_fx.checkpoint_corpus(),
    )


def witness_plan(selected: Any | None = None):
    corpus = selected or witness_corpus()
    return replace(
        checkpoint_fx.checkpoint_plan(),
        corpus_ref=corpus.reference(),
        content_ids=corpus.content_ids,
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def validate(
    *,
    selected_corpus: Any | None = None,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
    evaluated_at: str = "2026-08-03T19:58:31Z",
):
    corpus = selected_corpus or witness_corpus()
    return contract.validate_current_conflict_adjudicator_revocation_checkpoint_witnesses(
        plan=witness_plan(corpus),
        corpus=corpus,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        attestations=attestations or witness_attestations(),
        evaluated_at=evaluated_at,
    )


def prepare_witness_store(tmp_path: Path, *, run_id: str) -> tuple[Any, ...]:
    prepared = checkpoint_fx.prepare_checkpoint_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = witness_corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    contract.persist_current_conflict_adjudicator_revocation_checkpoint_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        attestations=witness_attestations(),
        evaluated_at="2026-08-03T19:58:31Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_current_witness_graph_and_schemas() -> None:
    selected = witness_corpus()
    report = validate()
    assert witness_registry().artifact_hash == (
        "sha256:2d0fe7764d111f480fd556b62357725d0ba5997e7abcce5dfa7057b398f18eb9"
    )
    assert witness_policy().artifact_hash == (
        "sha256:b9f2a86df193ba17900b1c682b5526002ab775a810bbbf704a2c382c3f36fdab"
    )
    assert tuple(item.artifact_hash for item in witness_attestations()) == (
        "sha256:5971087e0b9cc985b7349f486780c7fbaf1420c2469fa20f0fa8a4d1c19751fc",
        "sha256:f655cfbeff98550eb8fdbb7516fc5e89246e3547a0ae2c8d2cca95a6b6c15945",
        "sha256:1d0d661270308e4d7b13e2e42ecaf0bec9124aff309bc35aa36caab1a597ae36",
    )
    assert selected.artifact_hash == (
        "sha256:73cc89c16ebb72c07ec7731ae1b25c3981681eb590005c8fe66c953facca4666"
    )
    assert selected.predecessor_corpus_ref == checkpoint_fx.checkpoint_corpus().reference()
    assert report.outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert tuple(item.observation_kind for item in report.observations) == (
        CheckpointWitnessObservationKind.MATCHES_HEAD,
        CheckpointWitnessObservationKind.MATCHES_HEAD,
        CheckpointWitnessObservationKind.MATCHES_HEAD,
    )
    validate_schema(REGISTRY_SCHEMA, load_document(REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    for path in ATTESTATION_PATHS:
        validate_schema(ATTESTATION_SCHEMA, load_document(path))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_one_required_conflict_abstains_without_majority_vote() -> None:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed_documents[2]["observation_kind"] = "conflicting_head"
    changed = witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[ATTESTATION_KEY][2] = stored_ref_document(changed[2].reference())
    selected = witness_corpus(corpus_document)
    report = validate(selected_corpus=selected, attestations=changed)
    assert report.outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert tuple(item.abstention.triggered for item in report.observations) == (
        False,
        False,
        True,
    )


def test_identity_revision_drift_is_structural_failure() -> None:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[0]["witness_identity_revision"] = "synthetic-witness@9.9.9"
    changed = witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[ATTESTATION_KEY][0] = stored_ref_document(changed[0].reference())
    selected = witness_corpus(corpus_document)
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="identity revision"):
        validate(selected_corpus=selected, attestations=changed)


def test_observation_before_checkpoint_publication_is_rejected() -> None:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[0]["observed_at"] = "2026-08-03T19:58:17Z"
    changed_documents[0]["received_at"] = "2026-08-03T19:58:18Z"
    changed = witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[ATTESTATION_KEY][0] = stored_ref_document(changed[0].reference())
    selected = witness_corpus(corpus_document)
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="predates"):
        validate(selected_corpus=selected, attestations=changed)


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path, run_id="current-witness-reconstruction")
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = prepared[2]
    first = contract.load_current_conflict_adjudicator_revocation_checkpoint_witness_evidence(
        store,
        corpus=selected,
        registry=witness_registry(),
        policy=witness_policy(),
    )
    second = contract.load_current_conflict_adjudicator_revocation_checkpoint_witness_evidence(
        store,
        corpus=selected,
        registry=witness_registry(),
        policy=witness_policy(),
    )
    assert first == second
    assert first.attestations == witness_attestations()


def test_schema_rejects_extra_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
