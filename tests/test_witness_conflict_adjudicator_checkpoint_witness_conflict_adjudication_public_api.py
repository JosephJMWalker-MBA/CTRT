from __future__ import annotations

import ctrt.adjudicated_witness_conflict_adjudicator_checkpoint_runner as runner
import ctrt.witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication as contract

CONTRACT_NAMES = (
    "AdjudicationBoundCheckpointWitnessCorpusSnapshot",
    "ConflictAdjudicationDecisionReport",
    "ConflictAdjudicationError",
    "ConflictingCheckpointWitnessCorpusSnapshot",
    "StoredConflictAdjudicationEvidence",
    "load_conflict_adjudication_evidence",
    "persist_adjudication_bound_corpus",
    "validate_conflict_adjudication",
)

RUNNER_NAMES = (
    "ADJUDICATED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
    "AdjudicatedCheckpointWitnessConflictExperimentError",
    "AdjudicatedCheckpointWitnessConflictFinalManifest",
    "AdjudicatedCheckpointWitnessConflictRunnerStage",
    "AdjudicatedCheckpointWitnessConflictRunnerStatus",
    "AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner",
    "VerifiedAdjudicatedCheckpointWitnessConflictReceipt",
)


def test_checkpoint_witness_conflict_adjudication_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_checkpoint_witness_conflict_adjudication_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
