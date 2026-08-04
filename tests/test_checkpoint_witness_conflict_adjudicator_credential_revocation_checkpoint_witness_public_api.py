from __future__ import annotations

from importlib import import_module

contract = import_module(
    "ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness"
)
runner = import_module("ctrt.witness_gated_current_checkpoint_runner")


def test_current_checkpoint_witness_contract_public_api() -> None:
    expected = {
        "AdjudicatorCheckpointWitnessDecisionReport",
        "AdjudicatorCheckpointWitnessError",
        "AdjudicatorCheckpointWitnessObservationSummary",
        "StoredAdjudicatorCheckpointWitnessEvidence",
        "WitnessBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot",
        "load_current_checkpoint_witness_evidence",
        "persist_current_checkpoint_witness_corpus",
        "validate_current_checkpoint_witness_attestations",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_current_checkpoint_witness_runner_public_api() -> None:
    expected = {
        "CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
        "CurrentCheckpointWitnessExperimentError",
        "CurrentCheckpointWitnessFinalManifest",
        "CurrentCheckpointWitnessRunnerStage",
        "CurrentCheckpointWitnessRunnerStatus",
        "VerifiedCurrentCheckpointWitnessReceipt",
        "WitnessGatedCurrentCheckpointExperimentRunner",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
