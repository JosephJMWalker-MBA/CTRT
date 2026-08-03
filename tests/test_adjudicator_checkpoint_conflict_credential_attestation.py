# ruff: noqa: I001, F401, UP035
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    AdjudicatorCheckpointConflictCredentialError,
    CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    load_adjudicator_checkpoint_conflict_credential_evidence,
    persist_credential_bound_adjudicator_checkpoint_conflict_corpus,
    validate_adjudicator_checkpoint_conflict_credentials,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import (
    ArtifactNotFoundError,
    FileSystemArtifactStore,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.credentialed_adjudicator_checkpoint_conflict_runner import (
    CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS,
    CheckpointConflictCredentialRunnerStatus,
    CredentialedAdjudicatorCheckpointConflictExperimentRunner,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.witness_conflict_adjudication import WitnessConflictAdjudicationOutcome
from test_adjudicator_checkpoint_witness_attestation import plan_for
from test_adjudicator_checkpoint_witness_conflict_adjudication import (
    adjudicator_witness_policy,
    adjudicator_witness_registry,
    conflict_adjudication,
    conflict_adjudication_policy,
    conflict_adjudicator_registry,
    conflict_attestations,
    corpus as adjudication_corpus,
    load_document,
    prepare_adjudication_store,
)
from test_adjudicator_credential_attestation import (
    credential_policy as prior_adjudicator_credential_policy,
    issuer_registry as prior_adjudicator_issuer_registry,
)
from test_adjudicator_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_log,
    checkpoint_policy,
)
from test_adjudicator_credential_revocation_ledger import (
    revocation_ledger,
    revocation_policy,
)
from test_credential_revocation_checkpoints import (
    checkpoint as reviewer_checkpoint,
    checkpoint_log as reviewer_checkpoint_log,
    policy as reviewer_checkpoint_policy,
    validate_schema,
)
from test_credential_revocation_ledger import policy as reviewer_revocation_policy
from test_extraction_review_adjudication import analyzer_registry, environment, windows
from test_witness_conflict_adjudication import (
    adjudication_policy,
    adjudicator_registry,
    witness_policy,
    witness_registry,
)

ROOT = Path(__file__).parents[1]
ISSUER_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-witness-conflict-adjudicator-"
    "credential-issuer-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-witness-conflict-adjudicator-"
    "credential-policy.v0.1.0.json"
)
ATTESTATION_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-checkpoints"
    / "adjudicator-checkpoint-fork-credential.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.5.0.json"
)
ISSUER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-issuer-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-attestation.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-conflict-adjudicator-credential-bound-corpus.schema.json"
)
DECISION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / (
    "credentialed-adjudicator-checkpoint-conflict-final.schema.json"
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
) -> CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot:
    return CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def frozen_plan():
    selected = corpus()
    base = plan_for(selected.corpus)
    return replace(
        base,
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )


def validate(
    *,
    selected_credential: AdjudicatorCredentialAttestationSnapshot | None = None,
    evaluated_at: str = "2026-08-03T16:23:00Z",
):
    return validate_adjudicator_checkpoint_conflict_credentials(
        plan=frozen_plan(),
        corpus=corpus(),
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(selected_credential or credential(),),
        adjudication=conflict_adjudication(),
        evaluated_at=evaluated_at,
    )


def prepare_credential_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_adjudication_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = corpus()
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
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
        evaluated_at="2026-08-03T16:23:00Z",
    )
    return (*prepared[:-2], plan, selected)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    credential_evaluated_at: str = "2026-08-03T16:23:00Z",
):
    prepared = prepare_credential_store(tmp_path)
    (
        store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        reviewer_issuers,
        reviewer_credentials,
        reviewer_ledger,
        _,
        fixture_analyzers,
        reviewer_witness_records,
        bound_reviewer_adjudication,
        adjudicator_credential,
        _,
        _,
        _,
        _,
        _,
        _,
        plan,
        selected,
    ) = prepared
    runner = CredentialedAdjudicatorCheckpointConflictExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=cast(FileSystemArtifactStore, store),
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate,
        method_registry=methods,
        quality_policy=quality,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        issuer_registry=reviewer_issuers,
        credential_policy=reviewer_credentials,
        revocation_policy=reviewer_revocation_policy(),
        ledger=reviewer_ledger,
        checkpoint_policy=reviewer_checkpoint_policy(),
        checkpoint_log=reviewer_checkpoint_log(),
        checkpoints=(reviewer_checkpoint(),),
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        witness_attestations=reviewer_witness_records,
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=bound_reviewer_adjudication,
        adjudicator_issuer_registry=prior_adjudicator_issuer_registry(),
        adjudicator_credential_policy=prior_adjudicator_credential_policy(),
        adjudicator_credentials=(adjudicator_credential,),
        adjudicator_revocation_policy=revocation_policy(),
        adjudicator_revocation_ledger=revocation_ledger(),
        adjudicator_checkpoint_policy=checkpoint_policy(),
        adjudicator_checkpoint_log=checkpoint_log(),
        adjudicator_checkpoints=(checkpoint(),),
        adjudicator_checkpoint_witness_registry=adjudicator_witness_registry(),
        adjudicator_checkpoint_witness_policy=adjudicator_witness_policy(),
        adjudicator_checkpoint_witness_attestations=conflict_attestations(),
        adjudicator_checkpoint_conflict_adjudicator_registry=(
            conflict_adjudicator_registry()
        ),
        adjudicator_checkpoint_conflict_adjudication_policy=(
            conflict_adjudication_policy()
        ),
        adjudicator_checkpoint_conflict_adjudication=conflict_adjudication(),
        checkpoint_conflict_adjudicator_issuer_registry=issuer_registry(),
        checkpoint_conflict_adjudicator_credential_policy=credential_policy(),
        checkpoint_conflict_adjudicator_credentials=(credential(),),
        corpus=selected,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        checkpoint_conflict_credential_evaluated_at=credential_evaluated_at,
        adjudicator_checkpoint_verified_at="2026-08-03T14:54:00Z",
        adjudicator_witness_evaluated_at="2026-08-03T16:01:00Z",
        adjudicator_checkpoint_conflict_adjudication_evaluated_at=(
            "2026-08-03T16:01:00Z"
        ),
        adjudicator_revocation_evaluated_at="2026-08-03T14:00:00Z",
        adjudicator_credential_evaluated_at="2026-08-03T14:00:00Z",
        checkpoint_verified_at="2026-08-03T14:00:00Z",
        witness_evaluated_at="2026-08-03T14:00:00Z",
        adjudication_evaluated_at="2026-08-03T14:00:00Z",
        revocation_evaluated_at="2026-08-03T14:00:00Z",
        credential_evaluated_at="2026-08-03T14:00:00Z",
        quality_evaluated_at="2026-08-03T14:00:00Z",
        review_evaluated_at="2026-08-03T14:00:00Z",
    )
    return receipt, cast(FileSystemArtifactStore, store)


def test_fixed_graph_schemas_and_credential_decision() -> None:
    report = validate()
    assert report.outcome is CredentialDecisionOutcome.EXECUTE
    assert report.credentials[0].adjudicator_id == (
        "adjudicator.synthetic.adjudicator-checkpoint-fork"
    )
    assert report.adjudication_ref == conflict_adjudication().reference()
    validate_schema(ISSUER_SCHEMA, load_document(ISSUER_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(ATTESTATION_SCHEMA, load_document(ATTESTATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_active_credential_delegates_without_rewriting_conflict(tmp_path: Path) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="checkpoint-conflict-credential-execute",
    )
    assert receipt.status is CheckpointConflictCredentialRunnerStatus.VERIFIED
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.conflict_adjudication_outcome is (
        WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.adjudicated_conflict_receipt is not None
    assert receipt.verified_checks == CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS
    assert store.get(conflict_adjudication().artifact_id).payload == (
        conflict_adjudication().canonical_payload
    )
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.credential_decision_ref.artifact_id).text),
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    validate_schema(FINAL_SCHEMA, final)


def test_expired_credential_abstains_before_conflict_execution(tmp_path: Path) -> None:
    run_id = "checkpoint-conflict-credential-expired"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        credential_evaluated_at="2027-08-03T16:22:00Z",
    )
    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudicated_conflict_receipt is None
    assert receipt.adjudicator_checkpoint_witness_outcome is None
    assert receipt.conflict_adjudication_outcome is None
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            f"{run_id}:"
            "adjudicator-checkpoint-witness-conflict-adjudication-decision"
        )
    assert store.get(conflict_adjudication().artifact_id)


def test_identity_revision_drift_is_structural_failure() -> None:
    document = load_document(ATTESTATION_PATH)
    document["identity_revision"] = "synthetic-adjudicator@9.9.9"
    document["subject_reference"] = (
        "witness-conflict-adjudicator:"
        "adjudicator.synthetic.adjudicator-checkpoint-fork@"
        "synthetic-adjudicator@9.9.9"
    )
    altered = credential(document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document["adjudicator_checkpoint_conflict_adjudicator_credentials"][0][
        "identity_revision"
    ] = altered.identity_revision
    corpus_document["adjudicator_checkpoint_conflict_adjudicator_credentials"][0][
        "credential_attestation_ref"
    ] = {
        "artifact_id": altered.reference().artifact_id,
        "artifact_hash": altered.reference().artifact_hash,
        "canonicalization_version": altered.reference().canonicalization_version,
        "media_type": altered.reference().media_type,
    }
    selected = corpus(corpus_document)
    plan = replace(
        frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    with pytest.raises(
        AdjudicatorCheckpointConflictCredentialError,
        match="identity",
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


def test_storage_reconstruction_is_exact_and_idempotent(tmp_path: Path) -> None:
    prepared = prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    first = load_adjudicator_checkpoint_conflict_credential_evidence(
        store,
        corpus=corpus(),
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=conflict_adjudication(),
    )
    second = load_adjudicator_checkpoint_conflict_credential_evidence(
        store,
        corpus=corpus(),
        adjudicator_registry=conflict_adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=conflict_adjudication(),
    )
    assert first == second
    assert first.attestations == (credential(),)


def test_reused_closed_credential_schema_rejects_private_identity() -> None:
    document = deepcopy(load_document(ATTESTATION_PATH))
    document["real_name"] = "Not permitted"
    with pytest.raises(ValidationError):
        validate_schema(ATTESTATION_SCHEMA, document)


def test_predecessor_is_not_accepted_as_credential_bound_corpus() -> None:
    document = load_document(
        ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.4.0.json"
    )
    with pytest.raises(AdjudicatorCheckpointConflictCredentialError):
        corpus(document)
