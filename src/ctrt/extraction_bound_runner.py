"""Run governed experiments from verified extraction artifact graphs."""

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
from ctrt.candidate_eligibility import (
    CandidateEligibilityError,
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.experiment_runner import (
    ContentExecutionRequest,
    MultiContentExperimentError,
    MultiContentExperimentRunner,
    VerifiedExperimentReceipt,
)
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_manifest import (
    ExtractionCorpusManifestSnapshot,
    ExtractionManifestError,
    StoredExtractedCorpus,
    load_extracted_corpus,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class ExtractionBoundRunnerStage(StrEnum):
    """Boundary at which extraction-bound execution failed."""

    PREFLIGHT = "preflight"
    EXTRACTION_LOADING = "extraction-loading"
    EXPERIMENT_EXECUTION = "experiment-execution"
    COMPLETION_PERSISTENCE = "completion-persistence"
    VERIFICATION = "verification"


class ExtractionBoundRunnerStatus(StrEnum):
    """An extraction-bound receipt exists only after full verification."""

    VERIFIED = "verified"


class ExtractionBoundExperimentError(RuntimeError):
    """Fail-closed error preserving stage and verified partial content."""

    def __init__(
        self,
        stage: ExtractionBoundRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


EXTRACTION_BOUND_VERIFIED_CHECKS = (
    "source-artifacts-reverified",
    "extraction-method-and-revision-bound",
    "coordinate-maps-reverified",
    "canonical-content-reconstructed",
    "experiment-completion-reverified",
    "extraction-bound-completion-reverified",
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
class ExtractionExecutionWindow:
    """Timing for content reconstructed from stored extraction artifacts."""

    content_id: str
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        if not self.content_id.strip():
            raise ValueError("content_id must not be empty")
        started = _parse_timestamp(self.started_at, "started_at")
        completed = _parse_timestamp(self.completed_at, "completed_at")
        if completed < started:
            raise ValueError("completed_at may not precede started_at")


@dataclass(frozen=True, slots=True)
class ExtractionBoundExperimentCompletion:
    """Final marker linking extraction provenance to experiment completion."""

    completion_id: str
    experiment_run_id: str
    status: ExtractionBoundRunnerStatus
    experiment_id: str
    experiment_version: str
    corpus_manifest_ref: StoredArtifactRef
    experiment_completion_ref: StoredArtifactRef
    content_ids: tuple[str, ...]
    source_artifact_refs: tuple[StoredArtifactRef, ...]
    extraction_artifact_refs: tuple[StoredArtifactRef, ...]
    content_artifact_refs: tuple[StoredArtifactRef, ...]
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
                "extraction-bound completion identity fields must not be empty"
            )
        if self.status is not ExtractionBoundRunnerStatus.VERIFIED:
            raise ValueError("extraction-bound completion status must be verified")
        expected_id = f"{self.experiment_run_id}:extraction-bound-completion"
        if self.completion_id != expected_id:
            raise ValueError("completion_id must derive from experiment_run_id")
        expected_experiment = f"{self.experiment_run_id}:experiment-completion"
        if self.experiment_completion_ref.artifact_id != expected_experiment:
            raise ValueError(
                "experiment completion reference must identify experiment_run_id"
            )
        count = len(self.content_ids)
        if count < 2:
            raise ValueError(
                "extraction-bound completion requires multiple content items"
            )
        if len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("extraction-bound content IDs must be unique")
        if not (
            len(self.source_artifact_refs)
            == len(self.extraction_artifact_refs)
            == len(self.content_artifact_refs)
            == count
        ):
            raise ValueError(
                "extraction-bound completion requires one artifact graph per content"
            )
        if self.verified_checks != EXTRACTION_BOUND_VERIFIED_CHECKS:
            raise ValueError(
                "extraction-bound completion must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedExtractionBoundExperimentReceipt:
    """Proof that execution used the verified stored extraction graph."""

    experiment_run_id: str
    status: ExtractionBoundRunnerStatus
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    source_artifact_refs: tuple[StoredArtifactRef, ...]
    extraction_artifact_refs: tuple[StoredArtifactRef, ...]
    content_artifact_refs: tuple[StoredArtifactRef, ...]
    experiment_receipt: VerifiedExperimentReceipt
    completion_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not ExtractionBoundRunnerStatus.VERIFIED:
            raise ValueError("verified extraction-bound status must be verified")
        if self.experiment_receipt.experiment_run_id != self.experiment_run_id:
            raise ValueError("experiment receipt must identify experiment_run_id")
        if self.experiment_receipt.content_ids != self.content_ids:
            raise ValueError("experiment receipt content order must match")
        count = len(self.content_ids)
        if not (
            len(self.source_artifact_refs)
            == len(self.extraction_artifact_refs)
            == len(self.content_artifact_refs)
            == count
        ):
            raise ValueError(
                "verified extraction receipt requires one graph per content"
            )
        expected_id = f"{self.experiment_run_id}:extraction-bound-completion"
        if self.completion_manifest_ref.artifact_id != expected_id:
            raise ValueError("completion manifest reference must identify this run")
        if self.verified_checks != EXTRACTION_BOUND_VERIFIED_CHECKS:
            raise ValueError(
                "verified extraction receipt must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class ExtractionBoundExperimentRunner:
    """Reconstruct exact inputs from extraction artifacts before execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = MultiContentExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        corpus_manifest: ExtractionCorpusManifestSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("extraction-bound execution requires a frozen plan")
        if plan.corpus_ref != corpus_manifest.reference():
            raise ValueError("plan corpus_ref must match extraction corpus")
        if plan.content_ids != corpus_manifest.content_ids:
            raise ValueError("plan content order must match extraction corpus")
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus_manifest.content_ids:
            raise ValueError(
                "execution windows must match frozen content IDs exactly and in order"
            )
        if len(window_ids) < 2:
            raise ValueError(
                "extraction-bound execution requires multiple content items"
            )
        validate_candidate_eligibility(plan, candidate_registry)

    def _verify_completion(
        self,
        *,
        completion: ExtractionBoundExperimentCompletion,
        completion_ref: StoredArtifactRef,
        corpus_manifest: ExtractionCorpusManifestSnapshot,
    ) -> StoredExtractedCorpus:
        expected = serialize_artifact(completion.completion_id, completion)
        stored = self._store.get(
            completion_ref.artifact_id,
            expected_hash=completion_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored extraction-bound completion differs from expected manifest"
            )
        loaded = load_extracted_corpus(self._store, corpus_manifest)
        if loaded.manifest_ref != completion.corpus_manifest_ref:
            raise ArtifactIntegrityError(
                "extraction corpus reference differs during verification"
            )
        if loaded.source_refs != completion.source_artifact_refs:
            raise ArtifactIntegrityError(
                "source artifact references differ during verification"
            )
        if loaded.extraction_refs != completion.extraction_artifact_refs:
            raise ArtifactIntegrityError(
                "extraction artifact references differ during verification"
            )
        if loaded.content_refs != completion.content_artifact_refs:
            raise ArtifactIntegrityError(
                "content artifact references differ during verification"
            )
        self._store.get(
            completion.experiment_completion_ref.artifact_id,
            expected_hash=completion.experiment_completion_ref.artifact_hash,
        )
        return loaded

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        corpus_manifest: ExtractionCorpusManifestSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
    ) -> VerifiedExtractionBoundExperimentReceipt:
        """Return only after extraction provenance and completion reverify."""

        try:
            self._preflight(
                plan=plan,
                candidate_registry=candidate_registry,
                corpus_manifest=corpus_manifest,
                windows=windows,
                experiment_run_id=experiment_run_id,
            )
        except (CandidateEligibilityError, ValueError) as exc:
            raise ExtractionBoundExperimentError(
                ExtractionBoundRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            extracted = load_extracted_corpus(self._store, corpus_manifest)
        except (
            ArtifactStoreError,
            ExtractionManifestError,
            OSError,
            ValueError,
        ) as exc:
            raise ExtractionBoundExperimentError(
                ExtractionBoundRunnerStage.EXTRACTION_LOADING,
                str(exc),
            ) from exc

        requests = tuple(
            ContentExecutionRequest(
                content=content,
                started_at=window.started_at,
                completed_at=window.completed_at,
            )
            for content, window in zip(
                extracted.contents,
                windows,
                strict=True,
            )
        )
        try:
            experiment_receipt = self._runner.run(
                plan=plan,
                candidate_registry=candidate_registry,
                environment=environment,
                requests=requests,
                experiment_run_id=experiment_run_id,
            )
        except MultiContentExperimentError as exc:
            raise ExtractionBoundExperimentError(
                ExtractionBoundRunnerStage.EXPERIMENT_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        completion = ExtractionBoundExperimentCompletion(
            completion_id=f"{experiment_run_id}:extraction-bound-completion",
            experiment_run_id=experiment_run_id,
            status=ExtractionBoundRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            corpus_manifest_ref=extracted.manifest_ref,
            experiment_completion_ref=(
                experiment_receipt.completion_manifest_ref
            ),
            content_ids=plan.content_ids,
            source_artifact_refs=extracted.source_refs,
            extraction_artifact_refs=extracted.extraction_refs,
            content_artifact_refs=extracted.content_refs,
            verified_checks=EXTRACTION_BOUND_VERIFIED_CHECKS,
            completed_at=experiment_receipt.completed_at,
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
            raise ExtractionBoundExperimentError(
                ExtractionBoundRunnerStage.COMPLETION_PERSISTENCE,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        try:
            verified = self._verify_completion(
                completion=completion,
                completion_ref=completion_ref,
                corpus_manifest=corpus_manifest,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            ExtractionManifestError,
            OSError,
            ValueError,
        ) as exc:
            raise ExtractionBoundExperimentError(
                ExtractionBoundRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        return VerifiedExtractionBoundExperimentReceipt(
            experiment_run_id=experiment_run_id,
            status=ExtractionBoundRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            source_artifact_refs=verified.source_refs,
            extraction_artifact_refs=verified.extraction_refs,
            content_artifact_refs=verified.content_refs,
            experiment_receipt=experiment_receipt,
            completion_manifest_ref=completion_ref,
            verified_checks=EXTRACTION_BOUND_VERIFIED_CHECKS,
            completed_at=completion.completed_at,
        )
