from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_witness_conflict_adjudication import (
    load_document,
)
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)

adjudication_fx = import_module(
    "test_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudication"
)
contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential"
)
CredentialCorpus = vars(contract)[
    "CredentialBoundCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessCorpusSnapshot"
]
CredentialError = vars(contract)["CredentialError"]
load_evidence = vars(contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "credential_evidence"
]
persist_corpus = vars(contract)[
    "persist_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "credential_corpus"
]
validate_credentials = vars(contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "credentials"
]

ROOT = Path(__file__).parents[1]
ISSUER_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-"
    "conflict-adjudicator-credential-issuer-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-"
    "conflict-adjudicator-credential-policy.v0.1.0.json"
)
CREDENTIAL_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-checkpoints"
    / "witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation"
    / "checkpoints"
    / "witnesses"
    / "current-revocation-conflict-adjudicator-revocation-checkpoints"
    / "witnesses"
    / (
        "current-revocation-conflict-adjudicator-checkpoint-witness-"
        "conflict-adjudicator-credential.json"
    )
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.30.0.json"
)
ISSUER_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-issuer-registry.schema.json"
)
POLICY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-policy.schema.json"
)
CREDENTIAL_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-attestation.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-bound-corpus.schema.json"
)
PREFIX = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential"
)
CREDENTIAL_KEY = f"{PREFIX}s"
PREDECESSOR_KEY = f"{PREFIX}_predecessor_corpus_ref"


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
) -> Any:
    return CredentialCorpus.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or adjudication_fx.adjudication_corpus(),
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
) -> Any:
    document = deepcopy(load_document(CORPUS_PATH))
    document["corpus_id"] += ".test"
    document["corpus_version"] = "1.30.1-test"
    entry = document[CREDENTIAL_KEY][0]
    entry["credential_attestation_ref"] = stored_ref_document(
        selected_credential.reference()
    )
    if identity_revision is not None:
        entry["identity_revision"] = identity_revision
    return corpus(document)


def frozen_plan(selected: Any | None = None):
    bound = selected or corpus()
    return replace(
        adjudication_fx.plan_for(bound.corpus),
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
    )


def validate(
    *,
    selected_credential: AdjudicatorCredentialAttestationSnapshot | None = None,
    selected_corpus: Any | None = None,
    evaluated_at: str = "2026-08-03T19:59:14Z",
):
    selected = selected_credential or credential()
    bound = selected_corpus or corpus()
    if (
        bound.credential_entries[0].credential_attestation_ref
        != selected.reference()
    ):
        bound = bound_to(selected)
    return validate_credentials(
        plan=frozen_plan(bound),
        corpus=bound,
        adjudicator_registry=(
            adjudication_fx.conflict_adjudicator_registry()
        ),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(selected,),
        adjudication=adjudication_fx.conflict_adjudication(),
        evaluated_at=evaluated_at,
    )


def prepare_credential_store(
    tmp_path: Path,
    *,
    run_id: str = "current-conflict-adjudicator-credential-reconstruction",
) -> tuple[Any, ...]:
    prepared = adjudication_fx.prepare_adjudication_store(
        tmp_path,
        run_id=run_id,
    )
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[2]
    selected = corpus(predecessor=predecessor)
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=(
            adjudication_fx.conflict_adjudicator_registry()
        ),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(credential(),),
        adjudication=adjudication_fx.conflict_adjudication(),
        evaluated_at="2026-08-03T19:59:14Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_credential_graph_and_schemas() -> None:
    selected = corpus()
    report = validate()
    assert issuer_registry().artifact_hash == (
        "sha256:764b0e77ee7b1dc2bea93b896402002c5b81b6a785d05b5ba4aafa8ee05fda8c"
    )
    assert credential_policy().artifact_hash == (
        "sha256:a5074d6dab65673e899297bb3e1243dc013c88ba75d05845a1ad3b409c885a4a"
    )
    assert credential().artifact_hash == (
        "sha256:26759637a9f3a4b8e8cc2996a071abdbb9f4cbccd7c0cf873344f7a48f4885b6"
    )
    assert selected.artifact_hash == (
        "sha256:a9ece983cac8c81dee0bfd61df4cd396ea03eb1df339c0ef6cc43e0604b39209"
    )
    assert (
        selected.predecessor_corpus_ref
        == adjudication_fx.adjudication_corpus().reference()
    )
    assert report.outcome is CredentialDecisionOutcome.EXECUTE
    assert (
        report.adjudication_ref
        == adjudication_fx.conflict_adjudication().reference()
    )
    validate_schema(ISSUER_SCHEMA, load_document(ISSUER_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(CREDENTIAL_SCHEMA, load_document(CREDENTIAL_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_not_yet_valid_credential_abstains() -> None:
    report = validate(evaluated_at="2026-08-03T19:59:11Z")
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == (
        "credential-not-yet-valid",
    )


def test_expired_credential_abstains_at_half_open_boundary() -> None:
    report = validate(evaluated_at="2027-08-03T19:59:12Z")
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == (
        "credential-expired",
    )


def test_suspended_credential_preserves_adjudication() -> None:
    document = deepcopy(load_document(CREDENTIAL_PATH))
    document["status"] = "suspended"
    selected = credential(document)
    report = validate(selected_credential=selected)
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == (
        "credential-status:suspended",
    )
    assert (
        report.adjudication_ref
        == adjudication_fx.conflict_adjudication().reference()
    )


def test_substituted_identity_revision_is_structural_failure() -> None:
    document = deepcopy(load_document(CREDENTIAL_PATH))
    revision = "synthetic-substituted-current-adjudicator@9.9.9"
    document["identity_revision"] = revision
    document["subject_reference"] = (
        "witness-conflict-adjudicator:"
        f"{document['adjudicator_id']}@{revision}"
    )
    selected = credential(document)
    selected_corpus = bound_to(
        selected,
        identity_revision=revision,
    )
    with pytest.raises(
        CredentialError,
        match="credential entry identity differs",
    ):
        validate(
            selected_credential=selected,
            selected_corpus=selected_corpus,
        )


def test_predecessor_drift_is_rejected() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document[PREDECESSOR_KEY]["artifact_hash"] = "sha256:" + "0" * 64
    with pytest.raises(CredentialError, match="exact 1.29.0"):
        corpus(document)


def test_manifest_last_persistence_and_reconstruction(
    tmp_path: Path,
) -> None:
    prepared = prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = prepared[2]
    first = load_evidence(
        store,
        corpus=selected,
        adjudicator_registry=(
            adjudication_fx.conflict_adjudicator_registry()
        ),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=adjudication_fx.conflict_adjudication(),
    )
    second = load_evidence(
        store,
        corpus=selected,
        adjudicator_registry=(
            adjudication_fx.conflict_adjudicator_registry()
        ),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=adjudication_fx.conflict_adjudication(),
    )
    assert first == second
    assert first.attestations == (credential(),)


def test_schema_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
