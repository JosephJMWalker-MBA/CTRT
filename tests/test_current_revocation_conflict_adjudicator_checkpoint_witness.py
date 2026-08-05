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
    "test_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
)
contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_witness"
)

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-witness-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-witness-policy.v0.1.0.json"
)
ATTESTATION_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-checkpoint-"
    "witness-conflict-adjudicator-credential-revocation/checkpoints/witnesses/"
    "current-revocation-conflict-adjudicator-revocation-checkpoints/witnesses"
)
ATTESTATION_PATHS = tuple(
    ATTESTATION_ROOT / f"{name}-attestation.json"
    for name in ("alpha", "beta", "gamma")
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.28.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-registry.schema.json"
)
POLICY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-policy.schema.json"
)
ATTESTATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-attestation.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-revocation-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-bound-corpus.schema.json"
)
ATTESTATION_KEY = (
    "current_revocation_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_witness_attestation_refs"
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
    snapshot = contract.WitnessBoundCurrentRevocationConflictAdjudicatorCheckpointCorpusSnapshot
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
    evaluated_at: str = "2026-08-03T19:59:03Z",
):
    corpus = selected_corpus or witness_corpus()
    return contract.validate_current_revocation_conflict_adjudicator_checkpoint_witnesses(
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
    contract.persist_current_revocation_conflict_adjudicator_checkpoint_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        attestations=witness_attestations(),
        evaluated_at="2026-08-03T19:59:03Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_current_witness_graph_and_schemas() -> None:
    selected = witness_corpus()
    report = validate()
    assert witness_registry().artifact_hash == (
        "sha256:4ed633c94ad1329890b76a7511333f64d6637fe950993d1c7d1bbd0cc0d05c3b"
    )
    assert witness_policy().artifact_hash == (
        "sha256:0f03b5ac7191ded32e6d945b99bacf4d108efda37390a67bc0d226ea71b95c4f"
    )
    assert tuple(item.artifact_hash for item in witness_attestations()) == (
        "sha256:1c17fdd7b97e84f8be173eef4cdb3f640bfbbaaf10a8a0a4393240f125fa24e5",
        "sha256:8a7a408c9a035f31e0adb2219d4f44e0b83d5b491ca78128f90bfb64603a86ed",
        "sha256:0f33a9982f9d403627b779f4db0ecf4669ea648fc9b29cbdf0c338d66b19b850",
    )
    assert selected.artifact_hash == (
        "sha256:4dce56cbccb761b273f65b5a2538b65ea3b9d62d804151644ddedf0294193b2f"
    )
    assert selected.predecessor_corpus_ref == (
        checkpoint_fx.checkpoint_corpus().reference()
    )
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
    changed_documents[2]["observed_head_ref"]["artifact_hash"] = (
        "sha256:" + "0" * 64
    )
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
    changed_documents[0]["observed_at"] = "2026-08-03T19:58:48Z"
    changed_documents[0]["received_at"] = "2026-08-03T19:58:49Z"
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
    first = contract.load_current_revocation_conflict_adjudicator_checkpoint_witness_evidence(
        store,
        corpus=selected,
        registry=witness_registry(),
        policy=witness_policy(),
    )
    second = contract.load_current_revocation_conflict_adjudicator_checkpoint_witness_evidence(
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
