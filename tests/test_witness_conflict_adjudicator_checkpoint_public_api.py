from __future__ import annotations

import ctrt

EXPECTED_NAMES = (
    "WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS",
    "VerifiedWitnessConflictAdjudicatorCheckpointReceipt",
    "WitnessBoundCheckpointCorpusSnapshot",
    "WitnessConflictAdjudicatorCheckpointExperimentError",
    "WitnessConflictAdjudicatorCheckpointFinalManifest",
    "WitnessConflictAdjudicatorCheckpointRunnerStage",
    "WitnessConflictAdjudicatorCheckpointRunnerStatus",
    "WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner",
    "load_witness_evidence",
    "persist_witness_corpus",
    "validate_witness_attestations",
)


def test_named_checkpoint_witness_symbols_are_exported() -> None:
    for name in EXPECTED_NAMES:
        assert getattr(ctrt, name) is not None
