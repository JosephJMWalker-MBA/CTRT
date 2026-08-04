"""Typed façade for witnesses over the witness-conflict adjudicator checkpoint."""

from .checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    AdjudicatorCheckpointWitnessObservationSummary,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCheckpointCorpusSnapshot,
    load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_witness_evidence,
    persist_witness_bound_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_corpus,
    validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_witness_attestations,
)

validate_witnesses = (
    validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_witness_attestations
)

__all__ = (
    "AdjudicatorCheckpointWitnessDecisionReport",
    "AdjudicatorCheckpointWitnessError",
    "AdjudicatorCheckpointWitnessObservationSummary",
    "StoredAdjudicatorCheckpointWitnessEvidence",
    "WitnessBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCheckpointCorpusSnapshot",
    "load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_witness_evidence",
    "persist_witness_bound_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_corpus",
    "validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_witness_attestations",
    "validate_witnesses",
)
