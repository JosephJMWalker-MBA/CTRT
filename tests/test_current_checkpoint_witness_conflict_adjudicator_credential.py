from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema
from test_current_checkpoint_witness_conflict_adjudication import (
    adjudication_corpus,
    conflict_adjudication,
    conflict_adjudicator_registry,
    prepare_adjudication_store,
)

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.current_checkpoint_witness_conflict_adjudicator_credential import (
    CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
    CredentialError,
    load_current_checkpoint_witness_conflict_credential_evidence,
    persist_current_checkpoint_witness_conflict_credential_corpus,
    validate_current_checkpoint_witness_conflict_credentials,
)
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)

ROOT = Path(__file__).parents[1]
ISSUER_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "issuer-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "policy.v0.1.0.json"
)
CREDENTIAL_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-"
    "checkpoint-witness-conflict-adjudicator-credential-revocation/"
    "current-checkpoint-witness-conflict-adjudicator-credential.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.20.0.json"
)
ISSUER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-issuer-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-policy.schema.json"
CREDENTIAL_SCHEMA = ROOT / "schemas" / "adjudicator-credential-attestation.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-checkpoint-witness-conflict-adjudicator-credential-bound-"
    "corpus.schema.json"
)
CREDENTIAL_KEY = "current_checkpoint_witness_conflict_adjudicator_credentials"
PREDECESSOR_KEY = (
    "current_checkpoint_witness_conflict_adjudicator_credential_"
    "predecessor_corpus_ref"
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
        document or load_document(CREDENTIAL_PATH)
    )


def corpus(
    document: dict[str, Any] | None = None,
    *,
    predecessor: Any | None = None,
) -> CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot:
    return CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or adjudication_corpus(),
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def bound_to(
    selected_credential: AdjudicatorCredentialAttestationSnapshot,
    *,
    identity_revision: str | None = None,
) -> CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot:
    document = deepcopy(load_document(CORPUS_PATH))
    document["corpus_id"] += ".test"
    document["corpus_version"] = "1.20.1-test"
    entry = document[CREDENTIAL_KEY][0]
    entry["credential_attestation_ref"] = stored_ref_document(
        selected_credential.reference()
    )
    if identity_revision is not None:
        entry["identity_revision"] = identity_revision
    return corpus(document)


def frozen_plan(
    selected: CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot | None = None,
):
    bound = selected or corpus()
    from test_current_checkpoint_witness_conflict_adjudication import plan_for

    return replace(
        plan_for(bound.corpus),
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
    )


def validate(
    *,
    selected_credential: AdjudicatorCredentialAttestationSnapshot | None = None,
    selected_corpus: (
        CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot | None
    ) = None,
    evaluated_at: str = "2026-08-03T19:58:11Z",
):
    selected = selected_credential or credential()
    bound = selected_corpus or corpus()
    if bound.credential_entries[0].credential_attestation_ref != selected.reference():
        bound = bound_to(selected)
    return validate_current_checkpoint_witness_conflict_credentials(
        plan=frozen_plan(bound),
        corpus=bound,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(selected,),
        adjudication=conflict_adjudication(),
        evaluated_at=evaluated_at,
    )


def prepare_credential_store(
    tmp_path: Path,
    *,
    run_id: str = "current-conflict-credential-reconstruction",
) -> tuple[Any, ...]:
    prepared = prepare_adjudication_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_current_checkpoint_witness_conflict_credential_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(credential(),),
        adjudication=conflict_adjudication(),
        evaluated_at="2026-08-03T19:58:11Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_credential_graph_and_schemas() -> None:
    selected = corpus()
    report = validate()
    assert issuer_registry().artifact_hash == (
        "sha256:1c13ed78af7964464be460350c06ce32097e2e58c718c0f2b6a2d4fff6296fe8"
    )
    assert credential_policy().artifact_hash == (
        "sha256:ef4953a1c33f07e4e31aab2b5a0f7784c99354b147286a9c45bdd24ecd899526"
    )
    assert credential().artifact_hash == (
        "sha256:6c538f6ac902906ebbea7e59155e183fdaf8dd0ec37eb2848d1bd7f07433efa6"
    )
    assert selected.artifact_hash == (
        "sha256:8cba471df7daa5664a87822fb8fad5a68b10b19422129ee266224f153ede5f20"
    )
    assert selected.predecessor_corpus_ref == adjudication_corpus().reference()
    assert report.outcome is CredentialDecisionOutcome.EXECUTE
    assert report.adjudication_ref == conflict_adjudication().reference()
    validate_schema(ISSUER_SCHEMA, load_document(ISSUER_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(CREDENTIAL_SCHEMA, load_document(CREDENTIAL_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_not_yet_valid_credential_abstains() -> None:
    report = validate(evaluated_at="2026-08-03T19:58:08Z")
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == ("credential-not-yet-valid",)


def test_expired_credential_abstains_at_half_open_boundary() -> None:
    report = validate(evaluated_at="2027-08-03T19:58:09Z")
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == ("credential-expired",)


def test_suspended_credential_abstains_without_rewriting_adjudication() -> None:
    document = deepcopy(load_document(CREDENTIAL_PATH))
    document["status"] = "suspended"
    selected = credential(document)
    report = validate(selected_credential=selected)
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == (
        "credential-status:suspended",
    )
    assert report.adjudication_ref == conflict_adjudication().reference()


def test_substituted_identity_revision_is_structural_failure() -> None:
    document = deepcopy(load_document(CREDENTIAL_PATH))
    revision = "synthetic-substituted-current-conflict-adjudicator@9.9.9"
    document["identity_revision"] = revision
    document["subject_reference"] = (
        "witness-conflict-adjudicator:"
        f"{document['adjudicator_id']}@{revision}"
    )
    selected = credential(document)
    selected_corpus = bound_to(selected, identity_revision=revision)
    with pytest.raises(CredentialError, match="credential entry identity differs"):
        validate(
            selected_credential=selected,
            selected_corpus=selected_corpus,
        )


def test_predecessor_drift_is_rejected() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document[PREDECESSOR_KEY]["artifact_hash"] = "sha256:" + "0" * 64
    with pytest.raises(CredentialError, match="exact 1.19.0"):
        corpus(document)


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(
        CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot,
        prepared[2],
    )
    first = load_current_checkpoint_witness_conflict_credential_evidence(
        store,
        corpus=selected,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=conflict_adjudication(),
    )
    second = load_current_checkpoint_witness_conflict_credential_evidence(
        store,
        corpus=selected,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=conflict_adjudication(),
    )
    assert first == second
    assert first.attestations == (credential(),)


def test_schema_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
