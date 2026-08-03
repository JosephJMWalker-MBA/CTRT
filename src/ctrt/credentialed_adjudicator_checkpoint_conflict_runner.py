"""Gate adjudicator-checkpoint witness conflict resolution on issuer credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicated_adjudicator_checkpoint_witness_runner import (
    AdjudicatedAdjudicatorCheckpointWitnessExperimentError,
    AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner,
    VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt,
)
from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    AdjudicatorCheckpointConflictCredentialError,
    CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    StoredAdjudicatorCheckpointConflictCredentialEvidence,
    load_adjudicator_checkpoint_conflict_credential_evidence,
    validate_adjudicator_checkpoint_conflict_credentials,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialDecisionReport,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
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
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class CheckpointConflictCredentialRunnerStage(StrEnum):
    """Boundary at which checkpoint-conflict credential execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    CREDENTIAL_DECISION_PERSISTENCE = "credential-decision-persistence"
    ADJUDICATED_CONFLICT_EXECUTION = "adjudicated-conflict-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictCredentialRunnerStatus(StrEnum):
    """A receipt exists only after final evidence re-verifies."""

    VERIFIED = "verified"


class CheckpointConflictCredentialExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointConflictCredentialRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS = (
    "exact-checkpoint-conflict-adjudicator-identity-revision-bound",
    "exact-checkpoint-conflict-adjudicator-role-attested",
    "issuer-and-credential-policy-reverified",
    "credential-validity-evaluated-at-declared-time",
    "credential-abstention-precedes-conflict-adjudication-execution",
    "preserved-conflict-and-adjudication-record-left-immutable",
    "credential-and-downstream-outcomes-finalized-separately",
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
class CheckpointConflictCredentialFinalManifest:
    """Final marker for credential abstention or delegated conflict outcome."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictCredentialRunnerStatus
    credential_outcome: CredentialDecisionOutcome
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
    credential_corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudicated_conflict_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictCredentialRunnerStatus.VERIFIED:
            raise ValueError("checkpoint conflict credential status must be verified")
        if not self.credential_attestation_refs:
            raise ValueError("checkpoint conflict credential final requires attestations")
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(
                item is not None
                for item in (
                    self.adjudicator_checkpoint_witness_outcome,
                    self.conflict_adjudication_outcome,
                    self.adjudicator_revocation_outcome,
                    self.adjudicator_credential_outcome,
                    self.reviewer_checkpoint_witness_outcome,
                    self.reviewer_witness_adjudication_outcome,
                    self.reviewer_revocation_outcome,
                    self.adjudicated_conflict_final_ref,
                )
            ):
                raise ValueError(
                    "credential abstention may not claim downstream outcomes"
                )
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("credential abstention must be terminal abstention")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-abstention"
            )
        else:
            if (
                self.adjudicator_checkpoint_witness_outcome is None
                or self.conflict_adjudication_outcome is None
                or self.adjudicated_conflict_final_ref is None
            ):
                raise ValueError(
                    "credential execution requires delegated conflict evidence"
                )
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-checkpoint-conflict-adjudicator-credential-"
                    "terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from credential terminal outcome")
        if self.verified_checks != CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS:
            raise ValueError("checkpoint conflict credential final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictCredentialReceipt:
    """Proof of credential eligibility and optional conflict adjudication."""

    experiment_run_id: str
    status: CheckpointConflictCredentialRunnerStatus
    credential_outcome: CredentialDecisionOutcome
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
    credential_corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudicated_conflict_receipt: (
        VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictCredentialRunnerStatus.VERIFIED:
            raise ValueError("verified checkpoint conflict credential status required")
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.adjudicated_conflict_receipt is not None:
                raise ValueError(
                    "credential abstention may not contain delegated receipt"
                )
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-abstention"
            )
        else:
            if self.adjudicated_conflict_receipt is None:
                raise ValueError(
                    "credential execution requires delegated conflict receipt"
                )
            receipt = self.adjudicated_conflict_receipt
            if (
                receipt.adjudicator_checkpoint_witness_outcome
                is not self.adjudicator_checkpoint_witness_outcome
                or receipt.conflict_adjudication_outcome
                is not self.conflict_adjudication_outcome
                or receipt.adjudicator_revocation_outcome
                is not self.adjudicator_revocation_outcome
                or receipt.adjudicator_credential_outcome
                is not self.adjudicator_credential_outcome
                or receipt.reviewer_checkpoint_witness_outcome
                is not self.reviewer_checkpoint_witness_outcome
                or receipt.reviewer_witness_adjudication_outcome
                is not self.reviewer_witness_adjudication_outcome
                or receipt.reviewer_revocation_outcome
                is not self.reviewer_revocation_outcome
                or receipt.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("delegated receipt differs from credential receipt")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-checkpoint-conflict-adjudicator-credential-"
                    "terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong credential outcome")
        if self.verified_checks != CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS:
            raise ValueError("verified checkpoint conflict credential receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CredentialedAdjudicatorCheckpointConflictExperimentRunner:
    """Require eligible credentials before checkpoint-conflict adjudication."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        credential_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            credential_evaluated_at,
            "checkpoint_conflict_credential_evaluated_at",
        )
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint conflict credential gate requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match credential-bound conflict corpus")
        if corpus.corpus.adjudicator_registry_ref != adjudicator_registry.reference():
            raise ValueError("checkpoint conflict adjudicator registry must match corpus")
        if corpus.issuer_registry_ref != issuer_registry.reference():
            raise ValueError("checkpoint conflict credential issuer must match corpus")
        if corpus.credential_policy_ref != credential_policy.reference():
            raise ValueError("checkpoint conflict credential policy must match corpus")
        if corpus.corpus.adjudication_ref != adjudication.reference():
            raise ValueError("checkpoint conflict adjudication must match corpus")
        if tuple(item.content_id for item in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCredentialDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint conflict credential decision differs"
            )
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictCredentialFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
        evidence: StoredAdjudicatorCheckpointConflictCredentialEvidence,
        decision: AdjudicatorCredentialDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint conflict credential final differs"
            )
        if self._store.get(
            evidence.corpus_ref.artifact_id,
            expected_hash=evidence.corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "credential-bound checkpoint conflict corpus differs"
            )
        for reference in (
            evidence.adjudicator_registry_ref,
            evidence.issuer_registry_ref,
            evidence.credential_policy_ref,
            evidence.adjudication_ref,
            *evidence.attestation_refs,
        ):
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_decision = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-decision"
            ),
            decision,
        )
        if self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError(
                "checkpoint conflict credential decision differs during verification"
            )
        if final.adjudicated_conflict_final_ref is not None:
            self._store.get(
                final.adjudicated_conflict_final_ref.artifact_id,
                expected_hash=final.adjudicated_conflict_final_ref.artifact_hash,
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
        adjudicator_revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        adjudicator_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        adjudicator_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        adjudicator_checkpoint_log: (
            AdjudicatorCredentialRevocationCheckpointLogSnapshot
        ),
        adjudicator_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
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
        corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
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
    ) -> VerifiedCheckpointConflictCredentialReceipt:
        """Return verified credential abstention or delegated conflict outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=(
                    adjudicator_checkpoint_conflict_adjudicator_registry
                ),
                issuer_registry=checkpoint_conflict_adjudicator_issuer_registry,
                credential_policy=(
                    checkpoint_conflict_adjudicator_credential_policy
                ),
                adjudication=adjudicator_checkpoint_conflict_adjudication,
                windows=windows,
                experiment_run_id=experiment_run_id,
                credential_evaluated_at=(
                    checkpoint_conflict_credential_evaluated_at
                ),
            )
        except ValueError as exc:
            raise CheckpointConflictCredentialExperimentError(
                CheckpointConflictCredentialRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_adjudicator_checkpoint_conflict_credential_evidence(
                self._store,
                corpus=corpus,
                adjudicator_registry=(
                    adjudicator_checkpoint_conflict_adjudicator_registry
                ),
                issuer_registry=checkpoint_conflict_adjudicator_issuer_registry,
                credential_policy=(
                    checkpoint_conflict_adjudicator_credential_policy
                ),
                adjudication=adjudicator_checkpoint_conflict_adjudication,
            )
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise CheckpointConflictCredentialExperimentError(
                CheckpointConflictCredentialRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_adjudicator_checkpoint_conflict_credentials(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=(
                    adjudicator_checkpoint_conflict_adjudicator_registry
                ),
                issuer_registry=checkpoint_conflict_adjudicator_issuer_registry,
                credential_policy=(
                    checkpoint_conflict_adjudicator_credential_policy
                ),
                attestations=checkpoint_conflict_adjudicator_credentials,
                adjudication=adjudicator_checkpoint_conflict_adjudication,
                evaluated_at=checkpoint_conflict_credential_evaluated_at,
            )
        except (AdjudicatorCheckpointConflictCredentialError, ValueError) as exc:
            raise CheckpointConflictCredentialExperimentError(
                CheckpointConflictCredentialRunnerStage.CREDENTIAL_VALIDATION,
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
            raise CheckpointConflictCredentialExperimentError(
                CheckpointConflictCredentialRunnerStage.CREDENTIAL_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt | None = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            try:
                delegated = self._runner.run(
                    plan=plan,
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
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    adjudicator_checkpoint_verified_at=(
                        adjudicator_checkpoint_verified_at
                    ),
                    adjudicator_witness_evaluated_at=(
                        adjudicator_witness_evaluated_at
                    ),
                    adjudicator_checkpoint_conflict_adjudication_evaluated_at=(
                        adjudicator_checkpoint_conflict_adjudication_evaluated_at
                    ),
                    adjudicator_revocation_evaluated_at=(
                        adjudicator_revocation_evaluated_at
                    ),
                    adjudicator_credential_evaluated_at=(
                        adjudicator_credential_evaluated_at
                    ),
                    checkpoint_verified_at=checkpoint_verified_at,
                    witness_evaluated_at=witness_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except AdjudicatedAdjudicatorCheckpointWitnessExperimentError as exc:
                raise CheckpointConflictCredentialExperimentError(
                    CheckpointConflictCredentialRunnerStage.ADJUDICATED_CONFLICT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = checkpoint_conflict_credential_evaluated_at
        delegated_final_ref: StoredArtifactRef | None = None
        adjudicator_checkpoint_witness_outcome: (
            CheckpointWitnessDecisionOutcome | None
        ) = None
        conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        adjudicator_revocation_outcome: CredentialDecisionOutcome | None = None
        adjudicator_credential_outcome: CredentialDecisionOutcome | None = None
        reviewer_checkpoint_witness_outcome: (
            CheckpointWitnessDecisionOutcome | None
        ) = None
        reviewer_witness_adjudication_outcome: (
            WitnessConflictAdjudicationOutcome | None
        ) = None
        reviewer_revocation_outcome: CredentialDecisionOutcome | None = None
        if delegated is not None:
            terminal_outcome = delegated.terminal_outcome
            completed_at = delegated.completed_at
            delegated_final_ref = delegated.final_manifest_ref
            adjudicator_checkpoint_witness_outcome = (
                delegated.adjudicator_checkpoint_witness_outcome
            )
            conflict_adjudication_outcome = delegated.conflict_adjudication_outcome
            adjudicator_revocation_outcome = delegated.adjudicator_revocation_outcome
            adjudicator_credential_outcome = delegated.adjudicator_credential_outcome
            reviewer_checkpoint_witness_outcome = (
                delegated.reviewer_checkpoint_witness_outcome
            )
            reviewer_witness_adjudication_outcome = (
                delegated.reviewer_witness_adjudication_outcome
            )
            reviewer_revocation_outcome = delegated.reviewer_revocation_outcome

        final_id = (
            f"{experiment_run_id}:"
            "adjudicator-checkpoint-conflict-adjudicator-credential-abstention"
            if decision.outcome is CredentialDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:"
                "adjudicator-checkpoint-conflict-adjudicator-credential-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "adjudicator-checkpoint-conflict-adjudicator-credential-"
                    "terminal-abstention"
                )
            )
        )
        final = CheckpointConflictCredentialFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictCredentialRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            adjudicator_checkpoint_witness_outcome=(
                adjudicator_checkpoint_witness_outcome
            ),
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=(
                reviewer_checkpoint_witness_outcome
            ),
            reviewer_witness_adjudication_outcome=(
                reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=decision_ref,
            adjudicated_conflict_final_ref=delegated_final_ref,
            verified_checks=CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS,
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
            raise CheckpointConflictCredentialExperimentError(
                CheckpointConflictCredentialRunnerStage.FINAL_PERSISTENCE,
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
                evidence=evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictCredentialExperimentError(
                CheckpointConflictCredentialRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictCredentialReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictCredentialRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            adjudicator_checkpoint_witness_outcome=(
                adjudicator_checkpoint_witness_outcome
            ),
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=(
                reviewer_checkpoint_witness_outcome
            ),
            reviewer_witness_adjudication_outcome=(
                reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=decision_ref,
            adjudicated_conflict_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=CHECKPOINT_CONFLICT_CREDENTIAL_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
