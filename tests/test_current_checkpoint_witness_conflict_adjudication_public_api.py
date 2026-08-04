from __future__ import annotations

from importlib import import_module

contract = import_module("ctrt.current_checkpoint_witness_conflict_adjudication")
runner = import_module("ctrt.adjudicated_current_checkpoint_witness_runner")


def test_current_checkpoint_conflict_adjudication_contract_public_api() -> None:
    expected = {
        "AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot",
        "ConflictAdjudicationDecisionReport",
        "ConflictAdjudicationError",
        "ConflictingCurrentCheckpointWitnessCorpusSnapshot",
        "StoredConflictAdjudicationEvidence",
        "load_current_checkpoint_conflict_adjudication_evidence",
        "persist_current_checkpoint_adjudication_bound_corpus",
        "validate_current_checkpoint_conflict_adjudication",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_adjudicated_current_checkpoint_witness_runner_public_api() -> None:
    expected = {
        "ADJUDICATED_CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
        "AdjudicatedCurrentCheckpointWitnessExperimentError",
        "AdjudicatedCurrentCheckpointWitnessExperimentRunner",
        "AdjudicatedCurrentCheckpointWitnessFinalManifest",
        "AdjudicatedCurrentCheckpointWitnessRunnerStage",
        "AdjudicatedCurrentCheckpointWitnessRunnerStatus",
        "VerifiedAdjudicatedCurrentCheckpointWitnessReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
