"""Gate the exact `1.25.0` credential on append-only revocation history."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    StoredAdjudicatorCredentialRevocationEvidence,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.credentialed_current_revocation_checkpoint_witness_conflict_runner import (
    CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError,
    CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner,
    VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt,
)
from ctrt.current_revocation_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
)
from ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_credential import (
    CredentialAttestationSnapshot,
    CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
    CredentialError,
    CredentialPolicySnapshot,
    StoredCredentialEvidence,
    load_current_revocation_checkpoint_witness_conflict_credential_evidence,
)
from ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger import (
    RevocationBoundCurrentRevocationCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
    load_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence,
    validate_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)

_ARTIFACT_PREFIX = (
    "current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation"
)


class CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage(
    StrEnum
):
    """Boundary at which the current revocation conflict gate failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIAL_EXECUTION = "credential-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus(
    StrEnum
):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
    RuntimeError
):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS = (
    "exact-1.25.0-credential-predecessor-preserved",
    "exact-current-revocation-conflict-adjudicator-revocation-policy-bound",
    "exact-current-revocation-conflict-adjudicator-revocation-ledger-and-events-bound",
    "issuer-authority-and-linear-supersession-reverified",
    "recording-freeze-publication-and-evaluation-chronology-reverified",
    "revocation-status-evaluated-before-current-revocation-conflict-credential",
    "current-revocation-conflict-adjudicator-revocation-decision-persisted-before-pr47",
    "revocation-and-all-pr47-outcomes-finalized-separately",
)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


@dataclass(frozen=True, slots=True)
class CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationFinalManifest:
    """Final marker preserving revocation and every delegated outcome separately."""

    final_id: str
    experiment_run_id: str
    status: CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus
    current_revocation_checkpoint_conflict_adjudicator_revocation_outcome: (
        CredentialDecisionOutcome
    )
    current_revocation_checkpoint_conflict_adjudicator_credential_outcome: (
        CredentialDecisionOutcome | None
    )
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_revocation_checkpoint_resolution_status: (
        WitnessConflictResolutionStatus | None
    )
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome | None
    )
    resolved_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    current_conflict_adjudicator_credential_outcome: CredentialDecisionOutcome | None
    conflicting_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_resolution_status: WitnessConflictResolutionStatus | None
    current_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    resolved_current_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_revocation_outcome: CredentialDecisionOutcome | None
    current_credential_outcome: CredentialDecisionOutcome | None
    lower_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    lower_resolution_status: WitnessConflictResolutionStatus | None
    lower_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    lower_predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    predecessor_credential_corpus_ref: VersionedArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    revocation_decision_ref: StoredArtifactRef
    credential_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("current revocation conflict-adjudicator revocation must be verified")
        if not self.revocation_event_refs:
            raise ValueError("current revocation conflict-adjudicator revocation requires events")
        if len(self.revocation_event_refs) != len(set(self.revocation_event_refs)):
            raise ValueError("current revocation conflict-adjudicator refs must be unique")
        downstream = (
            self.current_revocation_checkpoint_conflict_adjudicator_credential_outcome,
            self.conflicting_current_revocation_checkpoint_witness_outcome,
            self.current_revocation_checkpoint_resolution_status,
            self.current_revocation_checkpoint_conflict_adjudication_outcome,
            self.resolved_current_revocation_checkpoint_witness_outcome,
            self.current_conflict_adjudicator_revocation_outcome,
            self.current_conflict_adjudicator_credential_outcome,
            self.conflicting_witness_outcome,
            self.current_resolution_status,
            self.current_conflict_adjudication_outcome,
            self.resolved_current_witness_outcome,
            self.current_revocation_outcome,
            self.current_credential_outcome,
            self.lower_checkpoint_witness_outcome,
            self.lower_resolution_status,
            self.lower_conflict_adjudication_outcome,
            self.lower_predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if (
            self.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
            is CredentialDecisionOutcome.ABSTAIN
        ):
            if any(item is not None for item in downstream):
                raise ValueError("revocation abstention may not claim PR #47 outcomes")
            if self.credential_final_ref is not None:
                raise ValueError("revocation abstention may not contain PR #47 final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("revocation abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.credential_final_ref is None:
                raise ValueError("revocation execution requires PR #47 final")
            if (
                self.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
                is None
            ):
                raise ValueError("revocation execution requires PR #47 outcomes")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from revocation terminal outcome")
        if (
            self.verified_checks
            != CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("current revocation conflict-adjudicator lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt:
    """Proof of as-of revocation status plus optional exact PR #47 result."""

    experiment_run_id: str
    status: CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus
    current_revocation_checkpoint_conflict_adjudicator_revocation_outcome: (
        CredentialDecisionOutcome
    )
    current_revocation_checkpoint_conflict_adjudicator_credential_outcome: (
        CredentialDecisionOutcome | None
    )
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_revocation_checkpoint_resolution_status: (
        WitnessConflictResolutionStatus | None
    )
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome | None
    )
    resolved_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    current_conflict_adjudicator_credential_outcome: CredentialDecisionOutcome | None
    conflicting_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_resolution_status: WitnessConflictResolutionStatus | None
    current_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    resolved_current_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_revocation_outcome: CredentialDecisionOutcome | None
    current_credential_outcome: CredentialDecisionOutcome | None
    lower_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    lower_resolution_status: WitnessConflictResolutionStatus | None
    lower_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    lower_predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    predecessor_credential_corpus_ref: VersionedArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    revocation_decision_ref: StoredArtifactRef
    credential_receipt: (
        VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("verified current revocation conflict-adjudicator required")
        downstream = (
            self.current_revocation_checkpoint_conflict_adjudicator_credential_outcome,
            self.conflicting_current_revocation_checkpoint_witness_outcome,
            self.current_revocation_checkpoint_resolution_status,
            self.current_revocation_checkpoint_conflict_adjudication_outcome,
            self.resolved_current_revocation_checkpoint_witness_outcome,
            self.current_conflict_adjudicator_revocation_outcome,
            self.current_conflict_adjudicator_credential_outcome,
            self.conflicting_witness_outcome,
            self.current_resolution_status,
            self.current_conflict_adjudication_outcome,
            self.resolved_current_witness_outcome,
            self.current_revocation_outcome,
            self.current_credential_outcome,
            self.lower_checkpoint_witness_outcome,
            self.lower_resolution_status,
            self.lower_conflict_adjudication_outcome,
            self.lower_predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if (
            self.current_revocation_checkpoint_conflict_adjudicator_revocation_outcome
            is CredentialDecisionOutcome.ABSTAIN
        ):
            if self.credential_receipt is not None:
                raise ValueError("revocation abstention may not contain PR #47 receipt")
            if any(item is not None for item in downstream):
                raise ValueError("revocation abstention may not contain PR #47 outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.credential_receipt
            if delegated is None:
                raise ValueError("revocation execution requires PR #47 receipt")
            if delegated.experiment_run_id != self.experiment_run_id:
                raise ValueError("PR #47 receipt belongs to another experiment run")
            delegated_values = (
                delegated.current_revocation_checkpoint_conflict_adjudicator_credential_outcome,
                delegated.conflicting_current_revocation_checkpoint_witness_outcome,
                delegated.current_revocation_checkpoint_resolution_status,
                delegated.current_revocation_checkpoint_conflict_adjudication_outcome,
                delegated.resolved_current_revocation_checkpoint_witness_outcome,
                delegated.current_conflict_adjudicator_revocation_outcome,
                delegated.current_conflict_adjudicator_credential_outcome,
                delegated.conflicting_witness_outcome,
                delegated.current_resolution_status,
                delegated.current_conflict_adjudication_outcome,
                delegated.resolved_current_witness_outcome,
                delegated.current_revocation_outcome,
                delegated.current_credential_outcome,
                delegated.lower_checkpoint_witness_outcome,
                delegated.lower_resolution_status,
                delegated.lower_conflict_adjudication_outcome,
                delegated.lower_predecessor_witness_outcome,
                delegated.inherited_revocation_outcome,
                delegated.inherited_credential_outcome,
                delegated.inherited_checkpoint_witness_outcome,
                delegated.inherited_resolution_status,
                delegated.inherited_adjudication_outcome,
            )
            if delegated_values != downstream:
                raise ValueError("PR #47 receipt differs from revocation receipt")
            if delegated.terminal_outcome is not self.terminal_outcome:
                raise ValueError("PR #47 terminal outcome differs")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong revocation outcome")
        if (
            self.verified_checks
            != CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("verified current revocation conflict-adjudicator lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner:
    """Require active as-of status before executing exact PR #47."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCurrentRevocationCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("revocation-gated current conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match revocation-bound corpus exactly")
        if corpus.predecessor_corpus_ref != credential_corpus.reference():
            raise ValueError("revocation corpus must bind exact 1.25.0 predecessor")
        if corpus.corpus.reference() != credential_corpus.reference():
            raise ValueError("revocation corpus carries different 1.25.0 predecessor")
        if corpus.revocation_policy_ref != revocation_policy.reference():
            raise ValueError("current revocation conflict-adjudicator policy differs")
        if corpus.revocation_ledger_ref != revocation_ledger.reference():
            raise ValueError("current revocation conflict-adjudicator ledger differs")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        credential_time = _parse_timestamp(
            credential_evaluated_at,
            "credential_evaluated_at",
        )
        witness_time = _parse_timestamp(
            conflict_witness_evaluated_at,
            "conflict_witness_evaluated_at",
        )
        prior_completed = _parse_timestamp(prior_completed_at, "prior_completed_at")
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= revocation_time
            <= credential_time
            <= witness_time
            <= prior_completed
            <= completed
        ):
            raise ValueError("revocation, credential, and PR #47 chronology differs")

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision"
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored current revocation decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: RevocationBoundCurrentRevocationCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_evidence: StoredAdjudicatorCredentialRevocationEvidence,
        credential_evidence: StoredCredentialEvidence,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored current revocation final differs")
        if self._store.get(
            final.revocation_corpus_ref.artifact_id,
            expected_hash=final.revocation_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.26.0 revocation corpus differs")
        predecessor = self._store.get(
            credential_corpus.reference().artifact_id,
            expected_hash=credential_corpus.reference().artifact_hash,
        )
        if predecessor.payload != credential_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.25.0 credential corpus differs")
        if self._store.get(
            final.revocation_policy_ref.artifact_id,
            expected_hash=final.revocation_policy_ref.artifact_hash,
        ).payload != revocation_policy.canonical_payload:
            raise ArtifactIntegrityError("stored current revocation policy differs")
        if self._store.get(
            final.revocation_ledger_ref.artifact_id,
            expected_hash=final.revocation_ledger_ref.artifact_hash,
        ).payload != revocation_ledger.canonical_payload:
            raise ArtifactIntegrityError("stored current revocation ledger differs")
        for reference in (
            *revocation_evidence.event_refs,
            credential_evidence.adjudicator_registry_ref,
            credential_evidence.issuer_registry_ref,
            credential_evidence.credential_policy_ref,
            credential_evidence.adjudication_ref,
            *credential_evidence.attestation_refs,
        ):
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        expected_decision = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            decision,
        )
        if self._store.get(
            final.revocation_decision_ref.artifact_id,
            expected_hash=final.revocation_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError("stored current revocation decision differs")
        if final.credential_final_ref is not None:
            self._store.get(
                final.credential_final_ref.artifact_id,
                expected_hash=final.credential_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCurrentRevocationCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: CredentialPolicySnapshot,
        credentials: tuple[CredentialAttestationSnapshot, ...],
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        experiment_run_id: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
        **delegated_inputs: Any,
    ) -> VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt:
        """Return revocation abstention or the exact delegated PR #47 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                credential_corpus=credential_corpus,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                prior_completed_at=prior_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            revocation_evidence = (
                load_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence(
                    self._store,
                    corpus=corpus,
                    policy=revocation_policy,
                    ledger=revocation_ledger,
                )
            )
            credential_evidence = (
                load_current_revocation_checkpoint_witness_conflict_credential_evidence(
                    self._store,
                    corpus=credential_corpus,
                    adjudicator_registry=conflict_adjudicator_registry,
                    issuer_registry=credential_issuer_registry,
                    credential_policy=credential_policy,
                    adjudication=conflict_adjudication,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationError,
            CredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = (
                validate_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger(
                    plan=plan,
                    corpus=corpus,
                    adjudicator_registry=conflict_adjudicator_registry,
                    issuer_registry=credential_issuer_registry,
                    credential_policy=credential_policy,
                    revocation_policy=revocation_policy,
                    ledger=revocation_ledger,
                    attestations=credential_evidence.attestations,
                    adjudication=conflict_adjudication,
                    events=revocation_events,
                    evaluated_at=revocation_evaluated_at,
                )
            )
        except (AdjudicatorCredentialRevocationError, ValueError) as exc:
            raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.REVOCATION_VALIDATION,
                str(exc),
            ) from exc

        try:
            decision_ref = self._persist_decision(
                experiment_run_id=experiment_run_id,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated_receipt: (
            VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt | None
        ) = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            credential_plan = replace(
                plan,
                corpus_ref=credential_corpus.reference(),
                content_ids=credential_corpus.content_ids,
            )
            try:
                delegated_receipt = self._runner.run(
                    plan=credential_plan,
                    corpus=credential_corpus,
                    adjudication_corpus=adjudication_corpus,
                    conflict_adjudicator_registry=conflict_adjudicator_registry,
                    credential_issuer_registry=credential_issuer_registry,
                    credential_policy=credential_policy,
                    credentials=credential_evidence.attestations,
                    conflict_adjudication=conflict_adjudication,
                    experiment_run_id=experiment_run_id,
                    credential_evaluated_at=credential_evaluated_at,
                    conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                    prior_completed_at=prior_completed_at,
                    completed_at=prior_completed_at,
                    **delegated_inputs,
                )
            except CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError as exc:
                raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                    CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.CREDENTIAL_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated_receipt is None:
            delegated_values: tuple[Any, ...] = (None,) * 22
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            credential_final_ref = None
            suffix = "abstention"
        else:
            delegated_values = (
                delegated_receipt.current_revocation_checkpoint_conflict_adjudicator_credential_outcome,
                delegated_receipt.conflicting_current_revocation_checkpoint_witness_outcome,
                delegated_receipt.current_revocation_checkpoint_resolution_status,
                delegated_receipt.current_revocation_checkpoint_conflict_adjudication_outcome,
                delegated_receipt.resolved_current_revocation_checkpoint_witness_outcome,
                delegated_receipt.current_conflict_adjudicator_revocation_outcome,
                delegated_receipt.current_conflict_adjudicator_credential_outcome,
                delegated_receipt.conflicting_witness_outcome,
                delegated_receipt.current_resolution_status,
                delegated_receipt.current_conflict_adjudication_outcome,
                delegated_receipt.resolved_current_witness_outcome,
                delegated_receipt.current_revocation_outcome,
                delegated_receipt.current_credential_outcome,
                delegated_receipt.lower_checkpoint_witness_outcome,
                delegated_receipt.lower_resolution_status,
                delegated_receipt.lower_conflict_adjudication_outcome,
                delegated_receipt.lower_predecessor_witness_outcome,
                delegated_receipt.inherited_revocation_outcome,
                delegated_receipt.inherited_credential_outcome,
                delegated_receipt.inherited_checkpoint_witness_outcome,
                delegated_receipt.inherited_resolution_status,
                delegated_receipt.inherited_adjudication_outcome,
            )
            terminal_outcome = delegated_receipt.terminal_outcome
            credential_final_ref = delegated_receipt.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        (
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome,
            conflicting_current_revocation_checkpoint_witness_outcome,
            current_revocation_checkpoint_resolution_status,
            current_revocation_checkpoint_conflict_adjudication_outcome,
            resolved_current_revocation_checkpoint_witness_outcome,
            current_conflict_adjudicator_revocation_outcome,
            current_conflict_adjudicator_credential_outcome,
            conflicting_witness_outcome,
            current_resolution_status,
            current_conflict_adjudication_outcome,
            resolved_current_witness_outcome,
            current_revocation_outcome,
            current_credential_outcome,
            lower_checkpoint_witness_outcome,
            lower_resolution_status,
            lower_conflict_adjudication_outcome,
            lower_predecessor_witness_outcome,
            inherited_revocation_outcome,
            inherited_credential_outcome,
            inherited_checkpoint_witness_outcome,
            inherited_resolution_status,
            inherited_adjudication_outcome,
        ) = delegated_values

        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus.VERIFIED
            ),
            current_revocation_checkpoint_conflict_adjudicator_revocation_outcome=(
                decision.outcome
            ),
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome=(
                current_revocation_checkpoint_conflict_adjudicator_credential_outcome
            ),
            conflicting_current_revocation_checkpoint_witness_outcome=(
                conflicting_current_revocation_checkpoint_witness_outcome
            ),
            current_revocation_checkpoint_resolution_status=(
                current_revocation_checkpoint_resolution_status
            ),
            current_revocation_checkpoint_conflict_adjudication_outcome=(
                current_revocation_checkpoint_conflict_adjudication_outcome
            ),
            resolved_current_revocation_checkpoint_witness_outcome=(
                resolved_current_revocation_checkpoint_witness_outcome
            ),
            current_conflict_adjudicator_revocation_outcome=(
                current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=conflicting_witness_outcome,
            current_resolution_status=current_resolution_status,
            current_conflict_adjudication_outcome=(
                current_conflict_adjudication_outcome
            ),
            resolved_current_witness_outcome=resolved_current_witness_outcome,
            current_revocation_outcome=current_revocation_outcome,
            current_credential_outcome=current_credential_outcome,
            lower_checkpoint_witness_outcome=lower_checkpoint_witness_outcome,
            lower_resolution_status=lower_resolution_status,
            lower_conflict_adjudication_outcome=lower_conflict_adjudication_outcome,
            lower_predecessor_witness_outcome=lower_predecessor_witness_outcome,
            inherited_revocation_outcome=inherited_revocation_outcome,
            inherited_credential_outcome=inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=inherited_resolution_status,
            inherited_adjudication_outcome=inherited_adjudication_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=revocation_evidence.corpus_ref,
            predecessor_credential_corpus_ref=corpus.predecessor_corpus_ref,
            revocation_policy_ref=revocation_evidence.revocation_policy_ref,
            revocation_ledger_ref=revocation_evidence.revocation_ledger_ref,
            revocation_event_refs=revocation_evidence.event_refs,
            adjudication_ref=credential_evidence.adjudication_ref,
            revocation_decision_ref=decision_ref,
            credential_final_ref=credential_final_ref,
            verified_checks=(
                CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(serialize_artifact(final.final_id, final))
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                credential_corpus=credential_corpus,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                revocation_evidence=revocation_evidence,
                credential_evidence=credential_evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt(
            experiment_run_id=experiment_run_id,
            status=(
                CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus.VERIFIED
            ),
            current_revocation_checkpoint_conflict_adjudicator_revocation_outcome=(
                decision.outcome
            ),
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome=(
                current_revocation_checkpoint_conflict_adjudicator_credential_outcome
            ),
            conflicting_current_revocation_checkpoint_witness_outcome=(
                conflicting_current_revocation_checkpoint_witness_outcome
            ),
            current_revocation_checkpoint_resolution_status=(
                current_revocation_checkpoint_resolution_status
            ),
            current_revocation_checkpoint_conflict_adjudication_outcome=(
                current_revocation_checkpoint_conflict_adjudication_outcome
            ),
            resolved_current_revocation_checkpoint_witness_outcome=(
                resolved_current_revocation_checkpoint_witness_outcome
            ),
            current_conflict_adjudicator_revocation_outcome=(
                current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=conflicting_witness_outcome,
            current_resolution_status=current_resolution_status,
            current_conflict_adjudication_outcome=(
                current_conflict_adjudication_outcome
            ),
            resolved_current_witness_outcome=resolved_current_witness_outcome,
            current_revocation_outcome=current_revocation_outcome,
            current_credential_outcome=current_credential_outcome,
            lower_checkpoint_witness_outcome=lower_checkpoint_witness_outcome,
            lower_resolution_status=lower_resolution_status,
            lower_conflict_adjudication_outcome=lower_conflict_adjudication_outcome,
            lower_predecessor_witness_outcome=lower_predecessor_witness_outcome,
            inherited_revocation_outcome=inherited_revocation_outcome,
            inherited_credential_outcome=inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=inherited_resolution_status,
            inherited_adjudication_outcome=inherited_adjudication_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=revocation_evidence.corpus_ref,
            predecessor_credential_corpus_ref=corpus.predecessor_corpus_ref,
            revocation_policy_ref=revocation_evidence.revocation_policy_ref,
            revocation_ledger_ref=revocation_evidence.revocation_ledger_ref,
            revocation_event_refs=revocation_evidence.event_refs,
            adjudication_ref=credential_evidence.adjudication_ref,
            revocation_decision_ref=decision_ref,
            credential_receipt=delegated_receipt,
            final_manifest_ref=final_ref,
            verified_checks=(
                CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS",
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationExperimentError",
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationFinalManifest",
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStage",
    "CurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationRunnerStatus",
    "RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
    "VerifiedCurrentRevocationCheckpointWitnessConflictAdjudicatorRevocationReceipt",
]
