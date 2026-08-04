from __future__ import annotations

from importlib import import_module

contract = import_module(
    "ctrt.current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_witness"
)
runner = import_module("ctrt.witness_gated_current_revocation_checkpoint_runner")

CONTRACT_NAMES = (
    "AdjudicatorCheckpointWitnessDecisionReport",
    "AdjudicatorCheckpointWitnessError",
    "AdjudicatorCheckpointWitnessObservationSummary",
    "StoredAdjudicatorCheckpointWitnessEvidence",
    "WitnessBoundCurrentConflictAdjudicatorRevocationCheckpointCorpusSnapshot",
    "load_current_conflict_adjudicator_revocation_checkpoint_witness_evidence",
    "persist_current_conflict_adjudicator_revocation_checkpoint_witness_corpus",
    "validate_current_conflict_adjudicator_revocation_checkpoint_witnesses",
)

RUNNER_NAMES = (
    "CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
    "CurrentRevocationCheckpointWitnessExperimentError",
    "CurrentRevocationCheckpointWitnessFinalManifest",
    "CurrentRevocationCheckpointWitnessRunnerStage",
    "CurrentRevocationCheckpointWitnessRunnerStatus",
    "VerifiedCurrentRevocationCheckpointWitnessReceipt",
    "WitnessGatedCurrentRevocationCheckpointExperimentRunner",
)


def test_current_revocation_checkpoint_witness_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_current_revocation_checkpoint_witness_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
