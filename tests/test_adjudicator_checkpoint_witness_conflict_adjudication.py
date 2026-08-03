# ruff: noqa: I001, F401, UP035
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicated_adjudicator_checkpoint_witness_runner import (
    ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
    AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner,
    AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus,
)
from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
    AdjudicatorCheckpointWitnessConflictAdjudicationError,
    load_adjudicator_checkpoint_witness_conflict_adjudication_evidence,
    persist_adjudication_bound_adjudicator_checkpoint_witness_corpus,
    validate_adjudicator_checkpoint_witness_conflict_adjudication,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from test_adjudicator_checkpoint_witness_attestation import (
    ATTESTATION_DIR,
    attestation,
    corpus as witness_corpus,
    plan_for,
    policy as adjudicator_witness_policy,
    prepare_witness_store,
    registry as adjudicator_witness_registry,
)
from test_adjudicator_credential_attestation import (
    credential_policy,
    issuer_registry,
    load_document,
)
from test_adjudicator_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_log,
    checkpoint_policy,
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
    "synthetic-adjudicator-checkpoint-witness-conflict-adjudicator-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-witness-conflict-adjudication-policy.v0.1.0.json"
)
CONFLICT_PATH = ATTESTATION_DIR / "gamma-conflict-attestation.json"
ADJUDICATION_PATH = ATTESTATION_DIR / "gamma-conflict-adjudication.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.4.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudicator-registry.schema.json"
)
POLICY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudication-policy.schema.json"
)
ADJUDICATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudication.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-adjudication-bound-corpus.schema.json"
)
DECISION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudication-decision.schema.json"
)
FINAL_SCHEMA = ROOT / "schemas" / (
    "adjudicated-adjudicator-checkpoint-witness-final.schema.json"
)


def conflict_attestation(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessAttestationSnapshot:
    return CheckpointWitnessAttestationSnapshot.from_document(
        document or load_document(CONFLICT_PATH)
    )


def conflict_attestations() -> tuple[CheckpointWitnessAttestationSnapshot, ...]:
    return (attestation("alpha"), attestation("beta"), conflict_attestation())


def conflict_adjudicator_registry(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicatorRegistrySnapshot:
    return WitnessConflictAdjudicatorRegistrySnapshot.from_document(
        document or load_document(REGISTRY_PATH)
    )


def conflict_adjudication_policy(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationPolicySnapshot:
    return WitnessConflictAdjudicationPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def conflict_adjudication(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationSnapshot:
    return WitnessConflictAdjudicationSnapshot.from_document(
        document or load_document(ADJUDICATION_PATH)
    )


def corpus(
    document: dict[str, Any] | None = None,
) -> AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot:
    return AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def validate(
    *,
    bound: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot | None = None,
    adjudicators: WitnessConflictAdjudicatorRegistrySnapshot | None = None,
    rules: WitnessConflictAdjudicationPolicySnapshot | None = None,
    decision_record: WitnessConflictAdjudicationSnapshot | None = None,
    evaluated_at: str = "2026-08-03T16:01:00Z",
):
    selected = bound or corpus()
    plan = plan_for(selected.corpus)
    witness_decision = validate_adjudicator_checkpoint_witness_attestations(
        plan=plan,
        corpus=selected.corpus,
        registry=adjudicator_witness_registry(),
        policy=adjudicator_witness_policy(),
        head_checkpoint=checkpoint(),
        attestations=conflict_attestations(),
        evaluated_at="2026-08-03T16:01:00Z",
    )
    return validate_adjudicator_checkpoint_witness_conflict_adjudication(
        plan=plan,
        corpus=selected,
        witness_registry=adjudicator_witness_registry(),
        witness_policy=adjudicator_witness_policy(),
        adjudicator_registry=adjudicators or conflict_adjudicator_registry(),
        adjudication_policy=rules or conflict_adjudication_policy(),
        witness_decision=witness_decision,
        adjudication=decision_record or conflict_adjudication(),
        evaluated_at=evaluated_at,
    )


def prepare_adjudication_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_witness_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = corpus()
    plan = replace(
        prepared[17],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_adjudication_bound_adjudicator_checkpoint_witness_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=witness_corpus(),
        witness_registry=adjudicator_witness_registry(),
        witness_policy=adjudicator_witness_policy(),
        head_checkpoint=checkpoint(),
        witness_attestations=conflict_attestations(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
        evaluated_at="2026-08-03T16:01:00Z",
    )
    return (*prepared, plan, selected)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    adjudicator_revocation_evaluated_at: str = "2026-08-03T14:00:00Z",
):
    prepared = prepare_adjudication_store(tmp_path)
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
    runner = AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner(
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
        adjudicator_issuer_registry=issuer_registry(),
        adjudicator_credential_policy=credential_policy(),
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
        corpus=selected,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        adjudicator_checkpoint_verified_at="2026-08-03T14:54:00Z",
        adjudicator_witness_evaluated_at="2026-08-03T16:01:00Z",
        adjudicator_checkpoint_conflict_adjudication_evaluated_at=(
            "2026-08-03T16:01:00Z"
        ),
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


def test_fixed_graph_schemas_and_resolved_decision() -> None:
    report = validate()
    assert report.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert report.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert report.outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert len(report.fork_evidence) == 1
    assert report.preserved_dissent[0].witness_id == (
        "witness.synthetic.adjudicator-gamma"
    )
    validate_schema(REGISTRY_SCHEMA, load_document(REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(ADJUDICATION_SCHEMA, load_document(ADJUDICATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_resolved_conflict_preserves_witness_abstention_and_executes(
    tmp_path: Path,
) -> None:
    receipt, store = execute(tmp_path, run_id="adjudicator-checkpoint-conflict-resolved")
    assert receipt.status is AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus.VERIFIED
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.witness_receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.witness_receipt.checkpoint_receipt is None
    assert receipt.conflict_adjudication_outcome is (
        WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.checkpoint_receipt is not None
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.verified_checks == (
        ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS
    )
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.adjudication_decision_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_pending_conflict_abstains() -> None:
    document = load_document(ADJUDICATION_PATH)
    document.update(
        {
            "status": "pending",
            "adjudicator_id": None,
            "adjudicator_identity_revision": None,
            "selected_head_ref": None,
            "preserved_dissent": [],
            "rationale": "Synthetic conflict is pending authorized review.",
        }
    )
    report = validate(decision_record=conflict_adjudication(document))
    assert report.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert report.resolution_status is WitnessConflictResolutionStatus.PENDING


def test_unresolved_conflict_abstains_and_preserves_dissent() -> None:
    document = load_document(ADJUDICATION_PATH)
    document.update(
        {
            "status": "unresolved",
            "selected_head_ref": None,
            "rationale": "Available evidence does not authorize resolution.",
        }
    )
    report = validate(decision_record=conflict_adjudication(document))
    assert report.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert report.resolution_status is WitnessConflictResolutionStatus.UNRESOLVED
    assert report.preserved_dissent


def test_resolved_adjudication_cannot_select_alternate_head() -> None:
    document = load_document(ADJUDICATION_PATH)
    document["selected_head_ref"] = deepcopy(document["fork_evidence"][0]["observed_head_ref"])
    with pytest.raises(
        AdjudicatorCheckpointWitnessConflictAdjudicationError,
        match="select declared checkpoint head",
    ):
        validate(decision_record=conflict_adjudication(document))


def test_adjudicator_identity_revision_drift_is_rejected() -> None:
    document = load_document(ADJUDICATION_PATH)
    document["adjudicator_identity_revision"] = "synthetic-adjudicator@9.9.9"
    with pytest.raises(
        AdjudicatorCheckpointWitnessConflictAdjudicationError,
        match="identity revision",
    ):
        validate(decision_record=conflict_adjudication(document))


def test_missing_preserved_dissent_is_rejected() -> None:
    document = load_document(ADJUDICATION_PATH)
    document["preserved_dissent"] = []
    with pytest.raises(ValueError, match="preserve dissent"):
        conflict_adjudication(document)


def test_closed_schemas_reject_vote_score_and_private_identity_fields() -> None:
    for path, schema, field in (
        (REGISTRY_PATH, REGISTRY_SCHEMA, "real_name"),
        (POLICY_PATH, POLICY_SCHEMA, "consensus_percentage"),
        (ADJUDICATION_PATH, ADJUDICATION_SCHEMA, "vote_count"),
    ):
        document = deepcopy(load_document(path))
        document[field] = 3
        with pytest.raises(ValidationError):
            validate_schema(schema, document)


def test_storage_reconstruction_is_exact_and_idempotent(tmp_path: Path) -> None:
    prepared = prepare_adjudication_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    first = load_adjudicator_checkpoint_witness_conflict_adjudication_evidence(
        store,
        corpus=corpus(),
        witness_registry=adjudicator_witness_registry(),
        witness_policy=adjudicator_witness_policy(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
    )
    second = load_adjudicator_checkpoint_witness_conflict_adjudication_evidence(
        store,
        corpus=corpus(),
        witness_registry=adjudicator_witness_registry(),
        witness_policy=adjudicator_witness_policy(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
    )
    assert first == second
    assert first.witness_evidence.attestations == conflict_attestations()


def test_downstream_revocation_abstention_preserves_resolved_adjudication(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="adjudicator-checkpoint-conflict-downstream-abstention",
        adjudicator_revocation_evaluated_at="2027-01-01T00:00:00Z",
    )
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.conflict_adjudication_outcome is (
        WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert store.get(receipt.adjudication_decision_ref.artifact_id)


def test_predecessor_corpus_is_not_accepted_as_adjudication_corpus() -> None:
    document = load_document(
        ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.3.0.json"
    )
    with pytest.raises(AdjudicatorCheckpointWitnessConflictAdjudicationError):
        corpus(document)
