from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import test_adjudicator_checkpoint_conflict_credential_attestation as credential_fx
import test_adjudicator_checkpoint_witness_attestation as adjudicator_witness_fx
import test_adjudicator_checkpoint_witness_conflict_adjudication as conflict_fx
import test_adjudicator_credential_attestation as prior_credential_fx
import test_adjudicator_credential_revocation_checkpoints as adjudicator_checkpoint_fx
import test_adjudicator_credential_revocation_ledger as prior_revocation_fx
import test_credential_revocation_checkpoints as reviewer_checkpoint_fx
import test_credential_revocation_ledger as reviewer_revocation_fx
import test_extraction_review_adjudication as extraction_fx
import test_witness_conflict_adjudication as reviewer_conflict_fx
from test_credential_revocation_checkpoints import validate_schema

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    persist_adjudicator_checkpoint_conflict_credential_revocation_bound_corpus,
)
from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_adjudicator_checkpoint_conflict_runner import (
    CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS,
    CheckpointConflictAdjudicatorRevocationRunnerStatus,
    RevocationGatedAdjudicatorCheckpointConflictExperimentRunner,
)
from ctrt.witness_conflict_adjudication import WitnessConflictAdjudicationOutcome
from test_adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    revocation_corpus,
    revocation_ledger,
    revocation_policy,
    suspension_event,
)

ROOT = Path(__file__).parents[1]
DECISION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / (
    "revocation-gated-adjudicator-checkpoint-conflict-final.schema.json"
)


def prepare_revocation_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = credential_fx.prepare_credential_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = credential_fx.corpus()
    selected = revocation_corpus(predecessor=predecessor)
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_adjudicator_checkpoint_conflict_credential_revocation_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        adjudicator_registry=conflict_fx.conflict_adjudicator_registry(),
        issuer_registry=credential_fx.issuer_registry(),
        credential_policy=credential_fx.credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(credential_fx.credential(),),
        adjudication=conflict_fx.conflict_adjudication(),
        events=(suspension_event(),),
        evaluated_at="2026-08-03T18:23:00Z",
    )
    return (*prepared[:-2], plan, selected)


def execute(
    tmp_path: Path,
    *,
    run_id: str,
    revocation_evaluated_at: str,
):
    prepared = prepare_revocation_store(tmp_path)
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
    runner = RevocationGatedAdjudicatorCheckpointConflictExperimentRunner(
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
        corpus=selected,
        environment=extraction_fx.environment(),
        windows=extraction_fx.windows(),
        experiment_run_id=run_id,
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


def test_active_as_of_status_delegates_without_rewriting_conflict(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="checkpoint-conflict-revocation-execute",
        revocation_evaluated_at="2026-12-31T23:59:59Z",
    )
    assert receipt.status is CheckpointConflictAdjudicatorRevocationRunnerStatus.VERIFIED
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.adjudicator_checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.conflict_adjudication_outcome is (
        WitnessConflictAdjudicationOutcome.EXECUTE
    )
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.credentialed_conflict_receipt is not None
    assert (
        receipt.verified_checks
        == CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
    )
    assert store.get(conflict_fx.conflict_adjudication().artifact_id).payload == (
        conflict_fx.conflict_adjudication().canonical_payload
    )
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    validate_schema(FINAL_SCHEMA, final)


def test_effective_suspension_abstains_before_credential_or_conflict(
    tmp_path: Path,
) -> None:
    run_id = "checkpoint-conflict-revocation-suspended"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        revocation_evaluated_at="2027-01-01T00:00:00Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credential_outcome is None
    assert receipt.adjudicator_checkpoint_witness_outcome is None
    assert receipt.conflict_adjudication_outcome is None
    assert receipt.adjudicator_revocation_outcome is None
    assert receipt.adjudicator_credential_outcome is None
    assert receipt.reviewer_checkpoint_witness_outcome is None
    assert receipt.reviewer_witness_adjudication_outcome is None
    assert receipt.reviewer_revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credentialed_conflict_receipt is None
    for artifact_id in (
        (
            f"{run_id}:adjudicator-checkpoint-conflict-"
            "adjudicator-credential-decision"
        ),
        f"{run_id}:adjudicator-checkpoint-witness-conflict-adjudication-decision",
        f"{run_id}:adjudicator-checkpoint-witness-decision",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(artifact_id)
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    validate_schema(FINAL_SCHEMA, final)
