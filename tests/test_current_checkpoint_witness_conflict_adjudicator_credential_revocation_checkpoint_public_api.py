from __future__ import annotations

from importlib import import_module

runner = import_module(
    "ctrt.checkpoint_gated_current_checkpoint_witness_conflict_runner"
)
contract = import_module(
    "ctrt.current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoints"
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
    "persist_current_checkpoint_witness_conflict_adjudicator_revocation_checkpoint_corpus",
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
