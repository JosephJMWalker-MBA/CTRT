"""Gate checkpoint-conflict adjudicator revocation on an immutable checkpoint head."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointLogSnapshot as PriorAdjudicatorCheckpointLog,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot as PriorAdjudicatorCheckpointPolicy,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot as PriorAdjudicatorCheckpoint,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot as PriorAdjudicatorRevocationLedger,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationPolicySnapshot as PriorAdjudicatorRevocationPolicy,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.credential_revocation_checkpoints import (
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.credential_revocation_ledger import (
    CredentialRevocationLedgerSnapshot,
    CredentialRevocationPolicySnapshot,
)
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import ExtractionQualityPolicySnapshot
from ctrt.extraction_review_adjudication import (
    ReviewAdjudicationPolicySnapshot,
    ReviewDecisionOutcome,
    ReviewerRegistrySnapshot,
)
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
    ReviewerCredentialPolicySnapshot,
)
from ctrt.revocation_gated_adjudicator_checkpoint_conflict_runner import (
    CheckpointConflictAdjudicatorRevocationExperimentError,
    RevocationGatedAdjudicatorCheckpointConflictExperimentRunner,
    VerifiedCheckpointConflictAdjudicatorRevocationReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage(StrEnum):
    """Boundary at which checkpoint-gated conflict revocation execution failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus(StrEnum):
    """A receipt exists only after checkpoint and final reverification."""

    VERIFIED = "verified"


class CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS = (
    "exact-checkpoint-conflict-adjudicator-revocation-checkpoint-policy-bound",
    "exact-checkpoint-conflict-adjudicator-revocation-checkpoint-log-bound",
    "contiguous-checkpoint-conflict-adjudicator-revocation-checkpoint-chain-verified",
    "ordered-checkpoint-conflict-adjudicator-revocation-event-prefix-extension-verified",
    "checkpoint-conflict-adjudicator-revocation-checkpoint-head-matches-ledger",
    "checkpoint-conflict-adjudicator-revocation-checkpoint-report-persisted",
    "checkpoint-conflict-adjudicator-revocation-outcome-finalized-separately",
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
class CheckpointConflictAdjudicatorRevocationCheckpointFinalManifest:
    """Final marker for checkpoint-verified conflict adjudicator revocation."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    checkpoint_corpus_ref: StoredArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoint_head_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    revocation_final_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if (
            self.status
            is not CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
        ):
            raise ValueError(
                "checkpoint-conflict revocation checkpoint status must be verified"
            )
        if not self.checkpoint_refs:
            raise ValueError("checkpoint-conflict revocation final requires checkpoints")
        if self.checkpoint_head_ref != self.checkpoint_refs[-1]:
            raise ValueError("checkpoint-conflict revocation checkpoint head must be final")
        expected_id = (
            f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
            "adjudicator-credential-revocation-checkpoint-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-terminal-abstention"
            )
        )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from checkpoint terminal outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint-conflict revocation final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt:
    """Proof of checkpoint verification plus the delegated revocation outcome."""

    experiment_run_id: str
    status: CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    checkpoint_corpus_ref: StoredArtifactRef
    checkpoint_policy_ref: StoredArtifactRef
    checkpoint_log_ref: StoredArtifactRef
    checkpoint_refs: tuple[StoredArtifactRef, ...]
    checkpoint_head_ref: StoredArtifactRef
    checkpoint_verification_ref: StoredArtifactRef
    revocation_receipt: VerifiedCheckpointConflictAdjudicatorRevocationReceipt
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if (
            self.status
            is not CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
        ):
            raise ValueError(
                "verified checkpoint-conflict revocation checkpoint required"
            )
        delegated = self.revocation_receipt
        if (
            delegated.revocation_outcome is not self.revocation_outcome
            or delegated.credential_outcome is not self.credential_outcome
            or delegated.adjudicator_checkpoint_witness_outcome
            is not self.adjudicator_checkpoint_witness_outcome
            or delegated.conflict_adjudication_outcome
            is not self.conflict_adjudication_outcome
            or delegated.adjudicator_revocation_outcome
            is not self.adjudicator_revocation_outcome
            or delegated.adjudicator_credential_outcome
            is not self.adjudicator_credential_outcome
            or delegated.reviewer_checkpoint_witness_outcome
            is not self.reviewer_checkpoint_witness_outcome
            or delegated.reviewer_witness_adjudication_outcome
            is not self.reviewer_witness_adjudication_outcome
            or delegated.reviewer_revocation_outcome
            is not self.reviewer_revocation_outcome
            or delegated.terminal_outcome is not self.terminal_outcome
        ):
            raise ValueError("revocation receipt differs from checkpoint receipt")
        expected_id = (
            f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
            "adjudicator-credential-revocation-checkpoint-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-terminal-abstention"
            )
        )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong checkpoint outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
        ):
            raise ValueError(
                "verified checkpoint-conflict revocation receipt lost checks"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class CheckpointGatedAdjudicatorCheckpointConflictExperimentRunner:
    """Verify the exact revocation checkpoint before the PR #28 runner."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = RevocationGatedAdjudicatorCheckpointConflictExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            checkpoint_verified_at,
            "checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at",
        )
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-gated conflict revocation requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match checkpoint-bound conflict corpus")
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("checkpoint policy reference must match corpus")
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("checkpoint log reference must match corpus")
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("checkpoint head reference must match corpus")
        if tuple(item.content_id for item in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            report,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint-conflict revocation checkpoint report differs"
            )
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictAdjudicatorRevocationCheckpointFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
        checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint-conflict revocation checkpoint final differs"
            )
        if self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("checkpoint corpus differs during verification")
        if self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        ).payload != checkpoint_policy.canonical_payload:
            raise ArtifactIntegrityError("checkpoint policy differs during verification")
        if self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        ).payload != checkpoint_log.canonical_payload:
            raise ArtifactIntegrityError("checkpoint log differs during verification")
        for reference in evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        expected_report = serialize_artifact(
            (
                f"{final.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != expected_report.payload:
            raise ArtifactIntegrityError(
                "checkpoint-conflict revocation checkpoint report differs"
            )
        self._store.get(
            final.revocation_final_ref.artifact_id,
            expected_hash=final.revocation_final_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        method_registry: ExtractionMethodRegistrySnapshot,
        quality_policy: ExtractionQualityPolicySnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        review_policy: ReviewAdjudicationPolicySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: ReviewerCredentialPolicySnapshot,
        revocation_policy: CredentialRevocationPolicySnapshot,
        ledger: CredentialRevocationLedgerSnapshot,
        checkpoint_policy: CredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: CredentialRevocationCheckpointLogSnapshot,
        checkpoints: tuple[CredentialRevocationLedgerCheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        adjudicator_issuer_registry: CredentialIssuerRegistrySnapshot,
        adjudicator_credential_policy: AdjudicatorCredentialPolicySnapshot,
        adjudicator_credentials: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
        adjudicator_revocation_policy: PriorAdjudicatorRevocationPolicy,
        adjudicator_revocation_ledger: PriorAdjudicatorRevocationLedger,
        adjudicator_checkpoint_policy: PriorAdjudicatorCheckpointPolicy,
        adjudicator_checkpoint_log: PriorAdjudicatorCheckpointLog,
        adjudicator_checkpoints: tuple[PriorAdjudicatorCheckpoint, ...],
        adjudicator_checkpoint_witness_registry: CheckpointWitnessRegistrySnapshot,
        adjudicator_checkpoint_witness_policy: CheckpointWitnessPolicySnapshot,
        adjudicator_checkpoint_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        adjudicator_checkpoint_conflict_adjudicator_registry: (
            WitnessConflictAdjudicatorRegistrySnapshot
        ),
        adjudicator_checkpoint_conflict_adjudication_policy: (
            WitnessConflictAdjudicationPolicySnapshot
        ),
        adjudicator_checkpoint_conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        checkpoint_conflict_adjudicator_issuer_registry: (
            CredentialIssuerRegistrySnapshot
        ),
        checkpoint_conflict_adjudicator_credential_policy: (
            AdjudicatorCredentialPolicySnapshot
        ),
        checkpoint_conflict_adjudicator_credentials: tuple[
            AdjudicatorCredentialAttestationSnapshot, ...
        ],
        checkpoint_conflict_adjudicator_revocation_policy: (
            AdjudicatorCredentialRevocationPolicySnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_ledger: (
            AdjudicatorCredentialRevocationLedgerSnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_events: tuple[
            AdjudicatorCredentialRevocationEventSnapshot, ...
        ],
        checkpoint_conflict_adjudicator_revocation_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_checkpoint_log: (
            AdjudicatorCredentialRevocationCheckpointLogSnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        corpus: CheckpointBoundAdjudicatorCheckpointConflictCredentialRevocationCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at: str,
        checkpoint_conflict_adjudicator_revocation_evaluated_at: str,
        checkpoint_conflict_credential_evaluated_at: str,
        adjudicator_checkpoint_verified_at: str,
        adjudicator_witness_evaluated_at: str,
        adjudicator_checkpoint_conflict_adjudication_evaluated_at: str,
        adjudicator_revocation_evaluated_at: str,
        adjudicator_credential_evaluated_at: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt:
        """Return checkpoint verification plus delegated PR #28 outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                checkpoint_policy=(
                    checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                ),
                checkpoint_log=checkpoint_conflict_adjudicator_revocation_checkpoint_log,
                windows=windows,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=(
                    checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at
                ),
            )
        except ValueError as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = (
                load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus,
                    policy=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                    ),
                    log=checkpoint_conflict_adjudicator_revocation_checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = (
                validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
                    plan=plan,
                    corpus=corpus,
                    policy=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                    ),
                    log=checkpoint_conflict_adjudicator_revocation_checkpoint_log,
                    ledger=checkpoint_conflict_adjudicator_revocation_ledger,
                    checkpoints=evidence.checkpoints,
                    verified_at=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at
                    ),
                )
            )
        except (AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc

        try:
            report_ref = self._persist_report(
                experiment_run_id=experiment_run_id,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        delegated_plan = replace(
            plan,
            corpus_ref=corpus.predecessor_corpus_ref,
            content_ids=corpus.content_ids,
        )
        try:
            delegated = self._runner.run(
                plan=delegated_plan,
                candidate_registry=candidate_registry,
                method_registry=method_registry,
                quality_policy=quality_policy,
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                revocation_policy=revocation_policy,
                ledger=ledger,
                checkpoint_policy=checkpoint_policy,
                checkpoint_log=checkpoint_log,
                checkpoints=checkpoints,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                witness_attestations=witness_attestations,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                adjudication=adjudication,
                adjudicator_issuer_registry=adjudicator_issuer_registry,
                adjudicator_credential_policy=adjudicator_credential_policy,
                adjudicator_credentials=adjudicator_credentials,
                adjudicator_revocation_policy=adjudicator_revocation_policy,
                adjudicator_revocation_ledger=adjudicator_revocation_ledger,
                adjudicator_checkpoint_policy=adjudicator_checkpoint_policy,
                adjudicator_checkpoint_log=adjudicator_checkpoint_log,
                adjudicator_checkpoints=adjudicator_checkpoints,
                adjudicator_checkpoint_witness_registry=(
                    adjudicator_checkpoint_witness_registry
                ),
                adjudicator_checkpoint_witness_policy=(
                    adjudicator_checkpoint_witness_policy
                ),
                adjudicator_checkpoint_witness_attestations=(
                    adjudicator_checkpoint_witness_attestations
                ),
                adjudicator_checkpoint_conflict_adjudicator_registry=(
                    adjudicator_checkpoint_conflict_adjudicator_registry
                ),
                adjudicator_checkpoint_conflict_adjudication_policy=(
                    adjudicator_checkpoint_conflict_adjudication_policy
                ),
                adjudicator_checkpoint_conflict_adjudication=(
                    adjudicator_checkpoint_conflict_adjudication
                ),
                checkpoint_conflict_adjudicator_issuer_registry=(
                    checkpoint_conflict_adjudicator_issuer_registry
                ),
                checkpoint_conflict_adjudicator_credential_policy=(
                    checkpoint_conflict_adjudicator_credential_policy
                ),
                checkpoint_conflict_adjudicator_credentials=(
                    checkpoint_conflict_adjudicator_credentials
                ),
                checkpoint_conflict_adjudicator_revocation_policy=(
                    checkpoint_conflict_adjudicator_revocation_policy
                ),
                checkpoint_conflict_adjudicator_revocation_ledger=(
                    checkpoint_conflict_adjudicator_revocation_ledger
                ),
                checkpoint_conflict_adjudicator_revocation_events=(
                    checkpoint_conflict_adjudicator_revocation_events
                ),
                corpus=corpus.corpus,
                environment=environment,
                windows=windows,
                experiment_run_id=experiment_run_id,
                checkpoint_conflict_adjudicator_revocation_evaluated_at=(
                    checkpoint_conflict_adjudicator_revocation_evaluated_at
                ),
                checkpoint_conflict_credential_evaluated_at=(
                    checkpoint_conflict_credential_evaluated_at
                ),
                adjudicator_checkpoint_verified_at=adjudicator_checkpoint_verified_at,
                adjudicator_witness_evaluated_at=adjudicator_witness_evaluated_at,
                adjudicator_checkpoint_conflict_adjudication_evaluated_at=(
                    adjudicator_checkpoint_conflict_adjudication_evaluated_at
                ),
                adjudicator_revocation_evaluated_at=adjudicator_revocation_evaluated_at,
                adjudicator_credential_evaluated_at=adjudicator_credential_evaluated_at,
                checkpoint_verified_at=checkpoint_verified_at,
                witness_evaluated_at=witness_evaluated_at,
                adjudication_evaluated_at=adjudication_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except CheckpointConflictAdjudicatorRevocationExperimentError as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        final_id = (
            f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
            "adjudicator-credential-revocation-checkpoint-completion"
            if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-terminal-abstention"
            )
        )
        final = CheckpointConflictAdjudicatorRevocationCheckpointFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
            ),
            revocation_outcome=delegated.revocation_outcome,
            credential_outcome=delegated.credential_outcome,
            adjudicator_checkpoint_witness_outcome=(
                delegated.adjudicator_checkpoint_witness_outcome
            ),
            conflict_adjudication_outcome=delegated.conflict_adjudication_outcome,
            adjudicator_revocation_outcome=delegated.adjudicator_revocation_outcome,
            adjudicator_credential_outcome=delegated.adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=(
                delegated.reviewer_checkpoint_witness_outcome
            ),
            reviewer_witness_adjudication_outcome=(
                delegated.reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=delegated.reviewer_revocation_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=(
                checkpoint_conflict_adjudicator_revocation_checkpoint_log.head_checkpoint_ref
            ),
            checkpoint_verification_ref=report_ref,
            revocation_final_ref=delegated.final_manifest_ref,
            verified_checks=(
                CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
            ),
            completed_at=delegated.completed_at,
        )
        try:
            final_ref = self._store.append(serialize_artifact(final.final_id, final))
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                checkpoint_policy=(
                    checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                ),
                checkpoint_log=checkpoint_conflict_adjudicator_revocation_checkpoint_log,
                evidence=evidence,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationCheckpointExperimentError(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if delegated.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt(
            experiment_run_id=experiment_run_id,
            status=(
                CheckpointConflictAdjudicatorRevocationCheckpointRunnerStatus.VERIFIED
            ),
            revocation_outcome=delegated.revocation_outcome,
            credential_outcome=delegated.credential_outcome,
            adjudicator_checkpoint_witness_outcome=(
                delegated.adjudicator_checkpoint_witness_outcome
            ),
            conflict_adjudication_outcome=delegated.conflict_adjudication_outcome,
            adjudicator_revocation_outcome=delegated.adjudicator_revocation_outcome,
            adjudicator_credential_outcome=delegated.adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=(
                delegated.reviewer_checkpoint_witness_outcome
            ),
            reviewer_witness_adjudication_outcome=(
                delegated.reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=delegated.reviewer_revocation_outcome,
            terminal_outcome=delegated.terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            checkpoint_corpus_ref=evidence.corpus_ref,
            checkpoint_policy_ref=evidence.checkpoint_policy_ref,
            checkpoint_log_ref=evidence.checkpoint_log_ref,
            checkpoint_refs=evidence.checkpoint_refs,
            checkpoint_head_ref=(
                checkpoint_conflict_adjudicator_revocation_checkpoint_log.head_checkpoint_ref
            ),
            checkpoint_verification_ref=report_ref,
            revocation_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=(
                CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_CHECKPOINT_VERIFIED_CHECKS
            ),
            completed_at=delegated.completed_at,
        )
