from __future__ import annotations

from ctrt import witness_conflict_adjudicator_checkpoint_witness as witness_contract
from ctrt import witness_gated_witness_conflict_adjudicator_checkpoint_runner as runner

CONTRACT_NAMES = (
    "WitnessBoundCheckpointCorpusSnapshot",
    "load_witness_evidence",
    "persist_witness_corpus",
    "validate_witness_attestations",
)
RUNNER_NAMES = (
    "WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS",
    "VerifiedWitnessConflictAdjudicatorCheckpointReceipt",
    "WitnessConflictAdjudicatorCheckpointExperimentError",
    "WitnessConflictAdjudicatorCheckpointFinalManifest",
    "WitnessConflictAdjudicatorCheckpointRunnerStage",
    "WitnessConflictAdjudicatorCheckpointRunnerStatus",
    "WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner",
)


def test_named_checkpoint_witness_module_apis_are_importable() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(witness_contract, name) is not None
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
