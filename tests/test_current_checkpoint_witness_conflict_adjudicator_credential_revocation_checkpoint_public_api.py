from __future__ import annotations

import ctrt.checkpoint_gated_current_checkpoint_witness_conflict_runner as runner
from ctrt import (
    current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints
    as contract,
)

CONTRACT_NAMES = (
    "AdjudicatorCredentialRevocationCheckpointError",
    "AdjudicatorCredentialRevocationCheckpointLogSnapshot",
    "AdjudicatorCredentialRevocationCheckpointPolicySnapshot",
    "AdjudicatorCredentialRevocationCheckpointVerificationReport",
    "AdjudicatorCredentialRevocationLedgerCheckpointSnapshot",
    "CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot",
    "StoredAdjudicatorCredentialRevocationCheckpointEvidence",
    "load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence",
    "persist_checkpoint_bound_current_checkpoint_witness_conflict_adjudicator_credential_revocation_corpus",
    "validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints",
)

RUNNER_NAMES = (
    "CURRENT_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
    "CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointFinalManifest",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStage",
    "CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointRunnerStatus",
    "VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt",
)


def test_current_conflict_adjudicator_revocation_checkpoint_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_current_conflict_adjudicator_revocation_checkpoint_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
