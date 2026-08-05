from importlib import import_module


def test_contract_public_api_is_importable() -> None:
    contract = import_module(
        "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
        "credential_revocation_checkpoints"
    )
    expected = {
        "AdjudicatorCredentialRevocationCheckpointError",
        "AdjudicatorCredentialRevocationCheckpointLogSnapshot",
        "AdjudicatorCredentialRevocationCheckpointPolicySnapshot",
        "AdjudicatorCredentialRevocationCheckpointVerificationReport",
        "AdjudicatorCredentialRevocationLedgerCheckpointSnapshot",
        "CheckpointBoundCurrentRevocationCheckpointWitnessConflictAdjudicator"
        "CredentialRevocationCorpusSnapshot",
        "StoredAdjudicatorCredentialRevocationCheckpointEvidence",
        "load_current_revocation_checkpoint_witness_conflict_adjudicator_"
        "credential_revocation_checkpoint_evidence",
        "persist_current_revocation_checkpoint_witness_conflict_adjudicator_"
        "revocation_checkpoint_corpus",
        "validate_current_revocation_checkpoint_witness_conflict_adjudicator_"
        "credential_revocation_checkpoints",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_runner_public_api_is_importable() -> None:
    runner = import_module(
        "ctrt.checkpoint_gated_current_revocation_checkpoint_witness_conflict_"
        "runner"
    )
    expected = {
        "CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_"
        "REVOCATION_CHECKPOINT_VERIFIED_CHECKS",
        "CheckpointGatedCurrentRevocationCheckpointWitnessConflict"
        "ExperimentRunner",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
        "CheckpointExperimentError",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
        "CheckpointFinalManifest",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
        "CheckpointRunnerStage",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocation"
        "CheckpointRunnerStatus",
        "VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicator"
        "RevocationCheckpointReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
