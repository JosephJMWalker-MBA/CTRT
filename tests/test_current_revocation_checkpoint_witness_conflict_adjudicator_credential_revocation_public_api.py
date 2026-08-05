from ctrt import (
    current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger as contract,
)
from ctrt import revocation_gated_current_revocation_checkpoint_witness_conflict_runner as runner


def test_contract_public_api_is_importable() -> None:
    expected = {
        "AdjudicatorCredentialRevocationDecisionReport",
        "AdjudicatorCredentialRevocationError",
        "AdjudicatorCredentialRevocationEventSnapshot",
        "AdjudicatorCredentialRevocationLedgerSnapshot",
        "AdjudicatorCredentialRevocationPolicySnapshot",
        "RevocationBoundCurrentRevocationCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot",
        "StoredAdjudicatorCredentialRevocationEvidence",
        "load_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence",
        "persist_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus",
        "validate_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger",
    }
    assert set(contract.__all__) == expected
    for name in expected:
        assert getattr(contract, name) is not None


def test_runner_public_api_is_importable() -> None:
    expected = {
        "CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationFinalManifest",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage",
        "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus",
        "RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
        "VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt",
    }
    assert set(runner.__all__) == expected
    for name in expected:
        assert getattr(runner, name) is not None
