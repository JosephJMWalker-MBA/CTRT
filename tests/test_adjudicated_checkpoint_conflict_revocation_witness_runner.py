from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import test_adjudicator_checkpoint_conflict_revocation_checkpoint_witness_attestation as witness_fx
from test_adjudicator_checkpoint_conflict_credential_attestation import frozen_plan
from test_adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema
from test_witness_gated_adjudicator_checkpoint_conflict_runner import (
    execute as execute_witness,
)

from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS,
    AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner,
    CheckpointConflictWitnessAdjudicationRunnerStatus,
)
from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
)
from ctrt.experiments import ExperimentPlan
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictResolutionStatus,
)

adjudication_fx = import_module(
    "test_adjudicator_checkpoint_conflict_revocation_checkpoint_"
    "witness_conflict_adjudication"
)

ROOT = Path(__file__).parents[1]
FINAL_SCHEMA = ROOT / "schemas" / (
    "adjudicated-checkpoint-conflict-revocation-witness-final.schema.json"
)


def versioned_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


def conflict_witness_graph() -> tuple[
    Any,
    tuple[CheckpointWitnessAttestationSnapshot, ...],
]:
    documents = tuple(
        deepcopy(load_document(path)) for path in witness_fx.ATTESTATION_PATHS
    )
    documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    documents[2]["observation_kind"] = "conflicting_head"
    attestations = witness_fx.witness_attestations(documents)
    corpus_document = deepcopy(load_document(witness_fx.CORPUS_PATH))
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_witness_attestation_refs"
    ][2] = witness_fx.stored_ref_document(attestations[2].reference())
    selected = witness_fx.witness_corpus(
        corpus_document,
        predecessor=checkpoint_corpus(),
    )
    return selected, attestations


def outer_conflict_case(
    *,
    status: str,
    witness_predecessor: Any,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
) -> tuple[
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    WitnessConflictAdjudicationSnapshot,
]:
    _, _, decision = adjudication_fx.conflict_case(status=status)
    document = deepcopy(load_document(adjudication_fx.CORPUS_PATH))
    document["corpus_id"] = (
        "corpus.synthetic-three-items.checkpoint-conflict-witness-"
        f"runner-{status}-test"
    )
    document["corpus_version"] = f"1.9.2-test-{status}"
    document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_witness_conflict_adjudication_predecessor_corpus_ref"
    ] = versioned_ref_document(witness_predecessor.reference())
    document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_witness_attestation_refs"
    ][2] = witness_fx.stored_ref_document(attestations[2].reference())
    document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_witness_conflict_adjudication_ref"
    ] = witness_fx.stored_ref_document(decision.reference())
    selected = CheckpointConflictWitnessAdjudicationCorpusSnapshot.from_document(
        document,
        checkpoint_predecessor=checkpoint_corpus(),
        witness_predecessor=witness_predecessor,
    )
    return selected, decision


def persist_outer_graph(
    store: FileSystemArtifactStore,
    *,
    selected: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    predecessor: Any,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    decision: WitnessConflictAdjudicationSnapshot,
) -> ExperimentPlan:
    plan = replace(
        frozen_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    adjudication_fx.persist_adjudication_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint(),
        witness_attestations=attestations,
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        adjudication_policy=adjudication_fx.adjudication_policy(),
        adjudication=decision,
        evaluated_at="2026-08-03T19:55:30Z",
    )
    return plan


def run_outer(
    store: FileSystemArtifactStore,
    *,
    run_id: str,
    plan: ExperimentPlan,
    selected: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
    decision: WitnessConflictAdjudicationSnapshot,
    witness_receipt: Any,
    checkpoint_executor: Any = None,
):
    runner = AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner(
        artifact_store=store
    )
    return runner.run(
        plan=plan,
        corpus=selected,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        witness_attestations=attestations,
        head_checkpoint=checkpoint(),
        adjudicator_registry=adjudication_fx.adjudicator_registry(),
        adjudication_policy=adjudication_fx.adjudication_policy(),
        adjudication=decision,
        witness_receipt=witness_receipt,
        checkpoint_executor=checkpoint_executor,
        experiment_run_id=run_id,
        witness_evaluated_at="2026-08-03T19:53:30Z",
        adjudication_evaluated_at="2026-08-03T19:55:30Z",
        completed_at="2026-08-03T19:56:00Z",
    )


def test_not_required_preserves_witness_and_reuses_checkpoint_receipt(
    tmp_path: Path,
) -> None:
    run_id = "checkpoint-conflict-witness-adjudication-not-required"
    witness_receipt, store = execute_witness(
        tmp_path,
        run_id=run_id,
        revocation_evaluated_at="2026-12-31T23:59:59Z",
    )
    selected = adjudication_fx.corpus()
    decision = adjudication_fx.adjudication()
    plan = persist_outer_graph(
        store,
        selected=selected,
        predecessor=witness_fx.witness_corpus(),
        attestations=witness_fx.witness_attestations(),
        decision=decision,
    )
    receipt = run_outer(
        store,
        run_id=run_id,
        plan=plan,
        selected=selected,
        attestations=witness_fx.witness_attestations(),
        decision=decision,
        witness_receipt=witness_receipt,
    )
    assert receipt.status is CheckpointConflictWitnessAdjudicationRunnerStatus.VERIFIED
    assert receipt.checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.EXECUTE
    )
    assert receipt.resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.checkpoint_receipt is witness_receipt.checkpoint_receipt
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert (
        receipt.verified_checks
        == CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS
    )
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_pending_conflict_is_terminal_and_never_calls_checkpoint(
    tmp_path: Path,
) -> None:
    run_id = "checkpoint-conflict-witness-adjudication-pending"
    witness_receipt, store = execute_witness(
        tmp_path,
        run_id=run_id,
        revocation_evaluated_at="2026-12-31T23:59:59Z",
        conflict=True,
    )
    predecessor, attestations = conflict_witness_graph()
    selected, decision = outer_conflict_case(
        status="pending",
        witness_predecessor=predecessor,
        attestations=attestations,
    )
    plan = persist_outer_graph(
        store,
        selected=selected,
        predecessor=predecessor,
        attestations=attestations,
        decision=decision,
    )
    calls = 0

    def forbidden_executor(**_: Any) -> Any:
        nonlocal calls
        calls += 1
        raise AssertionError("pending adjudication may not execute checkpoint")

    receipt = run_outer(
        store,
        run_id=run_id,
        plan=plan,
        selected=selected,
        attestations=attestations,
        decision=decision,
        witness_receipt=witness_receipt,
        checkpoint_executor=forbidden_executor,
    )
    assert calls == 0
    assert receipt.checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.resolution_status is WitnessConflictResolutionStatus.PENDING
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN


def test_unresolved_conflict_is_terminal_and_preserves_witness_abstention(
    tmp_path: Path,
) -> None:
    run_id = "checkpoint-conflict-witness-adjudication-unresolved"
    witness_receipt, store = execute_witness(
        tmp_path,
        run_id=run_id,
        revocation_evaluated_at="2026-12-31T23:59:59Z",
        conflict=True,
    )
    predecessor, attestations = conflict_witness_graph()
    selected, decision = outer_conflict_case(
        status="unresolved",
        witness_predecessor=predecessor,
        attestations=attestations,
    )
    plan = persist_outer_graph(
        store,
        selected=selected,
        predecessor=predecessor,
        attestations=attestations,
        decision=decision,
    )
    receipt = run_outer(
        store,
        run_id=run_id,
        plan=plan,
        selected=selected,
        attestations=attestations,
        decision=decision,
        witness_receipt=witness_receipt,
    )
    assert receipt.checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.resolution_status is WitnessConflictResolutionStatus.UNRESOLVED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN


def test_resolved_conflict_delegates_without_rewriting_witness_abstention(
    tmp_path: Path,
) -> None:
    run_id = "checkpoint-conflict-witness-adjudication-resolved"
    witness_receipt, store = execute_witness(
        tmp_path / "conflict",
        run_id=run_id,
        revocation_evaluated_at="2026-12-31T23:59:59Z",
        conflict=True,
    )
    predecessor, attestations = conflict_witness_graph()
    selected, decision = outer_conflict_case(
        status="resolved",
        witness_predecessor=predecessor,
        attestations=attestations,
    )
    plan = persist_outer_graph(
        store,
        selected=selected,
        predecessor=predecessor,
        attestations=attestations,
        decision=decision,
    )

    lower_witness_receipt, lower_store = execute_witness(
        tmp_path / "lower",
        run_id=run_id,
        revocation_evaluated_at="2026-12-31T23:59:59Z",
    )
    lower_receipt = lower_witness_receipt.checkpoint_receipt
    assert lower_receipt is not None
    lower_final = lower_store.get(
        lower_receipt.final_manifest_ref.artifact_id,
        expected_hash=lower_receipt.final_manifest_ref.artifact_hash,
    )
    store.append(lower_final)
    calls = 0

    def checkpoint_executor(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        experiment_run_id: str,
    ) -> Any:
        nonlocal calls
        calls += 1
        assert plan.corpus_ref == checkpoint_corpus().reference()
        assert corpus.reference() == checkpoint_corpus().reference()
        assert experiment_run_id == run_id
        return lower_receipt

    receipt = run_outer(
        store,
        run_id=run_id,
        plan=plan,
        selected=selected,
        attestations=attestations,
        decision=decision,
        witness_receipt=witness_receipt,
        checkpoint_executor=checkpoint_executor,
    )
    assert calls == 1
    assert receipt.checkpoint_witness_outcome is (
        CheckpointWitnessDecisionOutcome.ABSTAIN
    )
    assert receipt.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.checkpoint_receipt is lower_receipt
    assert lower_receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
