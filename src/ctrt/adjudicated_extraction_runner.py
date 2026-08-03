"""Gate quality-controlled extraction execution on review adjudication."""

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
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import (
    ExtractionQualityDecisionReport,
    ExtractionQualityEvidenceError,
    ExtractionQualityPolicySnapshot,
    QualityDecisionOutcome,
    StoredQualityEvidence,
    load_quality_evidence,
    validate_extraction_quality_evidence,
)
from ctrt.extraction_review_adjudication import (
    ReviewAdjudicationDecisionReport,
    ReviewAdjudicationError,
    ReviewAdjudicationPolicySnapshot,
    ReviewBoundExtractionCorpusSnapshot,
    ReviewDecisionOutcome,
    ReviewerRegistrySnapshot,
    StoredReviewAdjudicationEvidence,
    load_review_adjudication_evidence,
    validate_review_adjudication_evidence,
)
from ctrt.quality_gated_extraction_runner import (
    QualityGatedExperimentError,
    QualityGatedExtractionExperimentRunner,
    VerifiedQualityGatedExtractionReceipt,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class AdjudicatedExtractionRunnerStage(StrEnum):
    """Boundary at which review-adjudicated execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVIEW_VALIDATION = "review-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    QUALITY_GATE = "quality-gate"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicatedExtractionRunnerStatus(StrEnum):
    """A receipt exists only after review and final reverification."""

    VERIFIED = "verified"


class AdjudicatedExtractionExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicatedExtractionRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ADJUDICATED_EXTRACTION_VERIFIED_CHECKS = (
    "exact-reviewer-registry-bound",
    "reviewer-identities-and-roles-authorized",
    "contradictions-and-dissent-preserved",
    "adjudication-status-and-disagreement-preserved",
    "review-decision-persisted",
    "review-outcome-finalized",
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
class AdjudicatedExtractionFinalManifest:
    """Final marker for review-permitted execution or governed abstention."""

    final_id: str
    experiment_run_id: str
    status: AdjudicatedExtractionRunnerStatus
    review_outcome: ReviewDecisionOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    review_corpus_ref: StoredArtifactRef
    reviewer_registry_ref: StoredArtifactRef
    review_policy_ref: StoredArtifactRef
    review_adjudication_refs: tuple[StoredArtifactRef, ...]
    review_decision_ref: StoredArtifactRef
    quality_decision_ref: StoredArtifactRef
    quality_gated_final_ref: StoredArtifactRef | None
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
            raise ValueError(
                "adjudicated extraction identity fields must not be empty"
            )
        if self.status is not AdjudicatedExtractionRunnerStatus.VERIFIED:
            raise ValueError("adjudicated extraction status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError(
                "adjudicated extraction requires unique multiple content items"
            )
        if len(self.review_adjudication_refs) != len(self.content_ids):
            raise ValueError(
                "adjudicated extraction requires one review record per content"
            )
        if self.review_outcome is ReviewDecisionOutcome.ABSTAIN:
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("review abstention must be terminal abstention")
            if self.quality_gated_final_ref is not None:
                raise ValueError(
                    "review abstention may not reference quality-gated execution"
                )
        else:
            if self.quality_gated_final_ref is None:
                raise ValueError(
                    "review-permitted outcome requires quality-gated final"
                )
            expected_quality_id = (
                f"{self.experiment_run_id}:quality-gated-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else f"{self.experiment_run_id}:quality-abstention"
            )
            if self.quality_gated_final_ref.artifact_id != expected_quality_id:
                raise ValueError(
                    "quality-gated final does not match terminal outcome"
                )
        expected_final_id = (
            f"{self.experiment_run_id}:review-adjudicated-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else f"{self.experiment_run_id}:review-adjudication-abstention"
        )
        if self.final_id != expected_final_id:
            raise ValueError("final_id must derive from terminal outcome")
        if self.verified_checks != ADJUDICATED_EXTRACTION_VERIFIED_CHECKS:
            raise ValueError(
                "adjudicated extraction final must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedAdjudicatedExtractionReceipt:
    """Proof of identity-bound review execution or abstention."""

    experiment_run_id: str
    status: AdjudicatedExtractionRunnerStatus
    review_outcome: ReviewDecisionOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    review_corpus_ref: StoredArtifactRef
    reviewer_registry_ref: StoredArtifactRef
    review_policy_ref: StoredArtifactRef
    review_adjudication_refs: tuple[StoredArtifactRef, ...]
    review_decision_ref: StoredArtifactRef
    quality_decision_ref: StoredArtifactRef
    quality_gated_receipt: VerifiedQualityGatedExtractionReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not AdjudicatedExtractionRunnerStatus.VERIFIED:
            raise ValueError("verified adjudicated status must be verified")
        if len(self.review_adjudication_refs) != len(self.content_ids):
            raise ValueError("verified receipt requires one review per content")
        if self.review_outcome is ReviewDecisionOutcome.ABSTAIN:
            if self.quality_gated_receipt is not None:
                raise ValueError(
                    "review abstention may not contain quality-gated receipt"
                )
        else:
            if self.quality_gated_receipt is None:
                raise ValueError(
                    "review-permitted receipt requires quality-gated receipt"
                )
            observed_terminal = (
                ReviewDecisionOutcome.EXECUTE
                if self.quality_gated_receipt.outcome
                is QualityDecisionOutcome.EXECUTE
                else ReviewDecisionOutcome.ABSTAIN
            )
            if observed_terminal is not self.terminal_outcome:
                raise ValueError(
                    "quality-gated receipt outcome differs from terminal outcome"
                )
        expected_final_id = (
            f"{self.experiment_run_id}:review-adjudicated-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else f"{self.experiment_run_id}:review-adjudication-abstention"
        )
        if self.final_manifest_ref.artifact_id != expected_final_id:
            raise ValueError("final manifest must identify terminal outcome")
        if self.verified_checks != ADJUDICATED_EXTRACTION_VERIFIED_CHECKS:
            raise ValueError("verified receipt must preserve every check")
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatedExtractionExperimentRunner:
    """Evaluate reviewer adjudication before the existing quality gate."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._quality_runner = QualityGatedExtractionExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: ReviewBoundExtractionCorpusSnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        review_policy: ReviewAdjudicationPolicySnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(quality_evaluated_at, "quality_evaluated_at")
        _parse_timestamp(review_evaluated_at, "review_evaluated_at")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError(
                "review-adjudicated execution requires a frozen plan"
            )
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan corpus_ref must match review-bound corpus")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order must match review-bound corpus")
        if corpus.reviewer_registry_ref != reviewer_registry.reference():
            raise ValueError("reviewer registry reference must match corpus")
        if corpus.review_policy_ref != review_policy.reference():
            raise ValueError("review policy reference must match corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError(
                "execution windows must match frozen content order"
            )

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        review_decision: ReviewAdjudicationDecisionReport,
        quality_decision: ExtractionQualityDecisionReport,
    ) -> tuple[StoredArtifactRef, StoredArtifactRef]:
        review_artifact = serialize_artifact(
            f"{experiment_run_id}:review-adjudication-decision",
            review_decision,
        )
        review_ref = self._store.append(review_artifact)
        if self._store.get(
            review_ref.artifact_id,
            expected_hash=review_ref.artifact_hash,
        ).payload != review_artifact.payload:
            raise ArtifactIntegrityError(
                "stored review decision differs from expected report"
            )
        self._store.append(
            serialize_artifact(
                review_decision.artifact_id,
                {
                    "experiment_id": review_decision.experiment_id,
                    "experiment_version": review_decision.experiment_version,
                    "review_corpus_ref": review_decision.review_corpus_ref,
                    "reviewer_registry_ref": (
                        review_decision.reviewer_registry_ref
                    ),
                    "review_policy_ref": review_decision.review_policy_ref,
                },
            )
        )

        quality_artifact = serialize_artifact(
            f"{experiment_run_id}:extraction-quality-decision",
            quality_decision,
        )
        quality_ref = self._store.append(quality_artifact)
        if self._store.get(
            quality_ref.artifact_id,
            expected_hash=quality_ref.artifact_hash,
        ).payload != quality_artifact.payload:
            raise ArtifactIntegrityError(
                "stored quality decision differs from expected report"
            )
        return review_ref, quality_ref

    def _verify_final(
        self,
        *,
        final: AdjudicatedExtractionFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: ReviewBoundExtractionCorpusSnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        review_policy: ReviewAdjudicationPolicySnapshot,
        review_evidence: StoredReviewAdjudicationEvidence,
        review_decision: ReviewAdjudicationDecisionReport,
        quality_evidence: StoredQualityEvidence,
        quality_decision: ExtractionQualityDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored adjudicated final differs from expected"
            )
        if self._store.get(
            final.review_corpus_ref.artifact_id,
            expected_hash=final.review_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "review corpus differs during final verification"
            )
        if self._store.get(
            final.reviewer_registry_ref.artifact_id,
            expected_hash=final.reviewer_registry_ref.artifact_hash,
        ).payload != reviewer_registry.canonical_payload:
            raise ArtifactIntegrityError(
                "reviewer registry differs during final verification"
            )
        if self._store.get(
            final.review_policy_ref.artifact_id,
            expected_hash=final.review_policy_ref.artifact_hash,
        ).payload != review_policy.canonical_payload:
            raise ArtifactIntegrityError(
                "review policy differs during final verification"
            )
        for reference in review_evidence.adjudication_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        for reference in quality_evidence.assessment_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_review = serialize_artifact(
            f"{final.experiment_run_id}:review-adjudication-decision",
            review_decision,
        )
        if self._store.get(
            final.review_decision_ref.artifact_id,
            expected_hash=final.review_decision_ref.artifact_hash,
        ).payload != expected_review.payload:
            raise ArtifactIntegrityError(
                "review decision differs during final verification"
            )
        expected_quality = serialize_artifact(
            f"{final.experiment_run_id}:extraction-quality-decision",
            quality_decision,
        )
        if self._store.get(
            final.quality_decision_ref.artifact_id,
            expected_hash=final.quality_decision_ref.artifact_hash,
        ).payload != expected_quality.payload:
            raise ArtifactIntegrityError(
                "quality decision differs during final verification"
            )
        if final.quality_gated_final_ref is not None:
            self._store.get(
                final.quality_gated_final_ref.artifact_id,
                expected_hash=final.quality_gated_final_ref.artifact_hash,
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
        corpus: ReviewBoundExtractionCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedAdjudicatedExtractionReceipt:
        """Return a verified review abstention or quality-gated outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
                windows=windows,
                experiment_run_id=experiment_run_id,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except ValueError as exc:
            raise AdjudicatedExtractionExperimentError(
                AdjudicatedExtractionRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            quality_evidence = load_quality_evidence(
                self._store,
                corpus=corpus.corpus,
                policy=quality_policy,
            )
            review_evidence = load_review_adjudication_evidence(
                self._store,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
            )
        except (
            ArtifactStoreError,
            ExtractionQualityEvidenceError,
            ReviewAdjudicationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedExtractionExperimentError(
                AdjudicatedExtractionRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            quality_decision = validate_extraction_quality_evidence(
                plan=plan,
                corpus=corpus.corpus,
                policy=quality_policy,
                assessments=quality_evidence.assessments,
                evaluated_at=quality_evaluated_at,
            )
            review_decision = validate_review_adjudication_evidence(
                plan=plan,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
                adjudications=review_evidence.adjudications,
                evaluated_at=review_evaluated_at,
            )
        except (
            ExtractionQualityEvidenceError,
            ReviewAdjudicationError,
            ValueError,
        ) as exc:
            raise AdjudicatedExtractionExperimentError(
                AdjudicatedExtractionRunnerStage.REVIEW_VALIDATION,
                str(exc),
            ) from exc

        try:
            review_decision_ref, quality_decision_ref = self._persist_decision(
                experiment_run_id=experiment_run_id,
                review_decision=review_decision,
                quality_decision=quality_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedExtractionExperimentError(
                AdjudicatedExtractionRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        quality_receipt: VerifiedQualityGatedExtractionReceipt | None = None
        quality_final_ref: StoredArtifactRef | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = review_evaluated_at
        if review_decision.outcome is ReviewDecisionOutcome.EXECUTE:
            try:
                quality_receipt = self._quality_runner.run(
                    plan=plan,
                    candidate_registry=candidate_registry,
                    method_registry=method_registry,
                    quality_policy=quality_policy,
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    quality_evaluated_at=quality_evaluated_at,
                )
            except QualityGatedExperimentError as exc:
                raise AdjudicatedExtractionExperimentError(
                    AdjudicatedExtractionRunnerStage.QUALITY_GATE,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            quality_final_ref = quality_receipt.final_manifest_ref
            terminal_outcome = (
                ReviewDecisionOutcome.EXECUTE
                if quality_receipt.outcome is QualityDecisionOutcome.EXECUTE
                else ReviewDecisionOutcome.ABSTAIN
            )
            completed_at = quality_receipt.completed_at

        final = AdjudicatedExtractionFinalManifest(
            final_id=(
                f"{experiment_run_id}:review-adjudicated-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else f"{experiment_run_id}:review-adjudication-abstention"
            ),
            experiment_run_id=experiment_run_id,
            status=AdjudicatedExtractionRunnerStatus.VERIFIED,
            review_outcome=review_decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            review_corpus_ref=review_evidence.corpus_ref,
            reviewer_registry_ref=review_evidence.reviewer_registry_ref,
            review_policy_ref=review_evidence.review_policy_ref,
            review_adjudication_refs=review_evidence.adjudication_refs,
            review_decision_ref=review_decision_ref,
            quality_decision_ref=quality_decision_ref,
            quality_gated_final_ref=quality_final_ref,
            verified_checks=ADJUDICATED_EXTRACTION_VERIFIED_CHECKS,
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
            raise AdjudicatedExtractionExperimentError(
                AdjudicatedExtractionRunnerStage.FINAL_PERSISTENCE,
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
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
                review_evidence=review_evidence,
                review_decision=review_decision,
                quality_evidence=quality_evidence,
                quality_decision=quality_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicatedExtractionExperimentError(
                AdjudicatedExtractionRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedAdjudicatedExtractionReceipt(
            experiment_run_id=experiment_run_id,
            status=AdjudicatedExtractionRunnerStatus.VERIFIED,
            review_outcome=review_decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            review_corpus_ref=review_evidence.corpus_ref,
            reviewer_registry_ref=review_evidence.reviewer_registry_ref,
            review_policy_ref=review_evidence.review_policy_ref,
            review_adjudication_refs=review_evidence.adjudication_refs,
            review_decision_ref=review_decision_ref,
            quality_decision_ref=quality_decision_ref,
            quality_gated_receipt=quality_receipt,
            final_manifest_ref=final_ref,
            verified_checks=ADJUDICATED_EXTRACTION_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
