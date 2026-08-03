from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import test_adjudicator_checkpoint_conflict_credential_attestation as credential_fx
import test_adjudicator_checkpoint_witness_conflict_adjudication as conflict_fx
import test_adjudicator_credential_attestation as prior_credential_fx
import test_adjudicator_credential_revocation_checkpoints as adjudicator_checkpoint_fx
import test_adjudicator_credential_revocation_ledger as prior_revocation_fx
import test_credential_revocation_checkpoints as reviewer_checkpoint_fx
import test_credential_revocation_ledger as reviewer_revocation_fx
import test_extraction_review_adjudication as extraction_fx
import test_witness_conflict_adjudication as reviewer_conflict_fx
from jsonschema import ValidationError
from test_adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    revocation_corpus,
    revocation_ledger,
    revocation_policy,
    suspension_event,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema
from test_revocation_gated_adjudicator_checkpoint_conflict_runner import (
    prepare_revocation_store,
)

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence,
    persist_checkpoint_bound_adjudicator_checkpoint_conflict_credential_revocation_corpus,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_gated_adjudicator_checkpoint_conflict_runner import (
    CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS,
    CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus,
    CheckpointGatedAdjudicatorCheckpointConflictExperimentRunner,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import canonical_sha256
from ctrt.witness_conflict_adjudication import WitnessConflictAdjudicationOutcome

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-checkpoint-policy.v0.1.0.json"
)
CHECKPOINT_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoints/"
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-genesis-checkpoint.json"
)
LOG_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoints/"
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.7.0.json"
POLICY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-checkpoint-policy.schema.json"
)
CHECKPOINT_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-ledger-checkpoint.schema.json"
)
LOG_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-checkpoint-log.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-conflict-adjudicator-credential-"
    "revocation-checkpoint-bound-corpus.schema.json"
)
REPORT_SCHEMA = ROOT / "schemas" / (
    "adjudicator-credential-revocation-checkpoint-verification.schema.json"
)
FINAL_SCHEMA = ROOT / "schemas" / (
    "checkpoint-gated-adjudicator-checkpoint-conflict-revocation-final.schema.json"
)


def checkpoint_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationCheckpointPolicySnapshot:
    return AdjudicatorCredentialRevocationCheckpointPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def checkpoint(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationLedgerCheckpointSnapshot:
    return AdjudicatorCredentialRevocationLedgerCheckpointSnapshot.from_document(
        document or load_document(CHECKPOINT_PATH)
    )


def checkpoint_log(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationCheckpointLogSnapshot:
    return AdjudicatorCredentialRevocationCheckpointLogSnapshot.from_document(
        document or load_document(LOG_PATH)
    )


def checkpoint_corpus(
    document: dict[str, Any] | None = None,
    *,
    predecessor: Any | None = None,
) -> CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot:
    return CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH),
        predecessor=predecessor or revocation_corpus(),
    )


def checkpoint_plan():
    selected = checkpoint_corpus()
    return replace(
        credential_fx.frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def event_population_hash(refs: list[dict[str, str]]) -> str:
    return canonical_sha256({"event_refs": refs})


def verify(*, verified_at: str = "2026-08-03T19:27:00Z"):
    return validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
        plan=checkpoint_plan(),
        corpus=checkpoint_corpus(),
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at=verified_at,
    )


def prepare_checkpoint_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_revocation_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[-1]
    selected = checkpoint_corpus(predecessor=predecessor)
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_checkpoint_bound_adjudicator_checkpoint_conflict_credential_revocation_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T19:27:00Z",
    )
    return (*prepared[:-2], plan, selected)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    revocation_evaluated_at: str,
):
    prepared = prepare_checkpoint_store(tmp_path)
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
    runner = CheckpointGatedAdjudicatorCheckpointConflictExperimentRunner(
        analyzer_registry=extraction_fx.analyzer_registry(*fixture_analyzers),
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
        revocation_policy=reviewer_revocation_fx.policy(),
        ledger=reviewer_ledger,
        checkpoint_policy=reviewer_checkpoint_fx.policy(),
        checkpoint_log=reviewer_checkpoint_fx.checkpoint_log(),
        checkpoints=(reviewer_checkpoint_fx.checkpoint(),),
        witness_registry=reviewer_conflict_fx.witness_registry(),
        witness_policy=reviewer_conflict_fx.witness_policy(),
        witness_attestations=reviewer_witness_records,
        adjudicator_registry=reviewer_conflict_fx.adjudicator_registry(),
        adjudication_policy=reviewer_conflict_fx.adjudication_policy(),
        adjudication=bound_reviewer_adjudication,
        adjudicator_issuer_registry=prior_credential_fx.issuer_registry(),
        adjudicator_credential_policy=prior_credential_fx.credential_policy(),
        adjudicator_credentials=(adjudicator_credential,),
        adjudicator_revocation_policy=prior_revocation_fx.revocation_policy(),
        adjudicator_revocation_ledger=prior_revocation_fx.revocation_ledger(),
        adjudicator_checkpoint_policy=adjudicator_checkpoint_fx.checkpoint_policy(),
        adjudicator_checkpoint_log=adjudicator_checkpoint_fx.checkpoint_log(),
        adjudicator_checkpoints=(adjudicator_checkpoint_fx.checkpoint(),),
        adjudicator_checkpoint_witness_registry=(
            conflict_fx.adjudicator_witness_registry()
        ),
        adjudicator_checkpoint_witness_policy=(
            conflict_fx.adjudicator_witness_policy()
        ),
        adjudicator_checkpoint_witness_attestations=conflict_fx.conflict_attestations(),
        adjudicator_checkpoint_conflict_adjudicator_registry=(
            conflict_fx.conflict_adjudicator_registry()
        ),
        adjudicator_checkpoint_conflict_adjudication_policy=(
            conflict_fx.conflict_adjudication_policy()
        ),
        adjudicator_checkpoint_conflict_adjudication=(
            conflict_fx.conflict_adjudication()
        ),
        checkpoint_conflict_adjudicator_issuer_registry=credential_fx.issuer_registry(),
        checkpoint_conflict_adjudicator_credential_policy=(
            credential_fx.credential_policy()
        ),
        checkpoint_conflict_adjudicator_credentials=(credential_fx.credential(),),
        checkpoint_conflict_adjudicator_revocation_policy=revocation_policy(),
        checkpoint_conflict_adjudicator_revocation_ledger=revocation_ledger(),
        checkpoint_conflict_adjudicator_revocation_events=(suspension_event(),),
        checkpoint_conflict_adjudicator_revocation_checkpoint_policy=(
            checkpoint_policy()
        ),
        checkpoint_conflict_adjudicator_revocation_checkpoint_log=checkpoint_log(),
        checkpoint_conflict_adjudicator_revocation_checkpoints=(checkpoint(),),
        corpus=selected,
        environment=extraction_fx.environment(),
        windows=extraction_fx.windows(),
        experiment_run_id=run_id,
        checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at=(
            "2026-08-03T19:27:00Z"
        ),
        checkpoint_conflict_adjudicator_revocation_evaluated_at=(
            revocation_evaluated_at
        ),
        checkpoint_conflict_credential_evaluated_at="2026-08-03T18:23:00Z",
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


def test_fixed_checkpoint_graph_and_schemas() -> None:
    selected = checkpoint_corpus()
    report = verify()
    assert selected.reference().artifact_hash == (
        "sha256:26311c6a5da00c7e6ea3986406be48ca8d3087ccf3f41f07c783cd8db88635fb"
    )
    assert selected.predecessor_corpus_ref == revocation_corpus().reference()
    assert report.checkpoint_count == 1
    assert report.head_sequence_number == 0
    assert report.head_event_count == 1
    assert report.head_checkpoint_ref == checkpoint().reference()
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(CHECKPOINT_SCHEMA, load_document(CHECKPOINT_PATH))
    validate_schema(LOG_SCHEMA, load_document(LOG_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_checkpoint_omission_and_future_verification_are_rejected() -> None:
    document = deepcopy(load_document(CHECKPOINT_PATH))
    document["event_refs"] = []
    document["event_count"] = 0
    document["event_population_hash"] = event_population_hash([])
    changed = checkpoint(document)
    log_document = deepcopy(load_document(LOG_PATH))
    changed_ref = stored_ref_document(changed.reference())
    log_document["checkpoint_refs"] = [changed_ref]
    log_document["head_checkpoint_ref"] = changed_ref
    changed_log = checkpoint_log(log_document)
    with pytest.raises(AdjudicatorCredentialRevocationCheckpointError):
        validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
            plan=checkpoint_plan(),
            corpus=checkpoint_corpus(),
            policy=checkpoint_policy(),
            log=changed_log,
            ledger=revocation_ledger(),
            checkpoints=(changed,),
            verified_at="2026-08-03T19:27:00Z",
        )
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="before publication",
    ):
        verify(verified_at="2026-08-03T19:25:00Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_checkpoint_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(
        CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
        prepared[-1],
    )
    first = load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
        store,
        corpus=selected,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    second = load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
        store,
        corpus=selected,
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    assert first == second
    assert first.checkpoints == (checkpoint(),)


def test_active_checkpoint_delegates_without_rewriting_revocation(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="checkpoint-conflict-revocation-checkpoint-execute",
        revocation_evaluated_at="2026-12-31T23:59:59Z",
    )
    assert (
        receipt.status
        is CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.conflict_adjudication_outcome is (
        WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert (
        receipt.verified_checks
        == CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
    )
    report = cast(
        dict[str, Any],
        json.loads(store.get(receipt.checkpoint_verification_ref.artifact_id).text),
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(REPORT_SCHEMA, report)
    validate_schema(FINAL_SCHEMA, final)


def test_suspended_status_preserves_checkpoint_and_terminal_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="checkpoint-conflict-revocation-checkpoint-suspended",
        revocation_evaluated_at="2027-01-01T00:00:00Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.adjudicator_checkpoint_witness_outcome is None
    assert receipt.conflict_adjudication_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert store.get(receipt.checkpoint_verification_ref.artifact_id)
    assert receipt.revocation_receipt.credentialed_conflict_receipt is None


def test_schema_rejects_extra_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
