from __future__ import annotations

import ctrt
from ctrt import (
    checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints as checkpoints,
)

MODULE_NAMES = (
    "CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot",
    "load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_evidence",
    "persist_checkpoint_bound_checkpoint_conflict_witness_adjudicator_credential_revocation_corpus",
    "validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints",
)
PUBLIC_NAMES = {
    *MODULE_NAMES,
    "CHECKPOINT_CONFLICT_WITNESS_REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
    "CheckpointConflictWitnessRevocationCheckpointExperimentError",
    "CheckpointConflictWitnessRevocationCheckpointFinalManifest",
    "CheckpointConflictWitnessRevocationCheckpointRunnerStage",
    "CheckpointConflictWitnessRevocationCheckpointRunnerStatus",
    "CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner",
    "VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt",
}


def test_checkpoint_contract_symbols_are_importable() -> None:
    for name in MODULE_NAMES:
        assert getattr(checkpoints, name) is not None


def test_checkpoint_contract_and_runner_are_public() -> None:
    assert set(ctrt.__all__) >= PUBLIC_NAMES
    for name in PUBLIC_NAMES:
        assert getattr(ctrt, name) is not None
