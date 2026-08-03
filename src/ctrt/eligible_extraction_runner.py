"""Authorize extraction methods before governed extraction-bound execution."""

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
from ctrt.extraction_bound_runner import (
    ExtractionBoundExperimentError,
    ExtractionBoundExperimentRunner,
    ExtractionExecutionWindow,
    VerifiedExtractionBoundExperimentReceipt,
)
from ctrt.extraction_manifest import (
    ExtractionManifestError,
    ExtractionManifestSnapshot,
)
from ctrt.extraction_method_eligibility import (
    AuthorizedExtractionMethod,
    ExtractionMethodEligibilityError,
    ExtractionMethodEligibilityReport,
    ExtractionMethodRegistrySnapshot,
    MethodBoundExtractionCorpusSnapshot,
    validate_extraction_method_eligibility,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class EligibleExtractionRunnerStage(StrEnum):
    """Boundary at which method-authorized extraction execution failed."""

    PREFLIGHT = "preflight"
    EXTRACTION_LOADING = "extraction-loading"
    ELIGIBILITY = "eligibility"
    ELIGIBILITY_PERSISTENCE = "eligibility-persistence"
    EXPERIMENT_EXECUTION = "experiment-execution"
    COMPLETION_PERSISTENCE = "completion-persistence"
    VERIFICATION = "verification"


class EligibleExtractionRunnerStatus(StrEnum):
    """A receipt exists only after method authorization and final verification."""

    VERIFIED = "verified"


class EligibleExtractionExperimentError(RuntimeError):
    """Fail-closed error preserving stage and any completed content IDs."""

    def __init__(
        self,
        stage: EligibleExtractionRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


ELIGIBLE_EXTRACTION_VERIFIED_CHECKS = (
    "exact-method-registry-bound",
    "method-registry-accepted",
    "method-revisions-authorized",
    "source-types-and-mapping-kinds-authorized",
    "configuration-hashes-authorized",
    "eligibility-report-persisted",
    "extraction-bound-completion-reverified",
    "eligible-extraction-completion-reverified",
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
class EligibleExtractionExperimentCompletion:
    """Final marker linking method authorization to extraction-bound completion."""

    completion_id: str
    experiment_run_id: str
    status: EligibleExtractionRunnerStatus
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    method_registry_ref: StoredArtifactRef
    eligibility_report_ref: StoredArtifactRef
    extraction_bound_completion_ref: StoredArtifactRef
    authorized_extractions: tuple[AuthorizedExtractionMethod, ...]
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        required = (
            self.completion_id,
            self.experiment_run_id,
            self.experiment_id,
            self.experiment_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError(
                "eligible extraction completion identity fields must not be empty"
            )
        if self.status is not EligibleExtractionRunnerStatus.VERIFIED:
            raise ValueError("eligible extraction completion status must be verified")
        expected_id = f"{self.experiment_run_id}:eligible-extraction-completion"
        if self.completion_id != expected_id:
            raise ValueError("completion_id must derive from experiment_run_id")
        expected_bound = f"{self.experiment_run_id}:extraction-bound-completion"
        if self.extraction_bound_completion_ref.artifact_id != expected_bound:
            raise ValueError(
                "extraction-bound completion reference must identify experiment_run_id"
            )
        if len(self.content_ids) < 2:
            raise ValueError(
                "eligible extraction completion requires multiple content items"
            )
        if len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("eligible extraction content IDs must be unique")
        if tuple(item.content_id for item in self.authorized_extractions) != (
            self.content_ids
        ):
            raise ValueError(
                "authorized extraction order must match completion content IDs"
            )
        if self.verified_checks != ELIGIBLE_EXTRACTION_VERIFIED_CHECKS:
            raise ValueError(
                "eligible extraction completion must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedEligibleExtractionExperimentReceipt:
    """Proof that only registry-authorized extraction methods drove execution."""

    experiment_run_id: str
    status: EligibleExtractionRunnerStatus
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    method_registry_ref: StoredArtifactRef
    eligibility_report_ref: StoredArtifactRef
    extraction_bound_receipt: VerifiedExtractionBoundExperimentReceipt
    completion_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not EligibleExtractionRunnerStatus.VERIFIED:
            raise ValueError("verified eligible extraction status must be verified")
        if self.extraction_bound_receipt.experiment_run_id != self.experiment_run_id:
            raise ValueError(
                "extraction-bound receipt must identify experiment_run_id"
            )
        if self.extraction_bound_receipt.content_ids != self.content_ids:
            raise ValueError("extraction-bound receipt content order must match")
        expected_id = f"{self.experiment_run_id}:eligible-extraction-completion"
        if self.completion_manifest_ref.artifact_id != expected_id:
            raise ValueError("completion manifest reference must identify this run")
        if self.verified_checks != ELIGIBLE_EXTRACTION_VERIFIED_CHECKS:
            raise ValueError(
                "verified eligible extraction receipt must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class EligibleExtractionExperimentRunner:
    """Authorize stored extraction methods before delegating governed execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = ExtractionBoundExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: MethodBoundExtractionCorpusSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("eligible extraction execution requires a frozen plan")
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan corpus_ref must match the method-bound corpus")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order must match the method-bound corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids:
            raise ValueError(
                "execution windows must match frozen content IDs exactly and in order"
            )
        if len(window_ids) < 2:
            raise ValueError(
                "eligible extraction execution requires multiple content items"
            )

    def _load_extractions(
        self,
        corpus: MethodBoundExtractionCorpusSnapshot,
    ) -> tuple[ExtractionManifestSnapshot, ...]:
        extractions: list[ExtractionManifestSnapshot] = []
        for entry in corpus.corpus.contents:
            artifact = self._store.get(
                entry.extraction_artifact_ref.artifact_id,
                expected_hash=entry.extraction_artifact_ref.artifact_hash,
            )
            extraction = ExtractionManifestSnapshot.from_artifact(artifact)
            if extraction.reference() != entry.extraction_artifact_ref:
                raise ArtifactIntegrityError(
                    "stored extraction reference differs from frozen corpus"
                )
            extractions.append(extraction)
        return tuple(extractions)

    def _persist_eligibility(
        self,
        *,
        registry: ExtractionMethodRegistrySnapshot,
        report: ExtractionMethodEligibilityReport,
    ) -> tuple[StoredArtifactRef, StoredArtifactRef]:
        registry_ref = self._store.append(registry.artifact())
        stored_registry = self._store.get(
            registry_ref.artifact_id,
            expected_hash=registry_ref.artifact_hash,
        )
        if stored_registry.payload != registry.canonical_payload:
            raise ArtifactIntegrityError(
                "stored extraction method registry differs from expected registry"
            )
        report_artifact = report.artifact()
        report_ref = self._store.append(report_artifact)
        stored_report = self._store.get(
            report_ref.artifact_id,
            expected_hash=report_ref.artifact_hash,
        )
        if stored_report.payload != report_artifact.payload:
            raise ArtifactIntegrityError(
                "stored extraction eligibility report differs from expected report"
            )
        return registry_ref, report_ref

    def _verify_completion(
        self,
        *,
        completion: EligibleExtractionExperimentCompletion,
        completion_ref: StoredArtifactRef,
        registry: ExtractionMethodRegistrySnapshot,
        report: ExtractionMethodEligibilityReport,
    ) -> None:
        expected = serialize_artifact(completion.completion_id, completion)
        stored = self._store.get(
            completion_ref.artifact_id,
            expected_hash=completion_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored eligible extraction completion differs from expected"
            )
        stored_registry = self._store.get(
            completion.method_registry_ref.artifact_id,
            expected_hash=completion.method_registry_ref.artifact_hash,
        )
        if stored_registry.payload != registry.canonical_payload:
            raise ArtifactIntegrityError(
                "method registry differs during final verification"
            )
        expected_report = report.artifact()
        stored_report = self._store.get(
            completion.eligibility_report_ref.artifact_id,
            expected_hash=completion.eligibility_report_ref.artifact_hash,
        )
        if stored_report.payload != expected_report.payload:
            raise ArtifactIntegrityError(
                "eligibility report differs during final verification"
            )
        self._store.get(
            completion.extraction_bound_completion_ref.artifact_id,
            expected_hash=completion.extraction_bound_completion_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        method_registry: ExtractionMethodRegistrySnapshot,
        corpus: MethodBoundExtractionCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
    ) -> VerifiedEligibleExtractionExperimentReceipt:
        """Return only after method eligibility and all completion links reverify."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                windows=windows,
                experiment_run_id=experiment_run_id,
            )
        except ValueError as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            extractions = self._load_extractions(corpus)
        except (
            ArtifactStoreError,
            ExtractionManifestError,
            OSError,
            ValueError,
        ) as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.EXTRACTION_LOADING,
                str(exc),
            ) from exc

        try:
            report = validate_extraction_method_eligibility(
                plan=plan,
                corpus=corpus,
                registry=method_registry,
                extractions=extractions,
            )
        except (ExtractionMethodEligibilityError, ValueError) as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.ELIGIBILITY,
                str(exc),
            ) from exc

        try:
            method_registry_ref, eligibility_report_ref = (
                self._persist_eligibility(
                    registry=method_registry,
                    report=report,
                )
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.ELIGIBILITY_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            extraction_bound_receipt = self._runner.run(
                plan=plan,
                candidate_registry=candidate_registry,
                corpus_manifest=corpus.corpus,
                environment=environment,
                windows=windows,
                experiment_run_id=experiment_run_id,
            )
        except ExtractionBoundExperimentError as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.EXPERIMENT_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        completion = EligibleExtractionExperimentCompletion(
            completion_id=f"{experiment_run_id}:eligible-extraction-completion",
            experiment_run_id=experiment_run_id,
            status=EligibleExtractionRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            method_registry_ref=method_registry_ref,
            eligibility_report_ref=eligibility_report_ref,
            extraction_bound_completion_ref=(
                extraction_bound_receipt.completion_manifest_ref
            ),
            authorized_extractions=report.authorized_extractions,
            verified_checks=ELIGIBLE_EXTRACTION_VERIFIED_CHECKS,
            completed_at=extraction_bound_receipt.completed_at,
        )
        try:
            completion_artifact = serialize_artifact(
                completion.completion_id,
                completion,
            )
            completion_ref = self._store.append(completion_artifact)
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.COMPLETION_PERSISTENCE,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        try:
            self._verify_completion(
                completion=completion,
                completion_ref=completion_ref,
                registry=method_registry,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise EligibleExtractionExperimentError(
                EligibleExtractionRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        return VerifiedEligibleExtractionExperimentReceipt(
            experiment_run_id=experiment_run_id,
            status=EligibleExtractionRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            method_registry_ref=method_registry_ref,
            eligibility_report_ref=eligibility_report_ref,
            extraction_bound_receipt=extraction_bound_receipt,
            completion_manifest_ref=completion_ref,
            verified_checks=ELIGIBLE_EXTRACTION_VERIFIED_CHECKS,
            completed_at=completion.completed_at,
        )
