"""Run corpus-bound experiments from verified stored canonical content artifacts."""

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
from ctrt.canonical_content import (
    CanonicalContentError,
    load_canonical_corpus,
)
from ctrt.corpus_bound_runner import (
    CorpusBoundExperimentError,
    CorpusBoundExperimentRunner,
    CorpusBoundRunnerStatus,
    VerifiedCorpusBoundExperimentReceipt,
)
from ctrt.corpus_manifest import CorpusManifestSnapshot
from ctrt.experiment_runner import ContentExecutionRequest
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class StoredContentRunnerStage(StrEnum):
    """Boundary at which storage-backed experiment execution failed."""

    PREFLIGHT = "preflight"
    CONTENT_LOADING = "content-loading"
    EXPERIMENT_EXECUTION = "experiment-execution"
    COMPLETION_PERSISTENCE = "completion-persistence"
    VERIFICATION = "verification"


class StoredContentRunnerStatus(StrEnum):
    """A stored-content receipt exists only after final re-verification."""

    VERIFIED = "verified"


class StoredContentExperimentError(RuntimeError):
    """Fail-closed error preserving stage and any completed content IDs."""

    def __init__(
        self,
        stage: StoredContentRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


STORED_CONTENT_VERIFIED_CHECKS = (
    "canonical-content-artifacts-linked",
    "stored-content-artifacts-reverified",
    "execution-inputs-reconstructed",
    "corpus-bound-completion-reverified",
    "stored-content-completion-reverified",
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
class StoredContentExecutionWindow:
    """Execution timing for content whose bytes will be reconstructed from storage."""

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
class StoredContentExperimentCompletion:
    """Final marker linking stored inputs to verified corpus-bound completion."""

    completion_id: str
    experiment_run_id: str
    status: StoredContentRunnerStatus
    experiment_id: str
    experiment_version: str
    corpus_manifest_ref: StoredArtifactRef
    corpus_bound_completion_ref: StoredArtifactRef
    content_ids: tuple[str, ...]
    content_artifact_refs: tuple[StoredArtifactRef, ...]
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        identity_fields = (
            self.completion_id,
            self.experiment_run_id,
            self.experiment_id,
            self.experiment_version,
        )
        if any(not value.strip() for value in identity_fields):
            raise ValueError("stored-content completion identity fields must not be empty")
        if self.status is not StoredContentRunnerStatus.VERIFIED:
            raise ValueError("stored-content completion status must be verified")
        expected_id = f"{self.experiment_run_id}:stored-content-completion"
        if self.completion_id != expected_id:
            raise ValueError("completion_id must derive from experiment_run_id")
        expected_bound = f"{self.experiment_run_id}:corpus-bound-completion"
        if self.corpus_bound_completion_ref.artifact_id != expected_bound:
            raise ValueError(
                "corpus-bound completion reference must identify experiment_run_id"
            )
        if len(self.content_ids) < 2:
            raise ValueError("stored-content completion requires multiple content items")
        if len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("stored-content completion content IDs must be unique")
        if len(self.content_artifact_refs) != len(self.content_ids):
            raise ValueError(
                "stored-content completion requires one artifact per content ID"
            )
        if self.verified_checks != STORED_CONTENT_VERIFIED_CHECKS:
            raise ValueError(
                "stored-content completion must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedStoredContentExperimentReceipt:
    """Proof that execution inputs were reconstructed from verified stored content."""

    experiment_run_id: str
    status: StoredContentRunnerStatus
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    content_artifact_refs: tuple[StoredArtifactRef, ...]
    corpus_bound_receipt: VerifiedCorpusBoundExperimentReceipt
    completion_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.experiment_run_id,
                self.experiment_id,
                self.experiment_version,
            )
        ):
            raise ValueError("verified stored-content identity fields must not be empty")
        if self.status is not StoredContentRunnerStatus.VERIFIED:
            raise ValueError("verified stored-content receipt status must be verified")
        if self.corpus_bound_receipt.status is not CorpusBoundRunnerStatus.VERIFIED:
            raise ValueError("corpus-bound receipt must be verified")
        if self.corpus_bound_receipt.experiment_run_id != self.experiment_run_id:
            raise ValueError("corpus-bound receipt must identify experiment_run_id")
        if self.corpus_bound_receipt.content_ids != self.content_ids:
            raise ValueError("corpus-bound receipt content order must match content_ids")
        if len(self.content_artifact_refs) != len(self.content_ids):
            raise ValueError("verified receipt requires one artifact per content ID")
        expected_completion = f"{self.experiment_run_id}:stored-content-completion"
        if self.completion_manifest_ref.artifact_id != expected_completion:
            raise ValueError("completion manifest reference must identify this run")
        if self.verified_checks != STORED_CONTENT_VERIFIED_CHECKS:
            raise ValueError(
                "verified stored-content receipt must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class StoredContentExperimentRunner:
    """Reconstruct exact inputs from storage and delegate corpus-bound execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CorpusBoundExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        corpus_manifest: CorpusManifestSnapshot,
        windows: tuple[StoredContentExecutionWindow, ...],
        experiment_run_id: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("stored-content execution requires a frozen plan")
        if plan.corpus_ref != corpus_manifest.reference():
            raise ValueError("plan corpus_ref must match the canonical corpus manifest")
        if plan.content_ids != corpus_manifest.content_ids:
            raise ValueError("plan content order must match the canonical corpus manifest")
        if not corpus_manifest.has_content_artifacts:
            raise ValueError(
                "stored-content execution requires linked canonical content artifacts"
            )
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus_manifest.content_ids:
            raise ValueError(
                "execution windows must match the frozen content IDs exactly and in order"
            )
        if len(window_ids) < 2:
            raise ValueError("stored-content execution requires multiple content items")
        validate_candidate_eligibility(plan, candidate_registry)

    def _verify_completion(
        self,
        *,
        completion: StoredContentExperimentCompletion,
        completion_ref: StoredArtifactRef,
        corpus_manifest: CorpusManifestSnapshot,
    ) -> None:
        expected = serialize_artifact(completion.completion_id, completion)
        stored = self._store.get(
            completion_ref.artifact_id,
            expected_hash=completion_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored-content completion differs from the expected manifest"
            )
        loaded = load_canonical_corpus(self._store, corpus_manifest)
        if loaded.manifest_ref != completion.corpus_manifest_ref:
            raise ArtifactIntegrityError(
                "stored corpus manifest reference differs during final verification"
            )
        if loaded.content_refs != completion.content_artifact_refs:
            raise ArtifactIntegrityError(
                "stored content artifact references differ during final verification"
            )
        self._store.get(
            completion.corpus_bound_completion_ref.artifact_id,
            expected_hash=completion.corpus_bound_completion_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        corpus_manifest: CorpusManifestSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[StoredContentExecutionWindow, ...],
        experiment_run_id: str,
    ) -> VerifiedStoredContentExperimentReceipt:
        """Execute without receiving caller-supplied content text or metadata."""

        try:
            self._preflight(
                plan=plan,
                candidate_registry=candidate_registry,
                corpus_manifest=corpus_manifest,
                windows=windows,
                experiment_run_id=experiment_run_id,
            )
        except (CandidateEligibilityError, ValueError) as exc:
            raise StoredContentExperimentError(
                StoredContentRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            stored_corpus = load_canonical_corpus(self._store, corpus_manifest)
        except (ArtifactStoreError, CanonicalContentError, OSError, ValueError) as exc:
            raise StoredContentExperimentError(
                StoredContentRunnerStage.CONTENT_LOADING,
                str(exc),
            ) from exc

        requests = tuple(
            ContentExecutionRequest(
                content=content,
                started_at=window.started_at,
                completed_at=window.completed_at,
            )
            for content, window in zip(
                stored_corpus.contents,
                windows,
                strict=True,
            )
        )
        try:
            corpus_bound_receipt = self._runner.run(
                plan=plan,
                candidate_registry=candidate_registry,
                corpus_manifest=corpus_manifest,
                environment=environment,
                requests=requests,
                experiment_run_id=experiment_run_id,
            )
        except CorpusBoundExperimentError as exc:
            raise StoredContentExperimentError(
                StoredContentRunnerStage.EXPERIMENT_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        completion = StoredContentExperimentCompletion(
            completion_id=f"{experiment_run_id}:stored-content-completion",
            experiment_run_id=experiment_run_id,
            status=StoredContentRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            corpus_manifest_ref=stored_corpus.manifest_ref,
            corpus_bound_completion_ref=(
                corpus_bound_receipt.completion_manifest_ref
            ),
            content_ids=plan.content_ids,
            content_artifact_refs=stored_corpus.content_refs,
            verified_checks=STORED_CONTENT_VERIFIED_CHECKS,
            completed_at=corpus_bound_receipt.completed_at,
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
            raise StoredContentExperimentError(
                StoredContentRunnerStage.COMPLETION_PERSISTENCE,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        try:
            self._verify_completion(
                completion=completion,
                completion_ref=completion_ref,
                corpus_manifest=corpus_manifest,
            )
        except (
            ArtifactStoreError,
            CanonicalContentError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise StoredContentExperimentError(
                StoredContentRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        return VerifiedStoredContentExperimentReceipt(
            experiment_run_id=experiment_run_id,
            status=StoredContentRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            content_artifact_refs=stored_corpus.content_refs,
            corpus_bound_receipt=corpus_bound_receipt,
            completion_manifest_ref=completion_ref,
            verified_checks=STORED_CONTENT_VERIFIED_CHECKS,
            completed_at=completion.completed_at,
        )
