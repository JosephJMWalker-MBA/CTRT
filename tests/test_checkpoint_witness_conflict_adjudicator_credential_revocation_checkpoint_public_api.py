from __future__ import annotations

import ctrt.checkpoint_gated_checkpoint_witness_conflict_adjudication_runner as runner
import ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints as contract

CONTRACT_NAMES = (
    "AdjudicatorCredentialRevocationCheckpointError",
    "AdjudicatorCredentialRevocationCheckpointLogSnapshot",
    "AdjudicatorCredentialRevocationCheckpointPolicySnapshot",
    "AdjudicatorCredentialRevocationCheckpointVerificationReport",
    "AdjudicatorCredentialRevocationLedgerCheckpointSnapshot",
    "CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot",
    "StoredAdjudicatorCredentialRevocationCheckpointEvidence",
    "load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence",
    "persist_checkpoint_bound_checkpoint_witness_conflict_adjudicator_credential_revocation_corpus",
    "validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints",
)

RUNNER_NAMES = (
    "CHECKPOINT_WITNESS_CONFLICT_REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
    "CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner",
    "CheckpointWitnessConflictRevocationCheckpointExperimentError",
    "CheckpointWitnessConflictRevocationCheckpointFinalManifest",
    "CheckpointWitnessConflictRevocationCheckpointRunnerStage",
    "CheckpointWitnessConflictRevocationCheckpointRunnerStatus",
    "VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt",
)


def test_current_revocation_checkpoint_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_current_revocation_checkpoint_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
