"""Gate witness-conflict adjudicator credentials on append-only revocation history."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CheckpointExecutor,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialPolicySnapshot,
)
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
    StoredCredentialEvidence,
    load_checkpoint_conflict_witness_adjudicator_credential_evidence,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationEvidence,
    load_checkpoint_conflict_witness_adjudicator_credential_revocation_evidence,
    validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.credentialed_checkpoint_conflict_witness_adjudication_runner import (
    CheckpointConflictWitnessCredentialExperimentError,
    CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner,
    VerifiedCheckpointConflictWitnessCredentialReceipt,
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
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)


class CheckpointConflictWitnessRevocationRunnerStage(StrEnum):
    """Boundary at which revocation-gated witness adjudication failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIAL_EXECUTION = "credential-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictWitnessRevocationRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CheckpointConflictWitnessRevocationExperimentError(RuntimeError):
    """Fail-closed error preserving the exact failed stage."""

    def __init__(
        self,
        stage: CheckpointConflictWitnessRevocationRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS = (
    "exact-witness-conflict-adjudicator-revocation-policy-bound",
    "exact-witness-conflict-adjudicator-revocation-ledger-and-events-bound",
    "issuer-authority-and-linear-supersession-reverified",
    "event-recording-ledger-publication-and-evaluation-chronology-reverified",
    "credential-status-evaluated-before-credential-authorization",
    "revocation-decision-persisted-before-credential-execution",
    "credential-adjudication-witness-and-dissent-evidence-left-immutable",
    "revocation-credential-and-adjudication-outcomes-finalized-separately",
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
class CheckpointConflictWitnessRevocationFinalManifest:
    """Final marker for revocation abstention or delegated credential execution."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictWitnessRevocationRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
        if self.status is not CheckpointConflictWitnessRevocationRunnerStatus.VERIFIED:
            raise ValueError("witness-conflict revocation status must be verified")
        if not self.revocation_event_refs:
            raise ValueError("witness-conflict revocation final requires events")
        downstream = (
            self.credential_outcome,
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.adjudication_outcome,
            self.credential_final_ref,
        )
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("revocation abstention may not claim downstream outcomes")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("revocation abstention must be terminal")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-abstention"
            )
        else:
            if self.credential_outcome is None or self.credential_final_ref is None:
                raise ValueError("revocation execution requires credential evidence")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudicator-credential-revocation-"
                    "terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from revocation terminal outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("witness-conflict revocation final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictWitnessRevocationReceipt:
    """Proof of as-of revocation eligibility and optional credential execution."""

    experiment_run_id: str
    status: CheckpointConflictWitnessRevocationRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
    credential_receipt: VerifiedCheckpointConflictWitnessCredentialReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictWitnessRevocationRunnerStatus.VERIFIED:
            raise ValueError("verified witness-conflict revocation status required")
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.credential_receipt is not None:
                raise ValueError("revocation abstention may not contain credential receipt")
            if any(
                item is not None
                for item in (
                    self.credential_outcome,
                    self.checkpoint_witness_outcome,
                    self.resolution_status,
                    self.adjudication_outcome,
                )
            ):
                raise ValueError("revocation abstention may not contain outcomes")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-abstention"
            )
        else:
            delegated = self.credential_receipt
            if delegated is None:
                raise ValueError("revocation execution requires credential receipt")
            if (
                delegated.credential_outcome is not self.credential_outcome
                or delegated.checkpoint_witness_outcome
                is not self.checkpoint_witness_outcome
                or delegated.resolution_status is not self.resolution_status
                or delegated.adjudication_outcome is not self.adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("credential receipt differs from revocation receipt")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudicator-credential-revocation-"
                    "terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong revocation outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("verified witness-conflict revocation receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner:
    """Require active as-of status before executing the exact PR #32 runner."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        adjudication_evaluated_at: str,
        adjudication_completed_at: str,
        credential_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("revocation-gated adjudication requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match revocation-bound corpus exactly")
        if corpus.predecessor_corpus_ref != credential_corpus.reference():
            raise ValueError("revocation corpus must bind exact 1.10.0 predecessor")
        if corpus.revocation_policy_ref != revocation_policy.reference():
            raise ValueError("revocation policy reference differs from corpus")
        if corpus.revocation_ledger_ref != revocation_ledger.reference():
            raise ValueError("revocation ledger reference differs from corpus")
        witness_time = _parse_timestamp(witness_evaluated_at, "witness_evaluated_at")
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        credential_time = _parse_timestamp(
            credential_evaluated_at,
            "credential_evaluated_at",
        )
        adjudication_time = _parse_timestamp(
            adjudication_evaluated_at,
            "adjudication_evaluated_at",
        )
        adjudication_completed = _parse_timestamp(
            adjudication_completed_at,
            "adjudication_completed_at",
        )
        credential_completed = _parse_timestamp(
            credential_completed_at,
            "credential_completed_at",
        )
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            witness_time <= revocation_time <= credential_time <= adjudication_time
            <= adjudication_completed <= credential_completed <= completed
        ):
            raise ValueError(
                "witness, revocation, credential, adjudication, and completion "
                "chronology differs"
            )

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored witness-conflict credential revocation decision differs"
            )
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictWitnessRevocationFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
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
            raise ArtifactIntegrityError(
                "stored witness-conflict credential revocation final differs"
            )
        if self._store.get(
            revocation_evidence.corpus_ref.artifact_id,
            expected_hash=revocation_evidence.corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("revocation-bound corpus differs")
        predecessor = self._store.get(
            credential_corpus.reference().artifact_id,
            expected_hash=credential_corpus.reference().artifact_hash,
        )
        if predecessor.payload != credential_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.10.0 credential corpus differs")
        if self._store.get(
            revocation_evidence.revocation_policy_ref.artifact_id,
            expected_hash=revocation_evidence.revocation_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored revocation policy differs")
        if self._store.get(
            revocation_evidence.revocation_ledger_ref.artifact_id,
            expected_hash=revocation_evidence.revocation_ledger_ref.artifact_hash,
        ).payload != ledger.canonical_payload:
            raise ArtifactIntegrityError("stored revocation ledger differs")
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
            (
                f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-decision"
            ),
            decision,
        )
        if self._store.get(
            final.revocation_decision_ref.artifact_id,
            expected_hash=final.revocation_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError(
                "witness-conflict revocation decision differs during verification"
            )
        if final.credential_final_ref is not None:
            self._store.get(
                final.credential_final_ref.artifact_id,
                expected_hash=final.credential_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
        credential_corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        adjudication_evaluated_at: str,
        adjudication_completed_at: str,
        credential_completed_at: str,
        completed_at: str,
    ) -> VerifiedCheckpointConflictWitnessRevocationReceipt:
        """Return terminal revocation abstention or the exact PR #32 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                credential_corpus=credential_corpus,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                experiment_run_id=experiment_run_id,
                witness_evaluated_at=witness_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                adjudication_evaluated_at=adjudication_evaluated_at,
                adjudication_completed_at=adjudication_completed_at,
                credential_completed_at=credential_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointConflictWitnessRevocationExperimentError(
                CheckpointConflictWitnessRevocationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            revocation_evidence = (
                load_checkpoint_conflict_witness_adjudicator_credential_revocation_evidence(
                    self._store,
                    corpus=corpus,
                    policy=revocation_policy,
                    ledger=revocation_ledger,
                )
            )
            credential_evidence = (
                load_checkpoint_conflict_witness_adjudicator_credential_evidence(
                    self._store,
                    corpus=credential_corpus,
                    adjudicator_registry=adjudicator_registry,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    adjudication=adjudication,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictWitnessRevocationExperimentError(
                CheckpointConflictWitnessRevocationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = (
                validate_checkpoint_conflict_witness_adjudicator_credential_revocation_ledger(
                    plan=plan,
                    corpus=corpus,
                    adjudicator_registry=adjudicator_registry,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    revocation_policy=revocation_policy,
                    ledger=revocation_ledger,
                    attestations=credential_evidence.attestations,
                    adjudication=adjudication,
                    events=revocation_events,
                    evaluated_at=revocation_evaluated_at,
                )
            )
        except (AdjudicatorCredentialRevocationError, ValueError) as exc:
            raise CheckpointConflictWitnessRevocationExperimentError(
                CheckpointConflictWitnessRevocationRunnerStage.REVOCATION_VALIDATION,
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
            raise CheckpointConflictWitnessRevocationExperimentError(
                CheckpointConflictWitnessRevocationRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCheckpointConflictWitnessCredentialReceipt | None = None
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
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    witness_attestations=witness_attestations,
                    head_checkpoint=head_checkpoint,
                    adjudicator_registry=adjudicator_registry,
                    adjudication_policy=adjudication_policy,
                    adjudication=adjudication,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    credentials=credential_evidence.attestations,
                    witness_receipt=witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    witness_evaluated_at=witness_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    adjudication_completed_at=adjudication_completed_at,
                    completed_at=credential_completed_at,
                )
            except CheckpointConflictWitnessCredentialExperimentError as exc:
                raise CheckpointConflictWitnessRevocationExperimentError(
                    CheckpointConflictWitnessRevocationRunnerStage.CREDENTIAL_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        credential_outcome: CredentialDecisionOutcome | None = None
        checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        resolution_status: WitnessConflictResolutionStatus | None = None
        adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        credential_final_ref: StoredArtifactRef | None = None
        if delegated is not None:
            credential_outcome = delegated.credential_outcome
            checkpoint_witness_outcome = delegated.checkpoint_witness_outcome
            resolution_status = delegated.resolution_status
            adjudication_outcome = delegated.adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            credential_final_ref = delegated.final_manifest_ref

        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-abstention"
            if decision.outcome is CredentialDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-revocation-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudicator-credential-revocation-"
                    "terminal-abstention"
                )
            )
        )
        final = CheckpointConflictWitnessRevocationFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessRevocationRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            credential_outcome=credential_outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            adjudication_outcome=adjudication_outcome,
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
            verified_checks=CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS,
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
            raise CheckpointConflictWitnessRevocationExperimentError(
                CheckpointConflictWitnessRevocationRunnerStage.FINAL_PERSISTENCE,
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
                policy=revocation_policy,
                ledger=revocation_ledger,
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
            raise CheckpointConflictWitnessRevocationExperimentError(
                CheckpointConflictWitnessRevocationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictWitnessRevocationReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessRevocationRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            credential_outcome=credential_outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            adjudication_outcome=adjudication_outcome,
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
            verified_checks=CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CHECKPOINT_CONFLICT_WITNESS_REVOCATION_VERIFIED_CHECKS",
    "CheckpointConflictWitnessRevocationExperimentError",
    "CheckpointConflictWitnessRevocationFinalManifest",
    "CheckpointConflictWitnessRevocationRunnerStage",
    "CheckpointConflictWitnessRevocationRunnerStatus",
    "RevocationGatedCheckpointConflictWitnessAdjudicationExperimentRunner",
    "VerifiedCheckpointConflictWitnessRevocationReceipt",
]
