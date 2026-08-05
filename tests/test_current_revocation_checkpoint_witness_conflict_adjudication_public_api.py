from __future__ import annotations

from importlib import import_module

contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudication"
)
runner = import_module(
    "ctrt.adjudicated_current_revocation_checkpoint_witness_runner"
)


def test_current_revocation_checkpoint_conflict_contract_public_api() -> None:
    expected = {
        "AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot",
        "ConflictAdjudicationDecisionReport",
        "ConflictAdjudicationError",
        "ConflictingCurrentRevocationCheckpointWitnessCorpusSnapshot",
        "StoredConflictAdjudicationEvidence",
        "load_current_revocation_checkpoint_conflict_adjudication_evidence",
        "persist_current_revocation_checkpoint_adjudication_bound_corpus",
        "validate_current_revocation_checkpoint_conflict_adjudication",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_adjudicated_current_revocation_checkpoint_runner_public_api() -> None:
    expected = {
        "ADJUDICATED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
        "AdjudicatedCurrentRevocationCheckpointWitnessExperimentError",
        "AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner",
        "AdjudicatedCurrentRevocationCheckpointWitnessFinalManifest",
        "AdjudicatedCurrentRevocationCheckpointWitnessRunnerStage",
        "AdjudicatedCurrentRevocationCheckpointWitnessRunnerStatus",
        "VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
