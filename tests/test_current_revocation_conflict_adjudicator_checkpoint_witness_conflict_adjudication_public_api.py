from __future__ import annotations

from importlib import import_module

contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_"
    "witness_conflict_adjudication"
)
runner = import_module(
    "ctrt.adjudicated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)

CONTRACT_NAMES = (
    "AdjudicationBoundCurrentRevocationConflictAdjudicatorCheckpointWitnessCorpusSnapshot",
    "ConflictAdjudicationDecisionReport",
    "ConflictAdjudicationError",
    "ConflictingCurrentRevocationConflictAdjudicatorCheckpointWitnessCorpusSnapshot",
    "StoredConflictAdjudicationEvidence",
    "load_current_revocation_conflict_adjudicator_checkpoint_adjudication_evidence",
    "persist_current_revocation_conflict_adjudicator_checkpoint_adjudication_corpus",
    "validate_current_revocation_conflict_adjudicator_checkpoint_adjudication",
)

RUNNER_NAMES = (
    "ADJUDICATED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_VERIFIED_CHECKS",
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentError",
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "FinalManifest",
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStage",
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStatus",
    "VerifiedAdjudicatedCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessReceipt",
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentRunner",
)


def test_current_checkpoint_witness_conflict_adjudication_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_current_checkpoint_witness_conflict_adjudication_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
