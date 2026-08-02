"""Fail-closed corpus binding around the governed multi-content runner."""

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
from ctrt.corpus_manifest import (
    CorpusBindingError,
    CorpusContentEntry,
    CorpusManifestSnapshot,
    validate_corpus_binding,
)
from ctrt.experiment_runner import (
    ContentExecutionRequest,
    MultiContentExperimentError,
    MultiContentExperimentRunner,
    VerifiedExperimentReceipt,
)
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class CorpusBoundRunnerStage(StrEnum):
    """Boundary at which corpus-bound experiment execution failed."""

    PREFLIGHT = "preflight"
    CORPUS_PERSISTENCE = "corpus-persistence"
    EXPERIMENT_EXECUTION = "experiment-execution"
    COMPLETION_PERSISTENCE = "completion-persistence"
    VERIFICATION = "verification"


class CorpusBoundRunnerStatus(StrEnum):
    """A corpus-bound receipt exists only after final re-verification."""

    VERIFIED = "verified"


class CorpusBoundExperimentError(RuntimeError):
    """Fail-closed error preserving stage and any completed content IDs."""

    def __init__(
        self,
        stage: CorpusBoundRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CORPUS_BOUND_VERIFIED_CHECKS = (
    "exact-corpus-reference",
    "content-bytes-and-metadata-bound",
    "corpus-manifest-persisted",
    "experiment-completion-reverified",
    "corpus-bound-completion-reverified",
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
class BoundContentIdentity:
    """Content identity copied from the verified frozen corpus manifest."""

    position: int
    content_id: str
    content_hash: str
    language: str
    source_type: str
    extraction_ref: str

    @classmethod
    def from_entry(cls, entry: CorpusContentEntry) -> BoundContentIdentity:
        """Preserve one manifest entry in the corpus-bound completion marker."""

        return cls(
            position=entry.position,
            content_id=entry.content_id,
            content_hash=entry.content_hash,
            language=entry.language,
            source_type=entry.source_type.value,
            extraction_ref=entry.extraction_ref,
        )

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("bound content position must be non-negative")
        if any(
            not value.strip()
            for value in (
                self.content_id,
                self.content_hash,
                self.language,
                self.source_type,
                self.extraction_ref,
            )
        ):
            raise ValueError("bound content identity fields must not be empty")


@dataclass(frozen=True, slots=True)
class CorpusBoundExperimentCompletion:
    """Final marker linking verified experiment completion to its frozen corpus."""

    completion_id: str
    experiment_run_id: str
    status: CorpusBoundRunnerStatus
    experiment_id: str
    experiment_version: str
    corpus_id: str
    corpus_version: str
    corpus_manifest_ref: StoredArtifactRef
    experiment_completion_ref: StoredArtifactRef
    contents: tuple[BoundContentIdentity, ...]
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        identity_fields = (
            self.completion_id,
            self.experiment_run_id,
            self.experiment_id,
            self.experiment_version,
            self.corpus_id,
            self.corpus_version,
        )
        if any(not value.strip() for value in identity_fields):
            raise ValueError("corpus-bound completion identity fields must not be empty")
        if self.status is not CorpusBoundRunnerStatus.VERIFIED:
            raise ValueError("corpus-bound completion status must be verified")
        expected_completion_id = f"{self.experiment_run_id}:corpus-bound-completion"
        if self.completion_id != expected_completion_id:
            raise ValueError("completion_id must derive from experiment_run_id")
        if self.corpus_manifest_ref.artifact_id != self.corpus_id:
            raise ValueError("corpus manifest reference must identify corpus_id")
        expected_experiment_completion = (
            f"{self.experiment_run_id}:experiment-completion"
        )
        if self.experiment_completion_ref.artifact_id != expected_experiment_completion:
            raise ValueError(
                "experiment completion reference must identify experiment_run_id"
            )
        if len(self.contents) < 2:
            raise ValueError("corpus-bound completion requires multiple content items")
        positions = tuple(item.position for item in self.contents)
        if positions != tuple(range(len(self.contents))):
            raise ValueError("bound content positions must be contiguous and ordered")
        content_ids = tuple(item.content_id for item in self.contents)
        if len(content_ids) != len(set(content_ids)):
            raise ValueError("bound content IDs must be unique")
        if self.verified_checks != CORPUS_BOUND_VERIFIED_CHECKS:
            raise ValueError(
                "corpus-bound completion must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCorpusBoundExperimentReceipt:
    """Proof that the exact frozen corpus and experiment completion verified."""

    experiment_run_id: str
    status: CorpusBoundRunnerStatus
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    experiment_receipt: VerifiedExperimentReceipt
    corpus_manifest_ref: StoredArtifactRef
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
            raise ValueError("verified corpus-bound identity fields must not be empty")
        if self.status is not CorpusBoundRunnerStatus.VERIFIED:
            raise ValueError("verified corpus-bound receipt status must be verified")
        if self.experiment_receipt.experiment_run_id != self.experiment_run_id:
            raise ValueError("experiment receipt must identify experiment_run_id")
        if self.experiment_receipt.experiment_id != self.experiment_id:
            raise ValueError("experiment receipt must identify experiment_id")
        if self.experiment_receipt.experiment_version != self.experiment_version:
            raise ValueError("experiment receipt must identify experiment_version")
        if self.experiment_receipt.content_ids != self.content_ids:
            raise ValueError("experiment receipt content order must match content_ids")
        expected_completion = f"{self.experiment_run_id}:corpus-bound-completion"
        if self.completion_manifest_ref.artifact_id != expected_completion:
            raise ValueError("completion manifest reference must identify this run")
        if self.verified_checks != CORPUS_BOUND_VERIFIED_CHECKS:
            raise ValueError(
                "verified corpus-bound receipt must preserve every verification check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


class CorpusBoundExperimentRunner:
    """Bind exact corpus content before delegating governed multi-content execution."""

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
        corpus_manifest: CorpusManifestSnapshot,
        requests: tuple[ContentExecutionRequest, ...],
        experiment_run_id: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("corpus-bound execution requires a frozen plan")
        if len(requests) < 2:
            raise ValueError("corpus-bound execution requires multiple content items")
        planned_dimensions = {item.dimension_id for item in plan.instrument_revisions}
        if len(planned_dimensions) != 1:
            raise ValueError("corpus-bound runner currently requires one dimension")
        validate_candidate_eligibility(plan, candidate_registry)
        validate_corpus_binding(
            plan,
            corpus_manifest,
            tuple(item.content for item in requests),
        )
        for request in requests:
            expected_ref = f"content-item:{request.content.content_id}"
            if request.content.canonical_extraction_ref != expected_ref:
                raise CorpusBindingError(
                    "current corpus binding supports only content-item extraction identities"
                )

    def _persist_corpus_manifest(
        self,
        manifest: CorpusManifestSnapshot,
    ) -> StoredArtifactRef:
        reference = self._store.append(manifest.artifact())
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != manifest.canonical_payload:
            raise ArtifactIntegrityError(
                "stored corpus manifest differs from the canonical manifest"
            )
        return reference

    def _verify_completion(
        self,
        *,
        manifest: CorpusBoundExperimentCompletion,
        manifest_ref: StoredArtifactRef,
        corpus_manifest: CorpusManifestSnapshot,
    ) -> None:
        expected = serialize_artifact(manifest.completion_id, manifest)
        stored = self._store.get(
            manifest_ref.artifact_id,
            expected_hash=manifest_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored corpus-bound completion differs from the expected manifest"
            )
        stored_corpus = self._store.get(
            manifest.corpus_manifest_ref.artifact_id,
            expected_hash=manifest.corpus_manifest_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus_manifest.canonical_payload:
            raise ArtifactIntegrityError(
                "stored corpus manifest differs during final verification"
            )
        self._store.get(
            manifest.experiment_completion_ref.artifact_id,
            expected_hash=manifest.experiment_completion_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        corpus_manifest: CorpusManifestSnapshot,
        environment: ExecutionEnvironment,
        requests: tuple[ContentExecutionRequest, ...],
        experiment_run_id: str,
    ) -> VerifiedCorpusBoundExperimentReceipt:
        """Return only after corpus and experiment completion artifacts re-verify."""

        try:
            self._preflight(
                plan=plan,
                candidate_registry=candidate_registry,
                corpus_manifest=corpus_manifest,
                requests=requests,
                experiment_run_id=experiment_run_id,
            )
        except (CandidateEligibilityError, CorpusBindingError, ValueError) as exc:
            raise CorpusBoundExperimentError(
                CorpusBoundRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            corpus_manifest_ref = self._persist_corpus_manifest(corpus_manifest)
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise CorpusBoundExperimentError(
                CorpusBoundRunnerStage.CORPUS_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            experiment_receipt = self._runner.run(
                plan=plan,
                candidate_registry=candidate_registry,
                environment=environment,
                requests=requests,
                experiment_run_id=experiment_run_id,
            )
        except MultiContentExperimentError as exc:
            raise CorpusBoundExperimentError(
                CorpusBoundRunnerStage.EXPERIMENT_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        contents = tuple(
            BoundContentIdentity.from_entry(entry)
            for entry in corpus_manifest.contents
        )
        completion = CorpusBoundExperimentCompletion(
            completion_id=f"{experiment_run_id}:corpus-bound-completion",
            experiment_run_id=experiment_run_id,
            status=CorpusBoundRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            corpus_id=corpus_manifest.corpus_id,
            corpus_version=corpus_manifest.corpus_version,
            corpus_manifest_ref=corpus_manifest_ref,
            experiment_completion_ref=(
                experiment_receipt.completion_manifest_ref
            ),
            contents=contents,
            verified_checks=CORPUS_BOUND_VERIFIED_CHECKS,
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
            raise CorpusBoundExperimentError(
                CorpusBoundRunnerStage.COMPLETION_PERSISTENCE,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        try:
            self._verify_completion(
                manifest=completion,
                manifest_ref=completion_ref,
                corpus_manifest=corpus_manifest,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CorpusBoundExperimentError(
                CorpusBoundRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        return VerifiedCorpusBoundExperimentReceipt(
            experiment_run_id=experiment_run_id,
            status=CorpusBoundRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            experiment_receipt=experiment_receipt,
            corpus_manifest_ref=corpus_manifest_ref,
            completion_manifest_ref=completion_ref,
            verified_checks=CORPUS_BOUND_VERIFIED_CHECKS,
            completed_at=completion.completed_at,
        )
