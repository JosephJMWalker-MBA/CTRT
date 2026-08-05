from importlib import import_module


def test_contract_public_api_is_importable() -> None:
    contract = import_module(
        "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_revocation_closure_checkpoints"
    )
    expected = {
        "AdjudicatorCredentialRevocationCheckpointError",
        "AdjudicatorCredentialRevocationCheckpointLogSnapshot",
        "AdjudicatorCredentialRevocationCheckpointVerificationReport",
        "AdjudicatorCredentialRevocationLedgerCheckpointSnapshot",
        "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflict"
        "AdjudicatorCredentialRevocationClosureCheckpointPolicySnapshot",
        "ClosureCheckpointBoundCurrentRevocationConflictAdjudicatorCheckpoint"
        "WitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot",
        "StoredAdjudicatorCredentialRevocationCheckpointEvidence",
        "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_revocation_closure_checkpoint_"
        "evidence",
        "persist_current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_revocation_closure_checkpoint_"
        "corpus",
        "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_revocation_closure_checkpoints",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_runner_public_api_is_importable() -> None:
    runner = import_module(
        "ctrt.closure_checkpoint_gated_current_revocation_conflict_"
        "adjudicator_checkpoint_witness_conflict_adjudicator_credential_"
        "revocation_runner"
    )
    expected = {
        "CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_WITNESS_"
        "CONFLICT_ADJUDICATOR_CREDENTIAL_REVOCATION_CLOSURE_CHECKPOINT_"
        "VERIFIED_CHECKS",
        "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflict"
        "AdjudicatorCredentialRevocationClosureCheckpointExperimentError",
        "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflict"
        "AdjudicatorCredentialRevocationClosureCheckpointFinalManifest",
        "ClosureCheckpointGatedCurrentRevocationConflictAdjudicatorCheckpoint"
        "WitnessConflictAdjudicatorCredentialRevocationExperimentRunner",
        "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflict"
        "AdjudicatorCredentialRevocationClosureCheckpointRunnerStage",
        "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflict"
        "AdjudicatorCredentialRevocationClosureCheckpointRunnerStatus",
        "VerifiedCurrentRevocationConflictAdjudicatorCheckpointWitness"
        "ConflictAdjudicatorCredentialRevocationClosureCheckpointReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
