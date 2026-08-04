from __future__ import annotations

import ctrt

EXPECTED_PUBLIC_NAMES = {
    "CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS",
    "CheckpointConflictWitnessRevocationExperimentError",
    "CheckpointConflictWitnessRevocationFinalManifest",
    "CheckpointConflictWitnessRevocationRunnerStage",
    "CheckpointConflictWitnessRevocationRunnerStatus",
    "RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot",
    "RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner",
    "VerifiedCheckpointConflictWitnessRevocationReceipt",
    "load_checkpoint_conflict_witness_adjudicator_credential_revocation_evidence",
    "persist_checkpoint_conflict_witness_adjudicator_credential_revocation_bound_corpus",
    "validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger",
}


def test_witness_conflict_revocation_contract_is_public() -> None:
    assert EXPECTED_PUBLIC_NAMES <= set(ctrt.__all__)
    for name in EXPECTED_PUBLIC_NAMES:
        assert getattr(ctrt, name) is not None
