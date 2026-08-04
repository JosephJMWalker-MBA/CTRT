"""Gate the exact `1.15.0` credential on append-only revocation history."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

import ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints as cp
from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CheckpointExecutor,
)
from ctrt.adjudicator_credential_attestation import AdjudicatorCredentialPolicySnapshot
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential import (
    CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential import (
    CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
    CredentialError,
    CredentialPolicySnapshot,
    StoredCredentialEvidence,
    load_checkpoint_witness_conflict_credential_evidence,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationEvidence,
    load_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence,
    validate_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger,
)
from ctrt.credentialed_checkpoint_witness_conflict_adjudication_runner import (
    CredentialedCheckpointWitnessConflictExperimentError,
    CredentialedCheckpointWitnessConflictExperimentRunner,
    VerifiedCredentialedCheckpointWitnessConflictReceipt,
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
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness import (
    WitnessBoundCheckpointCorpusSnapshot,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCheckpointWitnessCorpusSnapshot,
)
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)

CheckpointCorpus = (
    cp.CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
)
CheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
CheckpointPolicy = cp.AdjudicatorCredentialRevocationCheckpointPolicySnapshot
CheckpointLog = cp.AdjudicatorCredentialRevocationCheckpointLogSnapshot
InheritedRevocationCorpus = (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
)

_ARTIFACT_PREFIX = (
    "checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-conflict-adjudicator-credential-revocation"
)


class CheckpointWitnessConflictRevocationRunnerStage(StrEnum):
    """Boundary at which the current revocation gate failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIAL_EXECUTION = "credential-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointWitnessConflictRevocationRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CheckpointWitnessConflictRevocationExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointWitnessConflictRevocationRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS = (
    "exact-1.15.0-credential-predecessor-preserved",
    "exact-current-revocation-policy-bound",
    "exact-current-revocation-ledger-and-events-bound",
    "issuer-authority-and-linear-supersession-reverified",
    "recording-freeze-publication-and-evaluation-chronology-reverified",
    "revocation-status-evaluated-before-current-credential-validation",
    "current-revocation-decision-persisted-before-pr37-execution",
    "revocation-and-all-downstream-outcomes-finalized-separately",
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
class CheckpointWitnessConflictRevocationFinalManifest:
    """Final marker preserving current revocation and delegated outcomes."""

    final_id: str
    experiment_run_id: str
    status: CheckpointWitnessConflictRevocationRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
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
        expected_status = CheckpointWitnessConflictRevocationRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("checkpoint-witness conflict revocation must be verified")
        if not self.revocation_event_refs:
            raise ValueError("checkpoint-witness conflict revocation requires events")
        downstream = (
            self.credential_outcome,
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.conflict_adjudication_outcome,
            self.predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
            self.credential_final_ref,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("revocation abstention may not claim downstream outcomes")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("revocation abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.credential_outcome is None or self.credential_final_ref is None:
                raise ValueError("revocation execution requires PR #37 evidence")
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
            != CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint-witness conflict revocation lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointWitnessConflictRevocationReceipt:
    """Proof of current as-of revocation status plus optional PR #37 result."""

    experiment_run_id: str
    status: CheckpointWitnessConflictRevocationRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
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
    credential_receipt: VerifiedCredentialedCheckpointWitnessConflictReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = CheckpointWitnessConflictRevocationRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("verified checkpoint-witness revocation status required")
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.credential_receipt is not None:
                raise ValueError("revocation abstention may not contain PR #37 receipt")
            downstream = (
                self.credential_outcome,
                self.checkpoint_witness_outcome,
                self.resolution_status,
                self.conflict_adjudication_outcome,
                self.predecessor_witness_outcome,
                self.inherited_revocation_outcome,
                self.inherited_credential_outcome,
                self.inherited_checkpoint_witness_outcome,
                self.inherited_resolution_status,
                self.inherited_adjudication_outcome,
            )
            if any(item is not None for item in downstream):
                raise ValueError("revocation abstention may not contain outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.credential_receipt
            if delegated is None:
                raise ValueError("revocation execution requires PR #37 receipt")
            if (
                delegated.credential_outcome is not self.credential_outcome
                or delegated.checkpoint_witness_outcome
                is not self.checkpoint_witness_outcome
                or delegated.resolution_status is not self.resolution_status
                or delegated.conflict_adjudication_outcome
                is not self.conflict_adjudication_outcome
                or delegated.predecessor_witness_outcome
                is not self.predecessor_witness_outcome
                or delegated.revocation_outcome
                is not self.inherited_revocation_outcome
                or delegated.inherited_credential_outcome
                is not self.inherited_credential_outcome
                or delegated.inherited_checkpoint_witness_outcome
                is not self.inherited_checkpoint_witness_outcome
                or delegated.inherited_resolution_status
                is not self.inherited_resolution_status
                or delegated.inherited_adjudication_outcome
                is not self.inherited_adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("PR #37 receipt differs from revocation receipt")
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
            != CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("verified checkpoint-witness revocation lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner:
    """Require active as-of status before executing exact PR #37."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CredentialedCheckpointWitnessConflictExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        current_revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        current_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        current_revocation_evaluated_at: str,
        current_credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("revocation-gated checkpoint conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match revocation-bound corpus exactly")
        if corpus.predecessor_corpus_ref != credential_corpus.reference():
            raise ValueError("revocation corpus must bind exact 1.15.0 predecessor")
        if corpus.corpus.reference() != credential_corpus.reference():
            raise ValueError("revocation corpus carries different 1.15.0 predecessor")
        if corpus.revocation_policy_ref != current_revocation_policy.reference():
            raise ValueError("current revocation policy differs from corpus")
        if corpus.revocation_ledger_ref != current_revocation_ledger.reference():
            raise ValueError("current revocation ledger differs from corpus")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        revocation_time = _parse_timestamp(
            current_revocation_evaluated_at,
            "current_revocation_evaluated_at",
        )
        credential_time = _parse_timestamp(
            current_credential_evaluated_at,
            "current_credential_evaluated_at",
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
            raise ValueError("revocation, credential, and PR #37 chronology differs")

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
        final: CheckpointWitnessConflictRevocationFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        policy: AdjudicatorCredentialRevocationPolicySnapshot,
        ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
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
            revocation_evidence.corpus_ref.artifact_id,
            expected_hash=revocation_evidence.corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.16.0 revocation corpus differs")
        predecessor = self._store.get(
            credential_corpus.reference().artifact_id,
            expected_hash=credential_corpus.reference().artifact_hash,
        )
        if predecessor.payload != credential_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.15.0 credential corpus differs")
        if self._store.get(
            revocation_evidence.revocation_policy_ref.artifact_id,
            expected_hash=revocation_evidence.revocation_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored current revocation policy differs")
        if self._store.get(
            revocation_evidence.revocation_ledger_ref.artifact_id,
            expected_hash=revocation_evidence.revocation_ledger_ref.artifact_hash,
        ).payload != ledger.canonical_payload:
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
            raise ArtifactIntegrityError("current revocation decision differs")
        if final.credential_final_ref is not None:
            self._store.get(
                final.credential_final_ref.artifact_id,
                expected_hash=final.credential_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessBoundCheckpointCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        revocation_corpus: InheritedRevocationCorpus,
        inherited_credential_corpus: (
            CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
        ),
        inherited_adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        checkpoint_policy: CheckpointPolicy,
        checkpoint_log: CheckpointLog,
        checkpoints: tuple[CheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        predecessor_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        current_issuer_registry: CredentialIssuerRegistrySnapshot,
        current_credential_policy: CredentialPolicySnapshot,
        current_revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        current_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        current_revocation_events: tuple[
            AdjudicatorCredentialRevocationEventSnapshot, ...
        ],
        inherited_witness_registry: CheckpointWitnessRegistrySnapshot,
        inherited_witness_policy: CheckpointWitnessPolicySnapshot,
        inherited_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        inherited_head_checkpoint: CheckpointSnapshot,
        inherited_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        inherited_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        inherited_adjudication: WitnessConflictAdjudicationSnapshot,
        inherited_issuer_registry: CredentialIssuerRegistrySnapshot,
        inherited_credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        inherited_witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        current_revocation_evaluated_at: str,
        current_credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_verified_at: str,
        predecessor_witness_evaluated_at: str,
        inherited_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        inherited_credential_evaluated_at: str,
        inherited_adjudication_evaluated_at: str,
        inherited_adjudication_completed_at: str,
        inherited_credential_completed_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> VerifiedCheckpointWitnessConflictRevocationReceipt:
        """Return revocation abstention or the exact delegated PR #37 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                credential_corpus=credential_corpus,
                current_revocation_policy=current_revocation_policy,
                current_revocation_ledger=current_revocation_ledger,
                experiment_run_id=experiment_run_id,
                current_revocation_evaluated_at=current_revocation_evaluated_at,
                current_credential_evaluated_at=current_credential_evaluated_at,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                prior_completed_at=prior_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointWitnessConflictRevocationExperimentError(
                CheckpointWitnessConflictRevocationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            revocation_evidence = (
                load_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence(
                    self._store,
                    corpus=corpus,
                    policy=current_revocation_policy,
                    ledger=current_revocation_ledger,
                )
            )
            credential_evidence = load_checkpoint_witness_conflict_credential_evidence(
                self._store,
                corpus=credential_corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=current_issuer_registry,
                credential_policy=current_credential_policy,
                adjudication=conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationError,
            CredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointWitnessConflictRevocationExperimentError(
                CheckpointWitnessConflictRevocationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = (
                validate_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger(
                    plan=plan,
                    corpus=corpus,
                    adjudicator_registry=conflict_adjudicator_registry,
                    issuer_registry=current_issuer_registry,
                    credential_policy=current_credential_policy,
                    revocation_policy=current_revocation_policy,
                    ledger=current_revocation_ledger,
                    attestations=credential_evidence.attestations,
                    adjudication=conflict_adjudication,
                    events=current_revocation_events,
                    evaluated_at=current_revocation_evaluated_at,
                )
            )
        except (AdjudicatorCredentialRevocationError, ValueError) as exc:
            raise CheckpointWitnessConflictRevocationExperimentError(
                CheckpointWitnessConflictRevocationRunnerStage.REVOCATION_VALIDATION,
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
            raise CheckpointWitnessConflictRevocationExperimentError(
                CheckpointWitnessConflictRevocationRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCredentialedCheckpointWitnessConflictReceipt | None = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            credential_plan = replace(
                plan,
                corpus_ref=credential_corpus.reference(),
                content_ids=credential_corpus.content_ids,
            )
            try:
                delegated = self._runner.run(
                    plan=credential_plan,
                    corpus=credential_corpus,
                    adjudication_corpus=adjudication_corpus,
                    witness_predecessor=witness_predecessor,
                    checkpoint_corpus=checkpoint_corpus,
                    revocation_corpus=revocation_corpus,
                    inherited_credential_corpus=inherited_credential_corpus,
                    inherited_adjudication_corpus=inherited_adjudication_corpus,
                    checkpoint_policy=checkpoint_policy,
                    checkpoint_log=checkpoint_log,
                    checkpoints=checkpoints,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    conflict_witness_attestations=conflict_witness_attestations,
                    predecessor_witness_attestations=(
                        predecessor_witness_attestations
                    ),
                    conflict_adjudicator_registry=conflict_adjudicator_registry,
                    conflict_adjudication_policy=conflict_adjudication_policy,
                    conflict_adjudication=conflict_adjudication,
                    current_issuer_registry=current_issuer_registry,
                    current_credential_policy=current_credential_policy,
                    current_credentials=credential_evidence.attestations,
                    inherited_witness_registry=inherited_witness_registry,
                    inherited_witness_policy=inherited_witness_policy,
                    inherited_witness_attestations=inherited_witness_attestations,
                    inherited_head_checkpoint=inherited_head_checkpoint,
                    inherited_adjudicator_registry=inherited_adjudicator_registry,
                    inherited_adjudication_policy=inherited_adjudication_policy,
                    inherited_adjudication=inherited_adjudication,
                    inherited_issuer_registry=inherited_issuer_registry,
                    inherited_credential_policy=inherited_credential_policy,
                    revocation_policy=revocation_policy,
                    revocation_ledger=revocation_ledger,
                    revocation_events=revocation_events,
                    inherited_witness_receipt=inherited_witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    current_credential_evaluated_at=current_credential_evaluated_at,
                    conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                    conflict_adjudication_evaluated_at=(
                        conflict_adjudication_evaluated_at
                    ),
                    checkpoint_verified_at=checkpoint_verified_at,
                    predecessor_witness_evaluated_at=(
                        predecessor_witness_evaluated_at
                    ),
                    inherited_witness_evaluated_at=inherited_witness_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    inherited_credential_evaluated_at=(
                        inherited_credential_evaluated_at
                    ),
                    inherited_adjudication_evaluated_at=(
                        inherited_adjudication_evaluated_at
                    ),
                    inherited_adjudication_completed_at=(
                        inherited_adjudication_completed_at
                    ),
                    inherited_credential_completed_at=(
                        inherited_credential_completed_at
                    ),
                    revocation_completed_at=revocation_completed_at,
                    checkpoint_completed_at=checkpoint_completed_at,
                    prior_completed_at=prior_completed_at,
                    completed_at=prior_completed_at,
                )
            except CredentialedCheckpointWitnessConflictExperimentError as exc:
                raise CheckpointWitnessConflictRevocationExperimentError(
                    CheckpointWitnessConflictRevocationRunnerStage.CREDENTIAL_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated is None:
            credential_outcome = None
            checkpoint_witness_outcome = None
            resolution_status = None
            conflict_adjudication_outcome = None
            predecessor_witness_outcome = None
            inherited_revocation_outcome = None
            inherited_credential_outcome = None
            inherited_checkpoint_witness_outcome = None
            inherited_resolution_status = None
            inherited_adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            credential_final_ref = None
            suffix = "abstention"
        else:
            credential_outcome = delegated.credential_outcome
            checkpoint_witness_outcome = delegated.checkpoint_witness_outcome
            resolution_status = delegated.resolution_status
            conflict_adjudication_outcome = delegated.conflict_adjudication_outcome
            predecessor_witness_outcome = delegated.predecessor_witness_outcome
            inherited_revocation_outcome = delegated.revocation_outcome
            inherited_credential_outcome = delegated.inherited_credential_outcome
            inherited_checkpoint_witness_outcome = (
                delegated.inherited_checkpoint_witness_outcome
            )
            inherited_resolution_status = delegated.inherited_resolution_status
            inherited_adjudication_outcome = delegated.inherited_adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            credential_final_ref = delegated.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CheckpointWitnessConflictRevocationFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointWitnessConflictRevocationRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            credential_outcome=credential_outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
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
            verified_checks=CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS,
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
            raise CheckpointWitnessConflictRevocationExperimentError(
                CheckpointWitnessConflictRevocationRunnerStage.FINAL_PERSISTENCE,
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
                policy=current_revocation_policy,
                ledger=current_revocation_ledger,
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
            raise CheckpointWitnessConflictRevocationExperimentError(
                CheckpointWitnessConflictRevocationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointWitnessConflictRevocationReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointWitnessConflictRevocationRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            credential_outcome=credential_outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
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
            credential_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CHECKPOINT_WITNESS_CONFLICT_REVOCATION_VERIFIED_CHECKS",
    "CheckpointWitnessConflictRevocationExperimentError",
    "CheckpointWitnessConflictRevocationFinalManifest",
    "CheckpointWitnessConflictRevocationRunnerStage",
    "CheckpointWitnessConflictRevocationRunnerStatus",
    "RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner",
    "VerifiedCheckpointWitnessConflictRevocationReceipt",
]
