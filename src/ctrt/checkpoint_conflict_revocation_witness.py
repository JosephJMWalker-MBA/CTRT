"""Typed façade for checkpoint-conflict revocation checkpoint witnesses."""

from .adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    AdjudicatorCheckpointWitnessObservationSummary,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence,
    persist_witness_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_corpus,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations,
)

validate_witnesses = (
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations
)

__all__ = (
    "AdjudicatorCheckpointWitnessDecisionReport",
    "AdjudicatorCheckpointWitnessError",
    "AdjudicatorCheckpointWitnessObservationSummary",
    "StoredAdjudicatorCheckpointWitnessEvidence",
    "WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot",
    "load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence",
    "persist_witness_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_corpus",
    "validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations",
    "validate_witnesses",
)
