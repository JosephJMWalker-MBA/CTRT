from __future__ import annotations

from importlib import import_module

contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_witness"
)
runner = import_module(
    "ctrt.witness_gated_current_revocation_checkpoint_witness_conflict_runner"
)

CONTRACT_NAMES = (
    "AdjudicatorCheckpointWitnessDecisionReport",
    "AdjudicatorCheckpointWitnessError",
    "AdjudicatorCheckpointWitnessObservationSummary",
    "StoredAdjudicatorCheckpointWitnessEvidence",
    "WitnessBoundCurrentRevocationConflictAdjudicatorCheckpointCorpusSnapshot",
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_evidence",
    "persist_current_revocation_conflict_adjudicator_checkpoint_witness_corpus",
    "validate_current_revocation_conflict_adjudicator_checkpoint_witnesses",
)

RUNNER_NAMES = (
    "CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessExperimentError",
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessFinalManifest",
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessRunnerStage",
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessRunnerStatus",
    "VerifiedCurrentRevocationConflictAdjudicatorCheckpointWitnessReceipt",
    "WitnessGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
)


def test_current_checkpoint_witness_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_current_checkpoint_witness_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
