from __future__ import annotations

import ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_ledger as contract
import ctrt.revocation_gated_checkpoint_witness_conflict_adjudication_runner as runner

CONTRACT_NAMES = (
    "AdjudicatorCredentialRevocationDecisionReport",
    "AdjudicatorCredentialRevocationError",
    "AdjudicatorCredentialRevocationEventSnapshot",
    "AdjudicatorCredentialRevocationLedgerSnapshot",
    "AdjudicatorCredentialRevocationPolicySnapshot",
    "RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot",
    "StoredAdjudicatorCredentialRevocationEvidence",
    "load_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence",
    "persist_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus",
    "validate_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger",
)

RUNNER_NAMES = (
    "CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS",
    "CheckpointWitnessConflictRevocationExperimentError",
    "CheckpointWitnessConflictRevocationFinalManifest",
    "CheckpointWitnessConflictRevocationRunnerStage",
    "CheckpointWitnessConflictRevocationRunnerStatus",
    "RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner",
    "VerifiedCheckpointWitnessConflictRevocationReceipt",
)


def test_checkpoint_witness_conflict_adjudicator_revocation_contract_api() -> None:
    for name in CONTRACT_NAMES:
        assert getattr(contract, name) is not None


def test_revocation_gated_checkpoint_witness_conflict_runner_api() -> None:
    for name in RUNNER_NAMES:
        assert getattr(runner, name) is not None
