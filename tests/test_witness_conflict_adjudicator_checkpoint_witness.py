from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
    prepare_checkpoint_store,
)
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessObservationKind,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness import (
    AdjudicatorCheckpointWitnessError,
    WitnessBoundCheckpointCorpusSnapshot,
    load_witness_evidence,
    persist_witness_corpus,
    validate_witness_attestations,
)

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-witness-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-witness-policy.v0.1.0.json"
)
ATTESTATION_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation-"
    "witness-conflict-adjudicator-credential-revocation"
)
ATTESTATION_PATHS = tuple(
    ATTESTATION_ROOT / f"{name}-attestation.json"
    for name in ("alpha", "beta", "gamma")
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.13.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-attestation.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-bound-corpus.schema.json"
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
) -> WitnessBoundCheckpointCorpusSnapshot:
    return WitnessBoundCheckpointCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or checkpoint_corpus(),
    )


def witness_plan(selected: WitnessBoundCheckpointCorpusSnapshot | None = None):
    corpus = selected or witness_corpus()
    return replace(
        checkpoint_corpus().corpus.reference() and checkpoint_plan_base(),
        corpus_ref=corpus.reference(),
        content_ids=corpus.content_ids,
    )


def checkpoint_plan_base():
    from test_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints import (
        checkpoint_plan,
    )

    return checkpoint_plan()


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def validate(
    *,
    selected_corpus: WitnessBoundCheckpointCorpusSnapshot | None = None,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
    evaluated_at: str = "2026-08-03T19:55:04Z",
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


def prepare_witness_store(tmp_path: Path, *, run_id: str) -> tuple[Any, ...]:
    prepared = prepare_checkpoint_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = witness_corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
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
        evaluated_at="2026-08-03T19:55:04Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_witness_graph_and_schemas() -> None:
    selected = witness_corpus()
    report = validate()
    assert witness_registry().artifact_hash == (
        "sha256:58d9cbadba843fc15ef6a92b2a0b27d1e1ff69ec1fb533b59eceb3de58fcbe60"
    )
    assert witness_policy().artifact_hash == (
        "sha256:a3aef0506da906c030d9b2dce3cc84524ad11e62f7e3852e4640bfeae1e2f66e"
    )
    assert tuple(item.artifact_hash for item in witness_attestations()) == (
        "sha256:af96324d4961dc44d39005765009aae841c199acec7ed37cf9e1e4124614d62f",
        "sha256:3193313a44be680b27309a3fc81868f28db34c6dbfe34dceaa16d997c96d6245",
        "sha256:9f49b590140340b6750d4b9ad6daa5705fb7571c7fec4bedbf9c65f949fad84f",
    )
    assert selected.artifact_hash == (
        "sha256:e03f982b4d1ee04299f165b1a699b9b643ae0aff4650f800f29d97e64557c4f3"
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
    key = (
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_checkpoint_witness_attestation_refs"
    )
    corpus_document[key][2] = stored_ref_document(changed[2].reference())
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
    key = (
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_checkpoint_witness_attestation_refs"
    )
    corpus_document[key][0] = stored_ref_document(changed[0].reference())
    selected = witness_corpus(corpus_document)
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="identity revision"):
        validate(selected_corpus=selected, attestations=changed)


def test_observation_before_checkpoint_publication_is_rejected() -> None:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[0]["observed_at"] = "2026-08-03T19:54:50Z"
    changed_documents[0]["received_at"] = "2026-08-03T19:54:51Z"
    changed = witness_attestations(changed_documents)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    key = (
        "checkpoint_conflict_revocation_witness_conflict_adjudicator_"
        "credential_revocation_checkpoint_witness_attestation_refs"
    )
    corpus_document[key][0] = stored_ref_document(changed[0].reference())
    selected = witness_corpus(corpus_document)
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="predates"):
        validate(selected_corpus=selected, attestations=changed)


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path, run_id="witness-reconstruction")
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(WitnessBoundCheckpointCorpusSnapshot, prepared[2])
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
