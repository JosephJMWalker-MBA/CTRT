"""Gate eligible extraction execution on independent quality evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_store import ArtifactIntegrityError, ArtifactStoreError, FileSystemArtifactStore, StoredArtifactRef
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.eligible_extraction_runner import EligibleExtractionExperimentError, EligibleExtractionExperimentRunner, VerifiedEligibleExtractionExperimentReceipt
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import (
    ExtractionQualityDecisionReport,
    ExtractionQualityEvidenceError,
    ExtractionQualityPolicySnapshot,
    QualityBoundExtractionCorpusSnapshot,
    QualityDecisionOutcome,
    StoredQualityEvidence,
    load_quality_evidence,
    validate_extraction_quality_evidence,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class QualityGatedRunnerStage(StrEnum):
    """Boundary at which quality-gated execution failed."""

    PREFLIGHT = "preflight"
    QUALITY_LOADING = "quality-loading"
    QUALITY_VALIDATION = "quality-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    EXPERIMENT_EXECUTION = "experiment-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class QualityGatedRunnerStatus(StrEnum):
    """A quality-gated receipt exists only after final reverification."""

    VERIFIED = "verified"


class QualityGatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: QualityGatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


QUALITY_GATED_VERIFIED_CHECKS = (
    "exact-quality-policy-bound",
    "quality-assessments-reverified",
    "automated-and-review-evidence-preserved",
    "uncertainty-and-abstention-preserved",
    "quality-decision-persisted",
    "quality-outcome-finalized",
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
class QualityGatedExtractionFinalManifest:
    """Final marker for either governed abstention or executed completion."""

    final_id: str
    experiment_run_id: str
    status: QualityGatedRunnerStatus
    outcome: QualityDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    quality_corpus_ref: StoredArtifactRef
    quality_policy_ref: StoredArtifactRef
    quality_assessment_refs: tuple[StoredArtifactRef, ...]
    quality_decision_ref: StoredArtifactRef
    eligible_extraction_completion_ref: StoredArtifactRef | None
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
            raise ValueError("quality-gated final identity fields must not be empty")
        if self.status is not QualityGatedRunnerStatus.VERIFIED:
            raise ValueError("quality-gated final status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("quality-gated final requires unique multiple content items")
        if len(self.quality_assessment_refs) != len(self.content_ids):
            raise ValueError("quality-gated final requires one assessment per content")
        if self.outcome is QualityDecisionOutcome.EXECUTE:
            if self.final_id != f"{self.experiment_run_id}:quality-gated-completion":
                raise ValueError("executed final_id must derive from experiment_run_id")
            if self.eligible_extraction_completion_ref is None:
                raise ValueError("executed quality outcome requires eligible completion")
            if self.eligible_extraction_completion_ref.artifact_id != (
                f"{self.experiment_run_id}:eligible-extraction-completion"
            ):
                raise ValueError("eligible completion must identify experiment_run_id")
        else:
            if self.final_id != f"{self.experiment_run_id}:quality-abstention":
                raise ValueError("abstention final_id must derive from experiment_run_id")
            if self.eligible_extraction_completion_ref is not None:
                raise ValueError("abstained outcome may not reference execution completion")
        if self.verified_checks != QUALITY_GATED_VERIFIED_CHECKS:
            raise ValueError("quality-gated final must preserve every check")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedQualityGatedExtractionReceipt:
    """Proof of an evidence-bound execute or abstain outcome."""

    experiment_run_id: str
    status: QualityGatedRunnerStatus
    outcome: QualityDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    quality_corpus_ref: StoredArtifactRef
    quality_policy_ref: StoredArtifactRef
    quality_assessment_refs: tuple[StoredArtifactRef, ...]
    quality_decision_ref: StoredArtifactRef
    eligible_extraction_receipt: VerifiedEligibleExtractionExperimentReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not QualityGatedRunnerStatus.VERIFIED:
            raise ValueError("verified quality-gated status must be verified")
        if len(self.quality_assessment_refs) != len(self.content_ids):
            raise ValueError("verified receipt requires one assessment per content")
        if self.outcome is QualityDecisionOutcome.EXECUTE:
            if self.eligible_extraction_receipt is None:
                raise ValueError("executed receipt requires eligible extraction receipt")
            if self.eligible_extraction_receipt.experiment_run_id != self.experiment_run_id:
                raise ValueError("eligible receipt must identify experiment_run_id")
            expected_id = f"{self.experiment_run_id}:quality-gated-completion"
        else:
            if self.eligible_extraction_receipt is not None:
                raise ValueError("abstained receipt may not contain execution receipt")
            expected_id = f"{self.experiment_run_id}:quality-abstention"
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest reference must identify this outcome")
        if self.verified_checks != QUALITY_GATED_VERIFIED_CHECKS:
            raise ValueError("verified receipt must preserve every check")
        _parse_timestamp(self.completed_at, "completed_at")


class QualityGatedExtractionExperimentRunner:
    """Evaluate quality evidence before eligible extraction execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = EligibleExtractionExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: QualityBoundExtractionCorpusSnapshot,
        policy: ExtractionQualityPolicySnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        quality_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(quality_evaluated_at, "quality_evaluated_at")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("quality-gated execution requires a frozen plan")
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan corpus_ref must match quality-bound corpus")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order must match quality-bound corpus")
        if corpus.quality_policy_ref != policy.reference():
            raise ValueError("quality-bound corpus policy reference must match policy")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError("execution windows must match unique frozen content order")

    def _persist_decision(
        self,
        report: ExtractionQualityDecisionReport,
        experiment_run_id: str,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:extraction-quality-decision",
            report,
        )
        reference = self._store.append(artifact)
        stored = self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError("stored quality decision differs from report")

        index_artifact = serialize_artifact(
            report.artifact_id,
            {
                "experiment_id": report.experiment_id,
                "experiment_version": report.experiment_version,
                "quality_corpus_ref": report.quality_corpus_ref,
                "quality_policy_ref": report.quality_policy_ref,
            },
        )
        self._store.append(index_artifact)
        return reference

    def _verify_final(
        self,
        *,
        final: QualityGatedExtractionFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: QualityBoundExtractionCorpusSnapshot,
        policy: ExtractionQualityPolicySnapshot,
        evidence: StoredQualityEvidence,
        decision: ExtractionQualityDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored = self._store.get(final_ref.artifact_id, expected_hash=final_ref.artifact_hash)
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError("stored quality-gated final differs")
        if self._store.get(
            final.quality_corpus_ref.artifact_id,
            expected_hash=final.quality_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("quality corpus differs during verification")
        if self._store.get(
            final.quality_policy_ref.artifact_id,
            expected_hash=final.quality_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("quality policy differs during verification")
        for reference in evidence.assessment_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        decision_artifact = serialize_artifact(
            f"{final.experiment_run_id}:extraction-quality-decision",
            decision,
        )
        if self._store.get(
            final.quality_decision_ref.artifact_id,
            expected_hash=final.quality_decision_ref.artifact_hash,
        ).payload != decision_artifact.payload:
            raise ArtifactIntegrityError("quality decision differs during verification")
        if final.eligible_extraction_completion_ref is not None:
            self._store.get(
                final.eligible_extraction_completion_ref.artifact_id,
                expected_hash=final.eligible_extraction_completion_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        method_registry: ExtractionMethodRegistrySnapshot,
        quality_policy: ExtractionQualityPolicySnapshot,
        corpus: QualityBoundExtractionCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        quality_evaluated_at: str,
    ) -> VerifiedQualityGatedExtractionReceipt:
        """Return a verified abstention or executed verified completion."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                policy=quality_policy,
                windows=windows,
                experiment_run_id=experiment_run_id,
                quality_evaluated_at=quality_evaluated_at,
            )
        except ValueError as exc:
            raise QualityGatedExperimentError(QualityGatedRunnerStage.PREFLIGHT, str(exc)) from exc

        try:
            evidence = load_quality_evidence(self._store, corpus=corpus, policy=quality_policy)
        except (ArtifactStoreError, ExtractionQualityEvidenceError, OSError, ValueError) as exc:
            raise QualityGatedExperimentError(QualityGatedRunnerStage.QUALITY_LOADING, str(exc)) from exc

        try:
            decision = validate_extraction_quality_evidence(
                plan=plan,
                corpus=corpus,
                policy=quality_policy,
                assessments=evidence.assessments,
                evaluated_at=quality_evaluated_at,
            )
        except (ExtractionQualityEvidenceError, ValueError) as exc:
            raise QualityGatedExperimentError(QualityGatedRunnerStage.QUALITY_VALIDATION, str(exc)) from exc

        try:
            decision_ref = self._persist_decision(decision, experiment_run_id)
        except (ArtifactStoreError, CanonicalSerializationError, OSError, ValueError) as exc:
            raise QualityGatedExperimentError(QualityGatedRunnerStage.DECISION_PERSISTENCE, str(exc)) from exc

        eligible_receipt: VerifiedEligibleExtractionExperimentReceipt | None = None
        eligible_completion_ref: StoredArtifactRef | None = None
        completed_at = quality_evaluated_at
        if decision.outcome is QualityDecisionOutcome.EXECUTE:
            try:
                eligible_receipt = self._runner.run(
                    plan=plan,
                    candidate_registry=candidate_registry,
                    method_registry=method_registry,
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                )
            except EligibleExtractionExperimentError as exc:
                raise QualityGatedExperimentError(
                    QualityGatedRunnerStage.EXPERIMENT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            eligible_completion_ref = eligible_receipt.completion_manifest_ref
            completed_at = eligible_receipt.completed_at

        final = QualityGatedExtractionFinalManifest(
            final_id=(
                f"{experiment_run_id}:quality-gated-completion"
                if decision.outcome is QualityDecisionOutcome.EXECUTE
                else f"{experiment_run_id}:quality-abstention"
            ),
            experiment_run_id=experiment_run_id,
            status=QualityGatedRunnerStatus.VERIFIED,
            outcome=decision.outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            quality_corpus_ref=evidence.corpus_ref,
            quality_policy_ref=evidence.policy_ref,
            quality_assessment_refs=evidence.assessment_refs,
            quality_decision_ref=decision_ref,
            eligible_extraction_completion_ref=eligible_completion_ref,
            verified_checks=QUALITY_GATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(serialize_artifact(final.final_id, final))
        except (ArtifactStoreError, CanonicalSerializationError, OSError, ValueError) as exc:
            raise QualityGatedExperimentError(
                QualityGatedRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if decision.outcome is QualityDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                policy=quality_policy,
                evidence=evidence,
                decision=decision,
            )
        except (ArtifactStoreError, CanonicalSerializationError, OSError, ValueError) as exc:
            raise QualityGatedExperimentError(
                QualityGatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if decision.outcome is QualityDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedQualityGatedExtractionReceipt(
            experiment_run_id=experiment_run_id,
            status=QualityGatedRunnerStatus.VERIFIED,
            outcome=decision.outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            quality_corpus_ref=evidence.corpus_ref,
            quality_policy_ref=evidence.policy_ref,
            quality_assessment_refs=evidence.assessment_refs,
            quality_decision_ref=decision_ref,
            eligible_extraction_receipt=eligible_receipt,
            final_manifest_ref=final_ref,
            verified_checks=QUALITY_GATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
