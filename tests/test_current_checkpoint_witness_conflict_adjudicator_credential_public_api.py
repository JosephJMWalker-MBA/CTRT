from ctrt import credentialed_current_checkpoint_witness_conflict_runner as runner
from ctrt import current_checkpoint_witness_conflict_adjudicator_credential as contract


def test_contract_public_api_is_importable() -> None:
    expected = {
        "CredentialAttestationSnapshot",
        "CredentialBoundCurrentCheckpointWitnessConflictCorpusSnapshot",
        "CredentialDecisionReport",
        "CredentialError",
        "CredentialPolicySnapshot",
        "StoredCredentialEvidence",
        "load_current_checkpoint_witness_conflict_credential_evidence",
        "persist_current_checkpoint_witness_conflict_credential_corpus",
        "validate_current_checkpoint_witness_conflict_credentials",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_runner_public_api_is_importable() -> None:
    expected = {
        "CREDENTIALED_CURRENT_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
        "CredentialedCurrentCheckpointWitnessConflictExperimentError",
        "CredentialedCurrentCheckpointWitnessConflictExperimentRunner",
        "CredentialedCurrentCheckpointWitnessConflictFinalManifest",
        "CredentialedCurrentCheckpointWitnessConflictRunnerStage",
        "CredentialedCurrentCheckpointWitnessConflictRunnerStatus",
        "VerifiedCredentialedCurrentCheckpointWitnessConflictReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
