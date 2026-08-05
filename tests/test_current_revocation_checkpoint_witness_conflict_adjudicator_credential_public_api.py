from __future__ import annotations

from importlib import import_module

contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_credential"
)
runner = import_module(
    "ctrt.credentialed_current_revocation_checkpoint_witness_conflict_runner"
)


def test_current_revocation_conflict_credential_contract_public_api() -> None:
    expected = {
        "CredentialAttestationSnapshot",
        "CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot",
        "CredentialDecisionReport",
        "CredentialError",
        "CredentialPolicySnapshot",
        "StoredCredentialEvidence",
        "load_current_revocation_checkpoint_witness_conflict_credential_evidence",
        "persist_current_revocation_checkpoint_witness_conflict_credential_corpus",
        "validate_current_revocation_checkpoint_witness_conflict_credentials",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_credentialed_current_revocation_conflict_runner_public_api() -> None:
    expected = {
        "CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
        "CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError",
        "CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
        "CredentialedCurrentRevocationCheckpointWitnessConflictFinalManifest",
        "CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage",
        "CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus",
        "VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
