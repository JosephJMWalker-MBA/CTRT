from __future__ import annotations

import ctrt.checkpoint_witness_conflict_adjudicator_credential as contract
import ctrt.credentialed_checkpoint_witness_conflict_adjudication_runner as runner

CONTRACT_NAMES = (
    "CredentialAttestationSnapshot",
    "CredentialBoundCheckpointWitnessConflictCorpusSnapshot",
    "CredentialDecisionReport",
    "CredentialError",
    "CredentialPolicySnapshot",
    "StoredCredentialEvidence",
    "load_checkpoint_witness_conflict_credential_evidence",
    "persist_checkpoint_witness_conflict_credential_corpus",
    "validate_checkpoint_witness_conflict_credentials",
)

RUNNER_NAMES = (
    "CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
    "CredentialedCheckpointWitnessConflictExperimentError",
    "CredentialedCheckpointWitnessConflictExperimentRunner",
    "CredentialedCheckpointWitnessConflictFinalManifest",
    "CredentialedCheckpointWitnessConflictRunnerStage",
    "CredentialedCheckpointWitnessConflictRunnerStatus",
    "VerifiedCredentialedCheckpointWitnessConflictReceipt",
)


def test_checkpoint_witness_conflict_adjudicator_credential_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_credentialed_checkpoint_witness_conflict_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
