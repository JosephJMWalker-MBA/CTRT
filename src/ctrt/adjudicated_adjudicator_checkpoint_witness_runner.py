"""Gate adjudicator checkpoint execution on authorized witness adjudication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_checkpoint_witness_attestation import (
    validate_adjudicator_checkpoint_witness_attestations,
)
from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
    AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport,
    AdjudicatorCheckpointWitnessConflictAdjudicationError,
    StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence,
    load_adjudicator_checkpoint_witness_conflict_adjudication_evidence,
    validate_adjudicator_checkpoint_witness_conflict_adjudication,
)
from ctrt.adjudicator_checkpoint_witness_runner import (
    AdjudicatorCheckpointWitnessExperimentError,
    AdjudicatorCheckpointWitnessExperimentRunner,
    VerifiedAdjudicatorCheckpointWitnessReceipt,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    load_adjudicator_credential_revocation_checkpoint_evidence,
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
from ctrt.checkpoint_gated_adjudicator_revocation_runner import (
    AdjudicatorCheckpointGatedExperimentError,
    CheckpointGatedAdjudicatorRevocationExperimentRunner,
    VerifiedAdjudicatorCheckpointGatedReceipt,
)
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
    WitnessConflictAdjudicationError,
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class AdjudicatedAdjudicatorCheckpointWitnessRunnerStage(StrEnum):
    """Boundary at which adjudicator-checkpoint witness adjudication failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    WITNESS_EXECUTION = "witness-execution"
    ADJUDICATION_VALIDATION = "adjudication-validation"
    ADJUDICATION_DECISION_PERSISTENCE = "adjudication-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus(StrEnum):
    """A receipt exists only after every final artifact is reverified."""

    VERIFIED = "verified"


class AdjudicatedAdjudicatorCheckpointWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatedAdjudicatorCheckpointWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS = (
    "original-adjudicator-checkpoint-witness-outcome-preserved",
    "exact-conflict-adjudicator-registry-and-policy-bound",
    "conflicting-head-evidence-reverified",
    "authorized-resolution-or-fail-closed-abstention",
    "resolved-head-restricted-to-verified-checkpoint-head",
    "preserved-dissent-reverified",
    "witness-count-never-used-as-authority",
    "adjudication-and-downstream-outcomes-finalized-separately",
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
class AdjudicatedAdjudicatorCheckpointWitnessFinalManifest:
    """Final marker for conflict abstention or authorized downstream execution."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    adjudication_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    witness_final_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    checkpoint_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        for value in (
            self.final_id,
            self.experiment_run_id,
            self.experiment_id,
            self.experiment_version,
        ):
            if not value.strip():
                raise ValueError("adjudicated checkpoint witness identity is empty")
        if self.status is not AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus.VERIFIED:
            raise ValueError("adjudicated checkpoint witness status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("adjudicated checkpoint witness requires unique contents")
        if not self.witness_attestation_refs:
            raise ValueError("adjudicated checkpoint witness requires attestations")
        if self.conflict_adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN:
            if self.checkpoint_final_ref is not None:
                raise ValueError("adjudication abstention may not claim checkpoint execution")
            if self.adjudicator_revocation_outcome is not None:
                raise ValueError("adjudication abstention may not claim revocation outcome")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("adjudication abstention must be terminal abstention")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-abstention"
            )
        else:
            if self.checkpoint_final_ref is None or self.adjudicator_revocation_outcome is None:
                raise ValueError("adjudication execution requires checkpoint outcome")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-checkpoint-witness-conflict-adjudication-"
                    "terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from adjudication terminal outcome")
        if (
            self.verified_checks
            != ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS
        ):
            raise ValueError("adjudicated checkpoint witness final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt:
    """Proof of preserved witness outcome and authorized adjudication."""

    experiment_run_id: str
    status: AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    adjudication_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    witness_receipt: VerifiedAdjudicatorCheckpointWitnessReceipt
    adjudication_decision_ref: StoredArtifactRef
    checkpoint_receipt: VerifiedAdjudicatorCheckpointGatedReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus.VERIFIED:
            raise ValueError("verified adjudicated checkpoint witness status is invalid")
        if (
            self.witness_receipt.adjudicator_checkpoint_witness_outcome
            is not self.adjudicator_checkpoint_witness_outcome
        ):
            raise ValueError("outer witness outcome differs from preserved receipt")
        if self.conflict_adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None:
                raise ValueError("adjudication abstention may not contain checkpoint receipt")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-abstention"
            )
        else:
            if self.checkpoint_receipt is None:
                raise ValueError("adjudication execution requires checkpoint receipt")
            if self.checkpoint_receipt.terminal_outcome is not self.terminal_outcome:
                raise ValueError("checkpoint receipt differs from terminal outcome")
            expected_id = (
                f"{self.experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-checkpoint-witness-conflict-adjudication-"
                    "terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest must identify adjudication terminal outcome")
        if (
            self.verified_checks
            != ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS
        ):
            raise ValueError("verified adjudicated checkpoint witness receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner:
    """Preserve witness abstention, then apply authorized conflict adjudication."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._witness_runner = AdjudicatorCheckpointWitnessExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )
        self._checkpoint_runner = CheckpointGatedAdjudicatorRevocationExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudication_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(adjudication_evaluated_at, "adjudication_evaluated_at")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("adjudicated checkpoint witness requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match adjudication-bound corpus exactly")
        if corpus.corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry reference must match corpus")
        if corpus.corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy reference must match corpus")
        if corpus.adjudicator_registry_ref != adjudicator_registry.reference():
            raise ValueError("adjudicator registry reference must match corpus")
        if corpus.adjudication_policy_ref != adjudication_policy.reference():
            raise ValueError("adjudication policy reference must match corpus")
        if corpus.adjudication_ref != adjudication.reference():
            raise ValueError("adjudication record reference must match corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError("execution windows must match frozen content order")

    def _persist_adjudication_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored conflict adjudication decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: AdjudicatedAdjudicatorCheckpointWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
        evidence: StoredAdjudicatorCheckpointWitnessConflictAdjudicationEvidence,
        decision: AdjudicatorCheckpointWitnessConflictAdjudicationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored adjudicated witness final differs")
        if self._store.get(
            final.adjudication_corpus_ref.artifact_id,
            expected_hash=final.adjudication_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("adjudication corpus differs during verification")
        for reference in (
            *evidence.witness_evidence.attestation_refs,
            evidence.adjudicator_registry_ref,
            evidence.adjudication_policy_ref,
            evidence.adjudication_ref,
            final.witness_final_ref,
        ):
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        decision_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-decision"
            ),
            decision,
        )
        if self._store.get(
            final.adjudication_decision_ref.artifact_id,
            expected_hash=final.adjudication_decision_ref.artifact_hash,
        ).payload != decision_artifact.payload:
            raise ArtifactIntegrityError("adjudication decision differs during verification")
        if final.checkpoint_final_ref is not None:
            self._store.get(
                final.checkpoint_final_ref.artifact_id,
                expected_hash=final.checkpoint_final_ref.artifact_hash,
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
        adjudicator_checkpoint_policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
        adjudicator_checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
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
        corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
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
    ) -> VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt:
        """Return verified adjudication abstention or downstream outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_registry=adjudicator_checkpoint_witness_registry,
                witness_policy=adjudicator_checkpoint_witness_policy,
                adjudicator_registry=(
                    adjudicator_checkpoint_conflict_adjudicator_registry
                ),
                adjudication_policy=(
                    adjudicator_checkpoint_conflict_adjudication_policy
                ),
                adjudication=adjudicator_checkpoint_conflict_adjudication,
                windows=windows,
                experiment_run_id=experiment_run_id,
                adjudication_evaluated_at=(
                    adjudicator_checkpoint_conflict_adjudication_evaluated_at
                ),
            )
        except ValueError as exc:
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = (
                load_adjudicator_checkpoint_witness_conflict_adjudication_evidence(
                    self._store,
                    corpus=corpus,
                    witness_registry=adjudicator_checkpoint_witness_registry,
                    witness_policy=adjudicator_checkpoint_witness_policy,
                    adjudicator_registry=(
                        adjudicator_checkpoint_conflict_adjudicator_registry
                    ),
                    adjudication_policy=(
                        adjudicator_checkpoint_conflict_adjudication_policy
                    ),
                    adjudication=adjudicator_checkpoint_conflict_adjudication,
                )
            )
            checkpoint_evidence = (
                load_adjudicator_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus.corpus.corpus,
                    policy=adjudicator_checkpoint_policy,
                    log=adjudicator_checkpoint_log,
                )
            )
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            witness_receipt = self._witness_runner.run(
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
                corpus=corpus.corpus,
                environment=environment,
                windows=windows,
                experiment_run_id=experiment_run_id,
                adjudicator_checkpoint_verified_at=adjudicator_checkpoint_verified_at,
                adjudicator_witness_evaluated_at=adjudicator_witness_evaluated_at,
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
        except AdjudicatorCheckpointWitnessExperimentError as exc:
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.WITNESS_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        witness_decision = validate_adjudicator_checkpoint_witness_attestations(
            plan=plan,
            corpus=corpus.corpus,
            registry=adjudicator_checkpoint_witness_registry,
            policy=adjudicator_checkpoint_witness_policy,
            head_checkpoint=checkpoint_evidence.checkpoints[-1],
            attestations=evidence.witness_evidence.attestations,
            evaluated_at=adjudicator_witness_evaluated_at,
        )
        try:
            adjudication_decision = (
                validate_adjudicator_checkpoint_witness_conflict_adjudication(
                    plan=plan,
                    corpus=corpus,
                    witness_registry=adjudicator_checkpoint_witness_registry,
                    witness_policy=adjudicator_checkpoint_witness_policy,
                    adjudicator_registry=(
                        adjudicator_checkpoint_conflict_adjudicator_registry
                    ),
                    adjudication_policy=(
                        adjudicator_checkpoint_conflict_adjudication_policy
                    ),
                    witness_decision=witness_decision,
                    adjudication=adjudicator_checkpoint_conflict_adjudication,
                    evaluated_at=(
                        adjudicator_checkpoint_conflict_adjudication_evaluated_at
                    ),
                )
            )
        except (
            AdjudicatorCheckpointWitnessConflictAdjudicationError,
            WitnessConflictAdjudicationError,
            ValueError,
        ) as exc:
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.ADJUDICATION_VALIDATION,
                str(exc),
            ) from exc

        try:
            adjudication_decision_ref = self._persist_adjudication_decision(
                experiment_run_id=experiment_run_id,
                decision=adjudication_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.ADJUDICATION_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        checkpoint_receipt: VerifiedAdjudicatorCheckpointGatedReceipt | None = None
        if adjudication_decision.outcome is WitnessConflictAdjudicationOutcome.EXECUTE:
            if witness_receipt.checkpoint_receipt is not None:
                checkpoint_receipt = witness_receipt.checkpoint_receipt
            else:
                try:
                    checkpoint_receipt = self._checkpoint_runner.run(
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
                        corpus=corpus.corpus.corpus,
                        environment=environment,
                        windows=windows,
                        experiment_run_id=experiment_run_id,
                        adjudicator_checkpoint_verified_at=(
                            adjudicator_checkpoint_verified_at
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
                except AdjudicatorCheckpointGatedExperimentError as exc:
                    raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                        AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.CHECKPOINT_EXECUTION,
                        str(exc),
                        completed_content_ids=exc.completed_content_ids,
                    ) from exc

        adjudicator_revocation_outcome: CredentialDecisionOutcome | None = None
        adjudicator_credential_outcome: CredentialDecisionOutcome | None = None
        reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        reviewer_revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = adjudicator_checkpoint_conflict_adjudication_evaluated_at
        checkpoint_final_ref: StoredArtifactRef | None = None
        if checkpoint_receipt is not None:
            adjudicator_revocation_outcome = checkpoint_receipt.adjudicator_revocation_outcome
            adjudicator_credential_outcome = checkpoint_receipt.adjudicator_credential_outcome
            reviewer_checkpoint_witness_outcome = checkpoint_receipt.witness_outcome
            reviewer_witness_adjudication_outcome = checkpoint_receipt.adjudication_outcome
            reviewer_revocation_outcome = checkpoint_receipt.reviewer_revocation_outcome
            terminal_outcome = checkpoint_receipt.terminal_outcome
            completed_at = checkpoint_receipt.completed_at
            checkpoint_final_ref = checkpoint_receipt.final_manifest_ref

        final_id = (
            f"{experiment_run_id}:"
            "adjudicator-checkpoint-witness-conflict-adjudication-abstention"
            if adjudication_decision.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:"
                "adjudicator-checkpoint-witness-conflict-adjudication-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "adjudicator-checkpoint-witness-conflict-adjudication-"
                    "terminal-abstention"
                )
            )
        )
        final = AdjudicatedAdjudicatorCheckpointWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus.VERIFIED,
            adjudicator_checkpoint_witness_outcome=witness_decision.outcome,
            conflict_adjudication_outcome=adjudication_decision.outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=reviewer_checkpoint_witness_outcome,
            reviewer_witness_adjudication_outcome=(
                reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            witness_registry_ref=evidence.witness_evidence.witness_registry_ref,
            witness_policy_ref=evidence.witness_evidence.witness_policy_ref,
            witness_attestation_refs=evidence.witness_evidence.attestation_refs,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            adjudication_policy_ref=evidence.adjudication_policy_ref,
            adjudication_ref=evidence.adjudication_ref,
            witness_final_ref=witness_receipt.final_manifest_ref,
            adjudication_decision_ref=adjudication_decision_ref,
            checkpoint_final_ref=checkpoint_final_ref,
            verified_checks=(
                ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS
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
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.FINAL_PERSISTENCE,
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
                decision=adjudication_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedAdjudicatorCheckpointWitnessExperimentError(
                AdjudicatedAdjudicatorCheckpointWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus.VERIFIED,
            adjudicator_checkpoint_witness_outcome=witness_decision.outcome,
            conflict_adjudication_outcome=adjudication_decision.outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=reviewer_checkpoint_witness_outcome,
            reviewer_witness_adjudication_outcome=(
                reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            witness_registry_ref=evidence.witness_evidence.witness_registry_ref,
            witness_policy_ref=evidence.witness_evidence.witness_policy_ref,
            witness_attestation_refs=evidence.witness_evidence.attestation_refs,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            adjudication_policy_ref=evidence.adjudication_policy_ref,
            adjudication_ref=evidence.adjudication_ref,
            witness_receipt=witness_receipt,
            adjudication_decision_ref=adjudication_decision_ref,
            checkpoint_receipt=checkpoint_receipt,
            final_manifest_ref=final_ref,
            verified_checks=(
                ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "ADJUDICATED_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
    "AdjudicatedAdjudicatorCheckpointWitnessExperimentError",
    "AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner",
    "AdjudicatedAdjudicatorCheckpointWitnessFinalManifest",
    "AdjudicatedAdjudicatorCheckpointWitnessRunnerStage",
    "AdjudicatedAdjudicatorCheckpointWitnessRunnerStatus",
    "VerifiedAdjudicatedAdjudicatorCheckpointWitnessReceipt",
]
