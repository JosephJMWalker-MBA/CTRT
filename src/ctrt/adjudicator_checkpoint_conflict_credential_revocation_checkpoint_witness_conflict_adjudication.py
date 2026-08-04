"""Compatibility façade for checkpoint-conflict witness adjudication."""

from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    ConflictAdjudicationError,
    ConflictDecisionReport,
    StoredConflictAdjudicationEvidence,
    load_checkpoint_conflict_witness_adjudication_evidence,
    persist_checkpoint_conflict_witness_adjudication_corpus,
    validate_checkpoint_conflict_witness_adjudication,
)

__all__ = (
    "CheckpointConflictWitnessAdjudicationCorpusSnapshot",
    "ConflictAdjudicationError",
    "ConflictDecisionReport",
    "StoredConflictAdjudicationEvidence",
    "load_checkpoint_conflict_witness_adjudication_evidence",
    "persist_checkpoint_conflict_witness_adjudication_corpus",
    "validate_checkpoint_conflict_witness_adjudication",
)
