from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from test_adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
)
from test_adjudicator_checkpoint_conflict_revocation_checkpoint_witness_attestation import (
    prepare_witness_store,
    witness_attestations,
    witness_corpus,
    witness_policy,
    witness_registry,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_conflict_witness_adjudicator_credential import (
    CheckpointConflictWitnessAdjudicatorCredentialError,
    CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
    load_checkpoint_conflict_witness_adjudicator_credential_evidence,
    persist_checkpoint_conflict_witness_adjudicator_credential_corpus,
    validate_checkpoint_conflict_witness_adjudicator_credentials,
)
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)

adjudication_fx = import_module(
    "test_adjudicator_checkpoint_conflict_revocation_checkpoint_"
    "witness_conflict_adjudication"
)

ROOT = Path(__file__).parents[1]
ISSUER_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-revocation-witness-conflict-"
    "adjudicator-credential-issuer-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-revocation-witness-conflict-"
    "adjudicator-credential-policy.v0.1.0.json"
)
ATTESTATION_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation/"
    "witness-conflict-adjudicator-credential.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.10.0.json"
)
ISSUER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-issuer-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-attestation.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / (
    "checkpoint-conflict-revocation-witness-conflict-adjudicator-"
    "credential-bound-corpus.schema.json"
)


def issuer_registry(
    document: dict[str, Any] | None = None,
) -> CredentialIssuerRegistrySnapshot:
    return CredentialIssuerRegistrySnapshot.from_document(
        document or load_document(ISSUER_PATH)
    )


def credential_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialPolicySnapshot:
    return AdjudicatorCredentialPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def credential(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialAttestationSnapshot:
    return AdjudicatorCredentialAttestationSnapshot.from_document(
        document or load_document(ATTESTATION_PATH)
    )


def corpus(
    document: dict[str, Any] | None = None,
) -> CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot:
    return CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH),
        checkpoint_predecessor=checkpoint_corpus(),
        witness_predecessor=witness_corpus(),
        adjudication_predecessor=adjudication_fx.corpus(),
    )


def plan_for(
    selected: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
    | None = None,
):
    bound = selected or corpus()
    return replace(
        adjudication_fx.plan_for(adjudication_fx.corpus()),
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
    )


def validate(
    *,
    selected: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
    | None = None,
    selected_credential: AdjudicatorCredentialAttestationSnapshot | None = None,
    evaluated_at: str = "2026-08-03T19:55:00Z",
):
    bound = selected or corpus()
    return validate_checkpoint_conflict_witness_adjudicator_credentials(
        plan=plan_for(bound),
        corpus=bound,
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(selected_credential or credential(),),
        adjudication=adjudication_fx.adjudication(),
        evaluated_at=evaluated_at,
    )


def prepare_credential_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_witness_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    adjudication_corpus = adjudication_fx.corpus()
    adjudication_plan = replace(
        prepared[-2],
        corpus_ref=adjudication_corpus.reference(),
        content_ids=adjudication_corpus.content_ids,
    )
    adjudication_fx.persist_adjudication_corpus(
        store,
        plan=adjudication_plan,
        corpus=adjudication_corpus,
        predecessor_corpus=prepared[-1],
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        head_checkpoint=checkpoint(),
        witness_attestations=witness_attestations(),
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        adjudication_policy=adjudication_fx.adjudication_policy(),
        adjudication=adjudication_fx.adjudication(),
        evaluated_at="2026-08-03T19:55:30Z",
    )
    selected = corpus()
    plan = replace(
        adjudication_plan,
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_conflict_witness_adjudicator_credential_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=adjudication_corpus,
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(credential(),),
        adjudication=adjudication_fx.adjudication(),
        evaluated_at="2026-08-03T19:55:00Z",
    )
    return (*prepared[:-2], plan, selected)


def test_fixed_graph_schemas_and_active_credential() -> None:
    selected = corpus()
    report = validate()
    assert selected.reference().artifact_hash == (
        "sha256:1ef073d0b8af20d4ea511f7828a0f90d753d532a1c46b3d6bd36e8a90df21b0f"
    )
    assert selected.predecessor_corpus_ref == adjudication_fx.corpus().reference()
    assert report.outcome is CredentialDecisionOutcome.EXECUTE
    assert report.credentials[0].adjudicator_id == (
        "adjudicator.synthetic.checkpoint-conflict-revocation-"
        "checkpoint-witness-conflict"
    )
    assert report.adjudication_ref == adjudication_fx.adjudication().reference()
    validate_schema(ISSUER_SCHEMA, load_document(ISSUER_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(ATTESTATION_SCHEMA, load_document(ATTESTATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_expired_credential_abstains_without_rewriting_adjudication() -> None:
    report = validate(evaluated_at="2027-08-03T19:54:30Z")
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.triggered
    assert "credential-expired" in report.credentials[0].abstention.reasons
    assert report.adjudication_ref == adjudication_fx.adjudication().reference()


def test_identity_revision_drift_is_structural_failure() -> None:
    attestation_document = load_document(ATTESTATION_PATH)
    attestation_document["identity_revision"] = "synthetic-adjudicator@9.9.9"
    attestation_document["subject_reference"] = (
        "witness-conflict-adjudicator:"
        "adjudicator.synthetic.checkpoint-conflict-revocation-"
        "checkpoint-witness-conflict@synthetic-adjudicator@9.9.9"
    )
    altered = credential(attestation_document)
    corpus_document = deepcopy(load_document(CORPUS_PATH))
    entry = corpus_document[
        "checkpoint_conflict_revocation_witness_conflict_"
        "adjudicator_credentials"
    ][0]
    entry["identity_revision"] = altered.identity_revision
    entry["credential_attestation_ref"] = {
        "artifact_id": altered.reference().artifact_id,
        "artifact_hash": altered.reference().artifact_hash,
        "canonicalization_version": altered.reference().canonicalization_version,
        "media_type": altered.reference().media_type,
    }
    selected = corpus(corpus_document)
    with pytest.raises(
        CheckpointConflictWitnessAdjudicatorCredentialError,
        match="identity",
    ):
        validate(selected=selected, selected_credential=altered)


def test_storage_reconstruction_is_exact_and_idempotent(tmp_path: Path) -> None:
    prepared = prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    first = load_checkpoint_conflict_witness_adjudicator_credential_evidence(
        store,
        corpus=corpus(),
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=adjudication_fx.adjudication(),
    )
    second = load_checkpoint_conflict_witness_adjudicator_credential_evidence(
        store,
        corpus=corpus(),
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=adjudication_fx.adjudication(),
    )
    assert first == second


def test_contract_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(
        CheckpointConflictWitnessAdjudicatorCredentialError,
        match="unsupported fields",
    ):
        corpus(document)
