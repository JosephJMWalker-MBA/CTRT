from __future__ import annotations

from importlib import import_module


def test_current_conflict_adjudicator_credential_public_api() -> None:
    contract = import_module(
        "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
        "conflict_adjudicator_credential"
    )
    assert set(contract.__all__) == {
        "CredentialAttestationSnapshot",
        (
            "CredentialBoundCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessCorpusSnapshot"
        ),
        "CredentialDecisionReport",
        "CredentialError",
        "CredentialPolicySnapshot",
        "StoredCredentialEvidence",
        (
            "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
            "credential_evidence"
        ),
        (
            "persist_current_revocation_conflict_adjudicator_checkpoint_witness_"
            "credential_corpus"
        ),
        (
            "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
            "credentials"
        ),
    }

    runner = import_module(
        "ctrt.credentialed_current_revocation_conflict_adjudicator_checkpoint_"
        "witness_runner"
    )
    assert set(runner.__all__) == {
        (
            "CREDENTIALED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
            "WITNESS_VERIFIED_CHECKS"
        ),
        (
            "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
            "ExperimentError"
        ),
        (
            "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
            "FinalManifest"
        ),
        (
            "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
            "ExperimentRunner"
        ),
        (
            "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
            "RunnerStage"
        ),
        (
            "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
            "RunnerStatus"
        ),
        (
            "VerifiedCredentialedCurrentRevocationConflictAdjudicatorCheckpoint"
            "WitnessReceipt"
        ),
    }
