from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_conflict_credential_attestation import frozen_plan
from test_adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
    prepare_checkpoint_store,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessObservationKind,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)

witness_contracts = import_module(
    "ctrt.adjudicator_checkpoint_conflict_credential_"
    "revocation_checkpoint_witness_attestation"
)
AdjudicatorCheckpointWitnessError = witness_contracts.AdjudicatorCheckpointWitnessError
WitnessCorpus = (
    witness_contracts.WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot
)
load_witness_evidence = (
    witness_contracts.load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence
)
persist_witness_corpus = (
    witness_contracts.persist_witness_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_corpus
)
validate_witness_attestations = (
    witness_contracts.validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations
)

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-"
    "witness-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-"
    "witness-policy.v0.1.0.json"
)
ATTESTATION_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation"
)
ATTESTATION_PATHS = tuple(
    ATTESTATION_ROOT / f"{name}-attestation.json"
    for name in ("alpha", "beta", "gamma")
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.8.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-attestation.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-conflict-revocation-checkpoint-"
    "witness-bound-corpus.schema.json"
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
    return WitnessCorpus.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or checkpoint_corpus(),
    )


def witness_plan(selected: Any | None = None):
    corpus = selected or witness_corpus()
    return replace(
        frozen_plan(),
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
    evaluated_at: str = "2026-08-03T19:53:30Z",
):
    corpus = selected_corpus or witness_corpus()
    return validate_witness_attestations(
        plan=witness_plan(corpus),
        corpus=corpus,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint(),
        attestations=attestations or witness_attestations(),
        evaluated_at=evaluated_at,
    )


def prepare_witness_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_checkpoint_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[-1]
    selected = witness_corpus(predecessor=predecessor)
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint(),
        attestations=witness_attestations(),
        evaluated_at="2026-08-03T19:53:30Z",
    )
    return (*prepared[:-2], plan, selected)


def test_fixed_witness_graph_and_schemas() -> None:
    selected = witness_corpus()
    report = validate()
    assert selected.reference().artifact_hash == (
        "sha256:3d48f367ce1b1101dd7044bb846da42786e3eb9af55c6de7d9bc9e5545f2479a"
    )
    assert selected.predecessor_corpus_ref == checkpoint_corpus().reference()
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


def test_one_conflict_abstains_without_majority_vote() -> None:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed_documents[2]["observation_kind"] = "conflicting_head"
    changed = witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_attestation_refs"
    ][2] = stored_ref_document(changed[2].reference())
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
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_attestation_refs"
    ][0] = stored_ref_document(changed[0].reference())
    selected = witness_corpus(corpus_document)
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="identity revision"):
        validate(selected_corpus=selected, attestations=changed)


def test_observation_before_checkpoint_publication_is_rejected() -> None:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[0]["observed_at"] = "2026-08-03T19:25:00Z"
    changed_documents[0]["received_at"] = "2026-08-03T19:25:10Z"
    changed = witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_checkpoint_witness_attestation_refs"
    ][0] = stored_ref_document(changed[0].reference())
    selected = witness_corpus(corpus_document)
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="predates"):
        validate(selected_corpus=selected, attestations=changed)


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = prepared[-1]
    first = load_witness_evidence(
        store,
        corpus=selected,
        registry=witness_registry(),
        policy=witness_policy(),
    )
    second = load_witness_evidence(
        store,
        corpus=selected,
        registry=witness_registry(),
        policy=witness_policy(),
    )
    assert first == second
    assert first.attestations == witness_attestations()


def test_manifest_content_order_drift_is_rejected() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["content_ids"] = ["content-003", "content-002", "content-001"]
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="content order"):
        witness_corpus(document)


def test_schema_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
