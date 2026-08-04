from __future__ import annotations

from ctrt import (
    checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints
    as checkpoints,
)

EXPECTED_NAMES = (
    "CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot",
    "load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_evidence",
    "persist_checkpoint_bound_checkpoint_conflict_witness_adjudicator_credential_revocation_corpus",
    "validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints",
)


def test_checkpoint_contract_symbols_are_importable() -> None:
    for name in EXPECTED_NAMES:
        assert getattr(checkpoints, name) is not None
