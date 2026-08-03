# ruff: noqa: I001, F401, UP035
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessError,
    WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    load_adjudicator_checkpoint_witness_evidence,
    persist_witness_bound_adjudicator_checkpoint_corpus,
    validate_adjudicator_checkpoint_witness_attestations,
)
from ctrt.adjudicator_checkpoint_witness_runner import (
    ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
    AdjudicatorCheckpointWitnessExperimentRunner,
    AdjudicatorCheckpointWitnessRunnerStatus,
)
from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from test_adjudicator_credential_attestation import (
    credential_policy,
    issuer_registry,
    load_document,
)
from test_adjudicator_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
    checkpoint_log,
    checkpoint_policy,
    prepare_checkpoint_store,
    stored_ref_document,
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
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-witness-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-witness-policy.v0.1.0.json"
)
ATTESTATION_DIR = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.3.0.json"
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
    "adjudicator-checkpoint-witness-bound-corpus.schema.json"
)
DECISION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-decision.schema.json"
)
FINAL_SCHEMA = ROOT / "schemas" / "adjudicator-checkpoint-witness-final.schema.json"


def registry(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessRegistrySnapshot:
    return CheckpointWitnessRegistrySnapshot.from_document(
        document or load_document(REGISTRY_PATH)
    )


def policy(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessPolicySnapshot:
    return CheckpointWitnessPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def attestation(
    name: str,
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessAttestationSnapshot:
    return CheckpointWitnessAttestationSnapshot.from_document(
        document or load_document(ATTESTATION_DIR / f"{name}-attestation.json")
    )


def attestations() -> tuple[CheckpointWitnessAttestationSnapshot, ...]:
    return tuple(attestation(name) for name in ("alpha", "beta", "gamma"))


def corpus(
    document: dict[str, Any] | None = None,
) -> WitnessBoundAdjudicatorCheckpointCorpusSnapshot:
    return WitnessBoundAdjudicatorCheckpointCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def plan_for(bound: WitnessBoundAdjudicatorCheckpointCorpusSnapshot):
    prepared = prepare_checkpoint_store(Path("/tmp/ctrt-unused-plan"))
    return replace(
        prepared[15],
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
    )


def validate(
    *,
    bound: WitnessBoundAdjudicatorCheckpointCorpusSnapshot | None = None,
    witness_registry: CheckpointWitnessRegistrySnapshot | None = None,
    witness_policy: CheckpointWitnessPolicySnapshot | None = None,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
    evaluated_at: str = "2026-08-03T14:56:00Z",
):
    selected = bound or corpus()
    return validate_adjudicator_checkpoint_witness_attestations(
        plan=plan_for(selected),
        corpus=selected,
        registry=witness_registry or registry(),
        policy=witness_policy or policy(),
        head_checkpoint=checkpoint(),
        attestations=witness_attestations or attestations(),
        evaluated_at=evaluated_at,
    )


def conflict_case() -> tuple[
    WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    tuple[CheckpointWitnessAttestationSnapshot, ...],
]:
    selected = list(attestations())
    document = load_document(ATTESTATION_DIR / "gamma-attestation.json")
    document["artifact_id"] = (
        "checkpoint-witness-attestation:"
        "attestation.synthetic.adjudicator-gamma.conflict.v0.1.0"
    )
    document["attestation_id"] = (
        "attestation.synthetic.adjudicator-gamma.conflict.v0.1.0"
    )
    document["observed_head_ref"] = {
        "artifact_id": "adjudicator-checkpoint:synthetic-conflicting-head",
        "artifact_hash": "sha256:" + "0" * 64,
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }
    document["observation_kind"] = "conflicting_head"
    document["note"] = "Synthetic conflicting adjudicator checkpoint head."
    selected[-1] = attestation("gamma", document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document["corpus_id"] = (
        "corpus.synthetic-three-items.adjudicator-checkpoint-witness-bound.conflict"
    )
    corpus_document["corpus_version"] = "1.3.1-test-conflict"
    corpus_document["created_at"] = "2026-08-03T14:57:00Z"
    corpus_document["adjudicator_checkpoint_witness_attestation_refs"] = [
        stored_ref_document(item.reference()) for item in selected
    ]
    return corpus(corpus_document), tuple(selected)


def prepare_witness_store(
    tmp_path: Path,
    *,
    bound: WitnessBoundAdjudicatorCheckpointCorpusSnapshot | None = None,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
) -> tuple[Any, ...]:
    prepared = prepare_checkpoint_store(tmp_path)
    selected = bound or corpus()
    records = witness_attestations or attestations()
    plan = replace(
        prepared[15],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_witness_bound_adjudicator_checkpoint_corpus(
        cast(FileSystemArtifactStore, prepared[0]),
        plan=plan,
        corpus=selected,
        predecessor_corpus=checkpoint_corpus(),
        registry=registry(),
        policy=policy(),
        head_checkpoint=checkpoint(),
        attestations=records,
        evaluated_at="2026-08-03T14:56:00Z",
    )
    return (*prepared, plan, selected, records)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    adjudicator_revocation_evaluated_at: str = "2026-08-03T14:00:00Z",
    bound: WitnessBoundAdjudicatorCheckpointCorpusSnapshot | None = None,
    witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
):
    prepared = prepare_witness_store(
        tmp_path,
        bound=bound,
        witness_attestations=witness_attestations,
    )
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
        bound_adjudication,
        adjudicator_credential,
        _,
        _,
        _,
        plan,
        selected,
        records,
    ) = prepared
    runner = AdjudicatorCheckpointWitnessExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=store,
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
        adjudication=bound_adjudication,
        adjudicator_issuer_registry=issuer_registry(),
        adjudicator_credential_policy=credential_policy(),
        adjudicator_credentials=(adjudicator_credential,),
        adjudicator_revocation_policy=revocation_policy(),
        adjudicator_revocation_ledger=revocation_ledger(),
        adjudicator_checkpoint_policy=checkpoint_policy(),
        adjudicator_checkpoint_log=checkpoint_log(),
        adjudicator_checkpoints=(checkpoint(),),
        adjudicator_checkpoint_witness_registry=registry(),
        adjudicator_checkpoint_witness_policy=policy(),
        adjudicator_checkpoint_witness_attestations=records,
        corpus=selected,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        adjudicator_checkpoint_verified_at="2026-08-03T14:54:00Z",
        adjudicator_witness_evaluated_at="2026-08-03T14:56:00Z",
        adjudicator_revocation_evaluated_at=adjudicator_revocation_evaluated_at,
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


def test_fixed_graph_and_schemas() -> None:
    decision = validate()
    assert decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert all(not item.abstention.triggered for item in decision.observations)
    validate_schema(REGISTRY_SCHEMA, load_document(REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    for name in ("alpha", "beta", "gamma"):
        validate_schema(
            ATTESTATION_SCHEMA,
            load_document(ATTESTATION_DIR / f"{name}-attestation.json"),
        )
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_clean_witness_graph_delegates_and_executes(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path, run_id="adjudicator-witness-clean")
    assert receipt.status is AdjudicatorCheckpointWitnessRunnerStatus.VERIFIED
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.verified_checks == ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.witness_decision_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_two_matches_cannot_outvote_one_conflict() -> None:
    bound, records = conflict_case()
    decision = validate(bound=bound, witness_attestations=records)
    assert decision.outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert [item.observation_kind.value for item in decision.observations] == [
        "matches_head",
        "matches_head",
        "conflicting_head",
    ]
    assert decision.observations[-1].abstention.reasons == (
        "adjudicator-checkpoint-witness-conflicting-head:"
        "witness.synthetic.adjudicator-gamma",
    )


def test_conflict_abstains_before_downstream(tmp_path: Path) -> None:
    bound, records = conflict_case()
    run_id = "adjudicator-witness-conflict"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        bound=bound,
        witness_attestations=records,
    )
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.adjudicator_revocation_outcome is None
    assert receipt.adjudicator_credential_outcome is None
    assert receipt.reviewer_checkpoint_witness_outcome is None
    assert receipt.adjudication_outcome is None
    assert receipt.reviewer_revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    assert store.get(receipt.checkpoint_verification_ref.artifact_id)
    assert store.get(receipt.witness_decision_ref.artifact_id)
    for suffix in (
        "adjudicator-credential-revocation-decision",
        "adjudicator-credential-decision",
        "checkpoint-witness-decision",
        "witness-conflict-adjudication-decision",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(f"{run_id}:{suffix}")


def test_identity_revision_drift_is_rejected() -> None:
    records = list(attestations())
    document = load_document(ATTESTATION_DIR / "alpha-attestation.json")
    document["witness_identity_revision"] = "synthetic-witness@9.9.9"
    records[0] = attestation("alpha", document)
    bound_document = load_document(CORPUS_PATH)
    bound_document["corpus_id"] += ".identity-drift"
    bound_document["corpus_version"] = "1.3.1-test-identity-drift"
    bound_document["adjudicator_checkpoint_witness_attestation_refs"] = [
        stored_ref_document(item.reference()) for item in records
    ]
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="identity revision"):
        validate(bound=corpus(bound_document), witness_attestations=tuple(records))


def test_expected_head_drift_is_rejected() -> None:
    records = list(attestations())
    document = load_document(ATTESTATION_DIR / "beta-attestation.json")
    document["expected_head_ref"]["artifact_hash"] = "sha256:" + "1" * 64
    document["observed_head_ref"]["artifact_hash"] = "sha256:" + "1" * 64
    records[1] = attestation("beta", document)
    bound_document = load_document(CORPUS_PATH)
    bound_document["corpus_id"] += ".head-drift"
    bound_document["corpus_version"] = "1.3.1-test-head-drift"
    bound_document["adjudicator_checkpoint_witness_attestation_refs"] = [
        stored_ref_document(item.reference()) for item in records
    ]
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="expected checkpoint"):
        validate(bound=corpus(bound_document), witness_attestations=tuple(records))


def test_observation_before_publication_is_rejected() -> None:
    records = list(attestations())
    document = load_document(ATTESTATION_DIR / "alpha-attestation.json")
    document["observed_at"] = "2026-08-03T14:50:59Z"
    records[0] = attestation("alpha", document)
    bound_document = load_document(CORPUS_PATH)
    bound_document["corpus_id"] += ".early-observation"
    bound_document["corpus_version"] = "1.3.1-test-early-observation"
    bound_document["adjudicator_checkpoint_witness_attestation_refs"] = [
        stored_ref_document(item.reference()) for item in records
    ]
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="predates"):
        validate(bound=corpus(bound_document), witness_attestations=tuple(records))


def test_attestation_received_after_evaluation_is_rejected() -> None:
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="received after"):
        validate(evaluated_at="2026-08-03T14:55:45Z")


def test_attestation_population_order_is_exact() -> None:
    with pytest.raises(AdjudicatorCheckpointWitnessError, match="population"):
        validate(witness_attestations=tuple(reversed(attestations())))


def test_closed_schemas_reject_vote_score_and_private_identity_fields() -> None:
    for path, schema, field in (
        (REGISTRY_PATH, REGISTRY_SCHEMA, "real_name"),
        (POLICY_PATH, POLICY_SCHEMA, "consensus_percentage"),
        (ATTESTATION_DIR / "alpha-attestation.json", ATTESTATION_SCHEMA, "vote_count"),
    ):
        document = deepcopy(load_document(path))
        document[field] = 3
        with pytest.raises(ValidationError):
            validate_schema(schema, document)


def test_storage_reconstruction_and_idempotence(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    first = load_adjudicator_checkpoint_witness_evidence(
        store,
        corpus=corpus(),
        registry=registry(),
        policy=policy(),
    )
    second = load_adjudicator_checkpoint_witness_evidence(
        store,
        corpus=corpus(),
        registry=registry(),
        policy=policy(),
    )
    assert first == second
    assert first.attestations == attestations()


def test_missing_stored_attestation_fails_loading(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    reference = attestation("beta").reference()
    store._blob_path(reference.artifact_hash).unlink()
    with pytest.raises(ArtifactNotFoundError):
        load_adjudicator_checkpoint_witness_evidence(
            store,
            corpus=corpus(),
            registry=registry(),
            policy=policy(),
        )


def test_downstream_revocation_abstention_preserves_witness_execute(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="adjudicator-witness-downstream-abstention",
        adjudicator_revocation_evaluated_at="2027-01-01T00:00:00Z",
    )
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert store.get(receipt.witness_decision_ref.artifact_id)


def test_predecessor_corpus_is_not_accepted_as_witness_corpus() -> None:
    document = load_document(
        ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.2.0.json"
    )
    with pytest.raises(AdjudicatorCheckpointWitnessError):
        corpus(document)
