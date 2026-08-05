from __future__ import annotations

from importlib import import_module


def test_revocation_contract_public_api() -> None:
    module = import_module(
        "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential_revocation_ledger"
    )
    expected = {
        "AdjudicatorCredentialRevocationDecisionReport",
        "AdjudicatorCredentialRevocationError",
        "AdjudicatorCredentialRevocationEventSnapshot",
        "AdjudicatorCredentialRevocationLedgerSnapshot",
        "AdjudicatorCredentialRevocationPolicySnapshot",
        (
            "RevocationBoundCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessConflictAdjudicatorCredentialCorpusSnapshot"
        ),
        "StoredAdjudicatorCredentialRevocationEvidence",
        (
            "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
            "conflict_adjudicator_credential_revocation_evidence"
        ),
        (
            "persist_current_revocation_conflict_adjudicator_checkpoint_witness_"
            "conflict_adjudicator_credential_revocation_bound_corpus"
        ),
        (
            "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
            "conflict_adjudicator_credential_revocation_ledger"
        ),
    }
    assert set(module.__all__) == expected
    assert all(hasattr(module, name) for name in expected)


def test_revocation_runner_public_api() -> None:
    module = import_module(
        "ctrt.revocation_gated_current_revocation_conflict_adjudicator_"
        "checkpoint_witness_conflict_adjudicator_credential_runner"
    )
    expected = {
        (
            "REVOCATION_GATED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_"
            "CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_CREDENTIAL_"
            "VERIFIED_CHECKS"
        ),
        (
            "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessConflictAdjudicatorCredentialExperimentError"
        ),
        (
            "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessConflictAdjudicatorCredentialFinalManifest"
        ),
        (
            "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessConflictAdjudicatorCredentialExperimentRunner"
        ),
        (
            "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessConflictAdjudicatorCredentialRunnerStage"
        ),
        (
            "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessConflictAdjudicatorCredentialRunnerStatus"
        ),
        (
            "VerifiedRevocationGatedCurrentRevocationConflictAdjudicator"
            "CheckpointWitnessConflictAdjudicatorCredentialReceipt"
        ),
    }
    assert set(module.__all__) == expected
    assert all(hasattr(module, name) for name in expected)
