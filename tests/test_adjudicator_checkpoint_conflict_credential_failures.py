# ruff: noqa: I001, F401, UP035
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    AdjudicatorCheckpointConflictCredentialError,
    load_adjudicator_checkpoint_conflict_credential_evidence,
    persist_credential_bound_adjudicator_checkpoint_conflict_corpus,
    validate_adjudicator_checkpoint_conflict_credentials,
)
from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from test_adjudicator_checkpoint_conflict_credential_attestation import (
    ATTESTATION_PATH,
    CORPUS_PATH,
    FINAL_SCHEMA,
    ISSUER_PATH,
    POLICY_PATH,
    adjudication_corpus,
    conflict_adjudication,
    conflict_adjudicator_registry,
    corpus,
    credential,
    credential_policy,
    frozen_plan,
    issuer_registry,
    load_document,
    prepare_adjudication_store,
    validate_schema,
)


def _stored_ref(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def _versioned_ref(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


def test_not_yet_valid_credential_is_governed_abstention() -> None:
    report = validate_adjudicator_checkpoint_conflict_credentials(
        plan=frozen_plan(),
        corpus=corpus(),
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(credential(),),
        adjudication=conflict_adjudication(),
        evaluated_at="2026-08-03T16:21:59Z",
    )
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == ("credential-not-yet-valid",)


def test_suspended_credential_is_governed_abstention() -> None:
    attestation_document = load_document(ATTESTATION_PATH)
    attestation_document["status"] = "suspended"
    suspended = credential(attestation_document)

    corpus_document = load_document(CORPUS_PATH)
    corpus_document["adjudicator_checkpoint_conflict_adjudicator_credentials"][0][
        "credential_attestation_ref"
    ] = _stored_ref(suspended.reference())
    selected = corpus(corpus_document)
    plan = replace(
        frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )

    report = validate_adjudicator_checkpoint_conflict_credentials(
        plan=plan,
        corpus=selected,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(suspended,),
        adjudication=conflict_adjudication(),
        evaluated_at="2026-08-03T16:23:00Z",
    )
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == (
        "credential-status:suspended",
    )


def test_inactive_issuer_is_governed_abstention_when_graph_is_coherent() -> None:
    issuer_document = load_document(ISSUER_PATH)
    issuer_document["issuers"][0]["active"] = False
    inactive_issuer = issuer_registry(issuer_document)

    policy_document = load_document(POLICY_PATH)
    policy_document["issuer_registry_ref"] = _versioned_ref(
        inactive_issuer.reference()
    )
    selected_policy = credential_policy(policy_document)

    corpus_document = load_document(CORPUS_PATH)
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_issuer_registry_ref"
    ] = _versioned_ref(inactive_issuer.reference())
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_policy_ref"
    ] = _versioned_ref(selected_policy.reference())
    selected = corpus(corpus_document)
    plan = replace(
        frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )

    report = validate_adjudicator_checkpoint_conflict_credentials(
        plan=plan,
        corpus=selected,
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=inactive_issuer,
        credential_policy=selected_policy,
        attestations=(credential(),),
        adjudication=conflict_adjudication(),
        evaluated_at="2026-08-03T16:23:00Z",
    )
    assert report.outcome is CredentialDecisionOutcome.ABSTAIN
    assert report.credentials[0].abstention.reasons == (
        "credential-issuer-inactive",
    )


def test_issuer_revision_drift_is_structural_failure() -> None:
    attestation_document = load_document(ATTESTATION_PATH)
    attestation_document["issuer_revision"] = (
        "synthetic-adjudicator-checkpoint-witness-conflict-governance@9.9.9"
    )
    altered = credential(attestation_document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document["adjudicator_checkpoint_conflict_adjudicator_credentials"][0][
        "credential_attestation_ref"
    ] = _stored_ref(altered.reference())
    selected = corpus(corpus_document)
    plan = replace(
        frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )

    with pytest.raises(
        AdjudicatorCheckpointConflictCredentialError,
        match="issuer revision",
    ):
        validate_adjudicator_checkpoint_conflict_credentials(
            plan=plan,
            corpus=selected,
            adjudicator_registry=conflict_adjudicator_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            attestations=(altered,),
            adjudication=conflict_adjudication(),
            evaluated_at="2026-08-03T16:23:00Z",
        )


def test_publication_rejects_expired_credential_without_manifest(
    tmp_path: Path,
) -> None:
    prepared = prepare_adjudication_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = corpus()
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )

    with pytest.raises(
        AdjudicatorCheckpointConflictCredentialError,
        match="requires eligible attestations",
    ):
        persist_credential_bound_adjudicator_checkpoint_conflict_corpus(
            store,
            plan=plan,
            corpus=selected,
            predecessor_corpus=adjudication_corpus(),
            adjudicator_registry=conflict_adjudicator_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            attestations=(credential(),),
            adjudication=conflict_adjudication(),
            evaluated_at="2027-08-03T16:22:00Z",
        )
    with pytest.raises(ArtifactNotFoundError):
        store.get(selected.reference().artifact_id)


def test_loader_fails_closed_when_attestation_is_missing(tmp_path: Path) -> None:
    prepared = prepare_adjudication_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = corpus()
    store.append(issuer_registry().artifact())
    store.append(credential_policy().artifact())
    store.append(selected.artifact())

    with pytest.raises(ArtifactNotFoundError):
        load_adjudicator_checkpoint_conflict_credential_evidence(
            store,
            corpus=selected,
            adjudicator_registry=conflict_adjudicator_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            adjudication=conflict_adjudication(),
        )


def test_final_schema_rejects_vote_aggregation_field() -> None:
    document = {
        "final_id": (
            "run:adjudicator-checkpoint-conflict-adjudicator-"
            "credential-abstention"
        ),
        "experiment_run_id": "run",
        "status": "verified",
        "credential_outcome": "abstain",
        "adjudicator_checkpoint_witness_outcome": None,
        "conflict_adjudication_outcome": None,
        "adjudicator_revocation_outcome": None,
        "adjudicator_credential_outcome": None,
        "reviewer_checkpoint_witness_outcome": None,
        "reviewer_witness_adjudication_outcome": None,
        "reviewer_revocation_outcome": None,
        "terminal_outcome": "abstain",
        "experiment_id": "experiment",
        "experiment_version": "0.1.0",
        "content_ids": ["content-001", "content-002"],
        "credential_corpus_ref": _stored_ref(credential().reference()),
        "adjudicator_registry_ref": _stored_ref(credential().reference()),
        "issuer_registry_ref": _stored_ref(credential().reference()),
        "credential_policy_ref": _stored_ref(credential().reference()),
        "credential_attestation_refs": [_stored_ref(credential().reference())],
        "adjudication_ref": _stored_ref(credential().reference()),
        "credential_decision_ref": _stored_ref(credential().reference()),
        "adjudicated_conflict_final_ref": None,
        "verified_checks": ["credential-checked"],
        "completed_at": "2026-08-03T16:23:00Z",
        "vote_count": 2,
    }
    with pytest.raises(ValidationError):
        validate_schema(FINAL_SCHEMA, document)
