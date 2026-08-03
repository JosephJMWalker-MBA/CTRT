"""Gate adjudicator checkpoint execution on immutable witness observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
    load_adjudicator_checkpoint_witness_evidence,
    validate_adjudicator_checkpoint_witness_attestations,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
    load_adjudicator_credential_revocation_checkpoint_evidence,
    validate_adjudicator_credential_revocation_checkpoints,
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
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class AdjudicatorCheckpointWitnessRunnerStage(StrEnum):
    """Boundary at which adjudicator-checkpoint witness execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatorCheckpointWitnessRunnerStatus(StrEnum):
    """A receipt exists only after witness and final reverification."""

    VERIFIED = "verified"


class AdjudicatorCheckpointWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatorCheckpointWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS = (
    "exact-adjudicator-checkpoint-witness-registry-bound",
    "exact-adjudicator-checkpoint-witness-policy-bound",
    "adjudicator-checkpoint-chain-reverified-before-witness-decision",
    "named-adjudicator-checkpoint-witness-revisions-verified",
    "adjudicator-checkpoint-head-observations-preserved-without-voting",
    "checkpoint-and-witness-reports-persisted",
    "adjudicator-checkpoint-witness-outcome-finalized",
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
class AdjudicatorCheckpointWitnessFinalManifest:
    """Final marker for witness abstention or checkpoint-gated outcome."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatorCheckpointWitnessRunnerStatus
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    witness_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    checkpoint_verification_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
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
                raise ValueError("adjudicator witness identity fields must not be empty")
        if self.status is not AdjudicatorCheckpointWitnessRunnerStatus.VERIFIED:
            raise ValueError("adjudicator witness status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("adjudicator witness execution requires unique contents")
        if not self.witness_attestation_refs:
            raise ValueError("adjudicator witness final requires attestations")
        if (
            self.adjudicator_checkpoint_witness_outcome
            is CheckpointWitnessDecisionOutcome.ABSTAIN
        ):
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("witness abstention must be terminal abstention")
            if self.adjudicator_revocation_outcome is not None:
                raise ValueError("witness abstention may not claim revocation outcome")
            if self.checkpoint_final_ref is not None:
                raise ValueError("witness abstention may not reference execution")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-witness-abstention"
            )
        else:
            if self.adjudicator_revocation_outcome is None:
                raise ValueError("witness execution requires revocation outcome")
            if self.checkpoint_final_ref is None:
                raise ValueError("witness execution requires checkpoint final")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-witness-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-checkpoint-witness-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from witness terminal outcome")
        if self.verified_checks != ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS:
            raise ValueError("adjudicator witness final lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatorCheckpointWitnessReceipt:
    """Proof of witness decision and optional checkpoint-gated execution."""

    experiment_run_id: str
    status: AdjudicatorCheckpointWitnessRunnerStatus
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    witness_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    checkpoint_verification_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    checkpoint_receipt: VerifiedAdjudicatorCheckpointGatedReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not AdjudicatorCheckpointWitnessRunnerStatus.VERIFIED:
            raise ValueError("verified adjudicator witness status must be verified")
        if (
            self.adjudicator_checkpoint_witness_outcome
            is CheckpointWitnessDecisionOutcome.ABSTAIN
        ):
            if self.checkpoint_receipt is not None:
                raise ValueError("witness abstention may not contain checkpoint receipt")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-witness-abstention"
            )
        else:
            if self.checkpoint_receipt is None:
                raise ValueError("witness execution requires checkpoint receipt")
            if self.checkpoint_receipt.adjudicator_revocation_outcome is not (
                self.adjudicator_revocation_outcome
            ):
                raise ValueError("checkpoint receipt differs from revocation outcome")
            if self.checkpoint_receipt.terminal_outcome is not self.terminal_outcome:
                raise ValueError("checkpoint receipt differs from terminal outcome")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-witness-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "adjudicator-checkpoint-witness-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest must identify witness outcome")
        if self.verified_checks != ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS:
            raise ValueError("verified witness receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatorCheckpointWitnessExperimentRunner:
    """Verify checkpoint chain and named witness observations before execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CheckpointGatedAdjudicatorRevocationExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_checkpoint_verified_at: str,
        adjudicator_witness_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            adjudicator_checkpoint_verified_at,
            "adjudicator_checkpoint_verified_at",
        )
        _parse_timestamp(
            adjudicator_witness_evaluated_at,
            "adjudicator_witness_evaluated_at",
        )
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("adjudicator witness execution requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match witness-bound corpus exactly")
        if corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry reference must match corpus")
        if corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy reference must match corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError("execution windows must match frozen content order")

    def _persist_checkpoint_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            report,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        self._store.append(
            serialize_artifact(
                report.artifact_id,
                {
                    "experiment_id": report.experiment_id,
                    "experiment_version": report.experiment_version,
                    "checkpoint_corpus_ref": report.checkpoint_corpus_ref,
                    "checkpoint_policy_ref": report.checkpoint_policy_ref,
                    "checkpoint_log_ref": report.checkpoint_log_ref,
                    "head_checkpoint_ref": report.head_checkpoint_ref,
                },
            )
        )
        return reference

    def _persist_witness_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:adjudicator-checkpoint-witness-decision",
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored witness decision differs")
        self._store.append(
            serialize_artifact(
                decision.artifact_id,
                {
                    "experiment_id": decision.experiment_id,
                    "experiment_version": decision.experiment_version,
                    "witness_corpus_ref": decision.witness_corpus_ref,
                    "witness_registry_ref": decision.witness_registry_ref,
                    "witness_policy_ref": decision.witness_policy_ref,
                    "checkpoint_head_ref": decision.checkpoint_head_ref,
                },
            )
        )
        return reference

    def _verify_final(
        self,
        *,
        final: AdjudicatorCheckpointWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_evidence: StoredAdjudicatorCheckpointWitnessEvidence,
        checkpoint_evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        checkpoint_report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
        witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored adjudicator witness final differs")
        if self._store.get(
            final.witness_corpus_ref.artifact_id,
            expected_hash=final.witness_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("witness corpus differs during verification")
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != witness_registry.canonical_payload:
            raise ArtifactIntegrityError("witness registry differs during verification")
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != witness_policy.canonical_payload:
            raise ArtifactIntegrityError("witness policy differs during verification")
        for reference in witness_evidence.attestation_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        for reference in checkpoint_evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        checkpoint_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            checkpoint_report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != checkpoint_artifact.payload:
            raise ArtifactIntegrityError("checkpoint report differs during verification")
        witness_artifact = serialize_artifact(
            f"{final.experiment_run_id}:adjudicator-checkpoint-witness-decision",
            witness_decision,
        )
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != witness_artifact.payload:
            raise ArtifactIntegrityError("witness decision differs during verification")
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
        corpus: WitnessBoundAdjudicatorCheckpointCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        adjudicator_checkpoint_verified_at: str,
        adjudicator_witness_evaluated_at: str,
        adjudicator_revocation_evaluated_at: str,
        adjudicator_credential_evaluated_at: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedAdjudicatorCheckpointWitnessReceipt:
        """Return verified witness abstention or downstream checkpoint outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_registry=adjudicator_checkpoint_witness_registry,
                witness_policy=adjudicator_checkpoint_witness_policy,
                windows=windows,
                experiment_run_id=experiment_run_id,
                adjudicator_checkpoint_verified_at=adjudicator_checkpoint_verified_at,
                adjudicator_witness_evaluated_at=adjudicator_witness_evaluated_at,
            )
        except ValueError as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            witness_evidence = load_adjudicator_checkpoint_witness_evidence(
                self._store,
                corpus=corpus,
                registry=adjudicator_checkpoint_witness_registry,
                policy=adjudicator_checkpoint_witness_policy,
            )
            checkpoint_evidence = (
                load_adjudicator_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus.corpus,
                    policy=adjudicator_checkpoint_policy,
                    log=adjudicator_checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCheckpointWitnessError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = validate_adjudicator_credential_revocation_checkpoints(
                plan=plan,
                corpus=corpus.corpus,
                policy=adjudicator_checkpoint_policy,
                log=adjudicator_checkpoint_log,
                ledger=adjudicator_revocation_ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=adjudicator_checkpoint_verified_at,
            )
        except (AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc

        try:
            checkpoint_report_ref = self._persist_checkpoint_report(
                experiment_run_id=experiment_run_id,
                report=checkpoint_report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_adjudicator_checkpoint_witness_attestations(
                plan=plan,
                corpus=corpus,
                registry=adjudicator_checkpoint_witness_registry,
                policy=adjudicator_checkpoint_witness_policy,
                head_checkpoint=checkpoint_evidence.checkpoints[-1],
                attestations=witness_evidence.attestations,
                evaluated_at=adjudicator_witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.WITNESS_VALIDATION,
                str(exc),
            ) from exc

        try:
            witness_decision_ref = self._persist_witness_decision(
                experiment_run_id=experiment_run_id,
                decision=witness_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedAdjudicatorCheckpointGatedReceipt | None = None
        adjudicator_revocation_outcome: CredentialDecisionOutcome | None = None
        adjudicator_credential_outcome: CredentialDecisionOutcome | None = None
        reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        reviewer_revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = adjudicator_witness_evaluated_at
        checkpoint_final_ref: StoredArtifactRef | None = None

        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
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
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    adjudicator_checkpoint_verified_at=adjudicator_checkpoint_verified_at,
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
            except AdjudicatorCheckpointGatedExperimentError as exc:
                raise AdjudicatorCheckpointWitnessExperimentError(
                    AdjudicatorCheckpointWitnessRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            checkpoint_final_ref = delegated.final_manifest_ref
            adjudicator_revocation_outcome = delegated.adjudicator_revocation_outcome
            adjudicator_credential_outcome = delegated.adjudicator_credential_outcome
            reviewer_checkpoint_witness_outcome = delegated.witness_outcome
            adjudication_outcome = delegated.adjudication_outcome
            reviewer_revocation_outcome = delegated.reviewer_revocation_outcome
            terminal_outcome = delegated.terminal_outcome
            completed_at = delegated.completed_at

        final_id = (
            f"{experiment_run_id}:adjudicator-checkpoint-witness-abstention"
            if witness_decision.outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:adjudicator-checkpoint-witness-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:"
                    "adjudicator-checkpoint-witness-terminal-abstention"
                )
            )
        )
        final = AdjudicatorCheckpointWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=AdjudicatorCheckpointWitnessRunnerStatus.VERIFIED,
            adjudicator_checkpoint_witness_outcome=witness_decision.outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=reviewer_checkpoint_witness_outcome,
            adjudication_outcome=adjudication_outcome,
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            witness_corpus_ref=witness_evidence.corpus_ref,
            witness_registry_ref=witness_evidence.witness_registry_ref,
            witness_policy_ref=witness_evidence.witness_policy_ref,
            witness_attestation_refs=witness_evidence.attestation_refs,
            checkpoint_verification_ref=checkpoint_report_ref,
            witness_decision_ref=witness_decision_ref,
            checkpoint_final_ref=checkpoint_final_ref,
            verified_checks=ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
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
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.FINAL_PERSISTENCE,
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
                witness_registry=adjudicator_checkpoint_witness_registry,
                witness_policy=adjudicator_checkpoint_witness_policy,
                witness_evidence=witness_evidence,
                checkpoint_evidence=checkpoint_evidence,
                checkpoint_report=checkpoint_report,
                witness_decision=witness_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatorCheckpointWitnessExperimentError(
                AdjudicatorCheckpointWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatorCheckpointWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatorCheckpointWitnessRunnerStatus.VERIFIED,
            adjudicator_checkpoint_witness_outcome=witness_decision.outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=reviewer_checkpoint_witness_outcome,
            adjudication_outcome=adjudication_outcome,
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            witness_corpus_ref=witness_evidence.corpus_ref,
            witness_registry_ref=witness_evidence.witness_registry_ref,
            witness_policy_ref=witness_evidence.witness_policy_ref,
            witness_attestation_refs=witness_evidence.attestation_refs,
            checkpoint_verification_ref=checkpoint_report_ref,
            witness_decision_ref=witness_decision_ref,
            checkpoint_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
