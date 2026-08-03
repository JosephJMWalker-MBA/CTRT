"""Gate checkpoint execution on immutable named-witness observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.checkpoint_gated_revocation_runner import (
    CheckpointGatedExperimentError,
    CheckpointGatedRevocationExperimentRunner,
    VerifiedCheckpointGatedReceipt,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessDecisionReport,
    CheckpointWitnessError,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
    StoredCheckpointWitnessEvidence,
    WitnessBoundCheckpointCorpusSnapshot,
    load_checkpoint_witness_evidence,
    validate_checkpoint_witness_attestations,
)
from ctrt.credential_revocation_checkpoints import (
    CredentialRevocationCheckpointError,
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationCheckpointVerificationReport,
    CredentialRevocationLedgerCheckpointSnapshot,
    StoredCredentialRevocationCheckpointEvidence,
    load_credential_revocation_checkpoint_evidence,
    validate_credential_revocation_checkpoints,
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
from ctrt.workbench import AnalyzerRegistry


class WitnessGatedRunnerStage(StrEnum):
    """Boundary at which witness-gated execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class WitnessGatedRunnerStatus(StrEnum):
    """A receipt exists only after witness and final reverification."""

    VERIFIED = "verified"


class WitnessGatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: WitnessGatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


WITNESS_GATED_VERIFIED_CHECKS = (
    "exact-witness-registry-bound",
    "exact-witness-policy-bound",
    "checkpoint-chain-reverified-before-witness-decision",
    "named-witness-identity-revisions-verified",
    "witness-head-observations-preserved-without-voting",
    "checkpoint-and-witness-reports-persisted",
    "witness-outcome-finalized",
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
class WitnessGatedFinalManifest:
    """Final marker for witness abstention or checkpoint-gated outcome."""

    final_id: str
    experiment_run_id: str
    status: WitnessGatedRunnerStatus
    witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
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
        if any(
            not value.strip()
            for value in (
                self.final_id,
                self.experiment_run_id,
                self.experiment_id,
                self.experiment_version,
            )
        ):
            raise ValueError("witness-gated identity fields must not be empty")
        if self.status is not WitnessGatedRunnerStatus.VERIFIED:
            raise ValueError("witness-gated status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError(
                "witness-gated execution requires unique multiple content items"
            )
        if not self.witness_attestation_refs:
            raise ValueError(
                "witness-gated final requires witness attestations"
            )
        if self.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("witness abstention must be terminal abstention")
            if self.revocation_outcome is not None:
                raise ValueError(
                    "witness abstention may not claim a revocation outcome"
                )
            if self.checkpoint_final_ref is not None:
                raise ValueError(
                    "witness abstention may not reference checkpoint execution"
                )
            expected_id = f"{self.experiment_run_id}:checkpoint-witness-abstention"
        else:
            if self.revocation_outcome is None or self.checkpoint_final_ref is None:
                raise ValueError(
                    "witness-permitted outcome requires checkpoint execution"
                )
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-witness-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "checkpoint-witness-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from witness terminal outcome")
        if self.verified_checks != WITNESS_GATED_VERIFIED_CHECKS:
            raise ValueError("witness-gated final must preserve every check")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedWitnessGatedReceipt:
    """Proof of witness decision and optional checkpoint-gated execution."""

    experiment_run_id: str
    status: WitnessGatedRunnerStatus
    witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
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
    checkpoint_receipt: VerifiedCheckpointGatedReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not WitnessGatedRunnerStatus.VERIFIED:
            raise ValueError("verified witness-gated status must be verified")
        if self.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None:
                raise ValueError(
                    "witness abstention may not contain checkpoint receipt"
                )
            if self.revocation_outcome is not None:
                raise ValueError(
                    "witness abstention may not claim revocation outcome"
                )
            expected_id = f"{self.experiment_run_id}:checkpoint-witness-abstention"
        else:
            if self.checkpoint_receipt is None:
                raise ValueError(
                    "witness-permitted receipt requires checkpoint receipt"
                )
            if self.checkpoint_receipt.revocation_outcome is not (
                self.revocation_outcome
            ):
                raise ValueError(
                    "checkpoint receipt differs from revocation outcome"
                )
            if self.checkpoint_receipt.terminal_outcome is not (
                self.terminal_outcome
            ):
                raise ValueError(
                    "checkpoint receipt differs from terminal outcome"
                )
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-witness-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:"
                    "checkpoint-witness-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest must identify witness outcome")
        if self.verified_checks != WITNESS_GATED_VERIFIED_CHECKS:
            raise ValueError(
                "verified witness receipt must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class WitnessGatedCheckpointExperimentRunner:
    """Verify checkpoint chain and witness observations before execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CheckpointGatedRevocationExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: WitnessBoundCheckpointCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        for value, field_name in (
            (checkpoint_verified_at, "checkpoint_verified_at"),
            (witness_evaluated_at, "witness_evaluated_at"),
            (revocation_evaluated_at, "revocation_evaluated_at"),
            (credential_evaluated_at, "credential_evaluated_at"),
            (quality_evaluated_at, "quality_evaluated_at"),
            (review_evaluated_at, "review_evaluated_at"),
        ):
            _parse_timestamp(value, field_name)
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("witness-gated execution requires a frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != (
            corpus.content_ids
        ):
            raise ValueError("plan must match witness-bound corpus exactly")
        if corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry reference must match corpus")
        if corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy reference must match corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError(
                "execution windows must match frozen content order"
            )

    def _persist_checkpoint_report(
        self,
        *,
        experiment_run_id: str,
        report: CredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:"
                "credential-revocation-checkpoint-verification"
            ),
            report,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint verification differs from report"
            )
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
        decision: CheckpointWitnessDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:checkpoint-witness-decision",
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored witness decision differs from report"
            )
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
        final: WitnessGatedFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: WitnessBoundCheckpointCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_evidence: StoredCheckpointWitnessEvidence,
        checkpoint_evidence: StoredCredentialRevocationCheckpointEvidence,
        checkpoint_report: CredentialRevocationCheckpointVerificationReport,
        witness_decision: CheckpointWitnessDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored witness-gated final differs from expected"
            )
        if self._store.get(
            final.witness_corpus_ref.artifact_id,
            expected_hash=final.witness_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "witness corpus differs during verification"
            )
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != witness_registry.canonical_payload:
            raise ArtifactIntegrityError(
                "witness registry differs during verification"
            )
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != witness_policy.canonical_payload:
            raise ArtifactIntegrityError(
                "witness policy differs during verification"
            )
        for reference in witness_evidence.attestation_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        for reference in checkpoint_evidence.checkpoint_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        checkpoint_report_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:"
                "credential-revocation-checkpoint-verification"
            ),
            checkpoint_report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != checkpoint_report_artifact.payload:
            raise ArtifactIntegrityError(
                "checkpoint report differs during witness verification"
            )
        witness_decision_artifact = serialize_artifact(
            f"{final.experiment_run_id}:checkpoint-witness-decision",
            witness_decision,
        )
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != witness_decision_artifact.payload:
            raise ArtifactIntegrityError(
                "witness decision differs during final verification"
            )
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
        checkpoints: tuple[
            CredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        corpus: WitnessBoundCheckpointCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedWitnessGatedReceipt:
        """Return a verified witness abstention or downstream checkpoint outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                windows=windows,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=checkpoint_verified_at,
                witness_evaluated_at=witness_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except ValueError as exc:
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            witness_evidence = load_checkpoint_witness_evidence(
                self._store,
                corpus=corpus,
                registry=witness_registry,
                policy=witness_policy,
            )
            checkpoint_evidence = (
                load_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus.corpus,
                    policy=checkpoint_policy,
                    log=checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            CheckpointWitnessError,
            CredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = validate_credential_revocation_checkpoints(
                plan=plan,
                corpus=corpus.corpus,
                policy=checkpoint_policy,
                log=checkpoint_log,
                ledger=ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=checkpoint_verified_at,
            )
        except (CredentialRevocationCheckpointError, ValueError) as exc:
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.CHECKPOINT_VALIDATION,
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
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_checkpoint_witness_attestations(
                plan=plan,
                corpus=corpus,
                registry=witness_registry,
                policy=witness_policy,
                head_checkpoint=checkpoint_evidence.checkpoints[-1],
                attestations=witness_evidence.attestations,
                evaluated_at=witness_evaluated_at,
            )
        except (CheckpointWitnessError, ValueError) as exc:
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.WITNESS_VALIDATION,
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
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        checkpoint_receipt: VerifiedCheckpointGatedReceipt | None = None
        checkpoint_final_ref: StoredArtifactRef | None = None
        revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = witness_evaluated_at
        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
            try:
                checkpoint_receipt = self._runner.run(
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
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    checkpoint_verified_at=checkpoint_verified_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except CheckpointGatedExperimentError as exc:
                raise WitnessGatedExperimentError(
                    WitnessGatedRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            checkpoint_final_ref = checkpoint_receipt.final_manifest_ref
            revocation_outcome = checkpoint_receipt.revocation_outcome
            terminal_outcome = checkpoint_receipt.terminal_outcome
            completed_at = checkpoint_receipt.completed_at

        final = WitnessGatedFinalManifest(
            final_id=(
                f"{experiment_run_id}:checkpoint-witness-abstention"
                if witness_decision.outcome
                is CheckpointWitnessDecisionOutcome.ABSTAIN
                else (
                    f"{experiment_run_id}:checkpoint-witness-completion"
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else (
                        f"{experiment_run_id}:"
                        "checkpoint-witness-terminal-abstention"
                    )
                )
            ),
            experiment_run_id=experiment_run_id,
            status=WitnessGatedRunnerStatus.VERIFIED,
            witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
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
            verified_checks=WITNESS_GATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(
                serialize_artifact(final.final_id, final)
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.FINAL_PERSISTENCE,
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
                witness_registry=witness_registry,
                witness_policy=witness_policy,
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
            raise WitnessGatedExperimentError(
                WitnessGatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedWitnessGatedReceipt(
            experiment_run_id=experiment_run_id,
            status=WitnessGatedRunnerStatus.VERIFIED,
            witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
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
            checkpoint_receipt=checkpoint_receipt,
            final_manifest_ref=final_ref,
            verified_checks=WITNESS_GATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
