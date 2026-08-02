"""Fail-closed orchestration across every content item in a frozen experiment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
    load_experiment_bundle,
)
from ctrt.candidate_eligibility import (
    CandidateEligibilityError,
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.contracts import ContentItem, ResultStatus
from ctrt.execution_session import (
    ExecutionSessionStatus,
    GovernedExecutionError,
    GovernedExecutionSession,
    VerifiedExecutionReceipt,
)
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.serialization import (
    CanonicalSerializationError,
    canonical_sha256,
    serialize_artifact,
)
from ctrt.workbench import AnalyzerRegistry, WorkbenchReportStatus


class ExperimentRunnerStage(StrEnum):
    """Boundary at which a multi-content experiment run failed."""

    PREFLIGHT = "preflight"
    SESSION_EXECUTION = "session-execution"
    RECEIPT_PERSISTENCE = "receipt-persistence"
    COMPLETION_PERSISTENCE = "completion-persistence"
    VERIFICATION = "verification"


class ExperimentRunnerStatus(StrEnum):
    """A multi-content runner returns only after full verification."""

    VERIFIED = "verified"


class MultiContentExperimentError(RuntimeError):
    """Fail-closed error preserving the failed stage and prior verified content."""

    def __init__(
        self,
        stage: ExperimentRunnerStage,
        message: str,
        *,
        content_id: str | None = None,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.content_id = content_id
        self.completed_content_ids = completed_content_ids
        location = f" for {content_id}" if content_id is not None else ""
        super().__init__(f"{stage.value}{location} failed: {message}")


EXPERIMENT_VERIFIED_CHECKS = (
    "exact-content-scope",
    "all-session-receipts-persisted",
    "all-session-bundles-reverified",
    "completion-manifest-persisted",
    "completion-manifest-reverified",
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


def _require_sha256(value: str, field_name: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError(f"{field_name} must use a sha256: prefix")
    digest = value[len(prefix) :]
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(
            f"{field_name} must contain a lowercase 64-character SHA-256 digest"
        )


def _run_id(experiment_run_id: str, position: int, content_id: str) -> str:
    return f"{experiment_run_id}:{position:04d}:{content_id}"


@dataclass(frozen=True, slots=True)
class ContentExecutionRequest:
    """One authorized content item and its externally recorded execution window."""

    content: ContentItem
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        started = _parse_timestamp(self.started_at, "started_at")
        completed = _parse_timestamp(self.completed_at, "completed_at")
        if completed < started:
            raise ValueError("completed_at may not precede started_at")


@dataclass(frozen=True, slots=True)
class ExperimentSessionCompletion:
    """Role-bound references proving one content session completed and was stored."""

    position: int
    content_id: str
    run_id: str
    session_id: str
    receipt_ref: StoredArtifactRef
    bundle_manifest_ref: StoredArtifactRef
    result_statuses: tuple[ResultStatus, ...]
    workbench_status: WorkbenchReportStatus

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("session completion position must be non-negative")
        if any(
            not value.strip()
            for value in (
                self.content_id,
                self.run_id,
                self.session_id,
            )
        ):
            raise ValueError("session completion identity fields must not be empty")
        if self.session_id != f"{self.run_id}:governed-session":
            raise ValueError("session_id must derive from run_id")
        if self.receipt_ref.artifact_id != f"{self.session_id}:receipt":
            raise ValueError("receipt reference must derive from session_id")
        expected_bundle = f"{self.run_id}:record:artifact-bundle"
        if self.bundle_manifest_ref.artifact_id != expected_bundle:
            raise ValueError("bundle manifest reference must derive from run_id")
        if len(self.result_statuses) < 2:
            raise ValueError("session completion requires at least two result statuses")


@dataclass(frozen=True, slots=True)
class ExperimentCompletionManifest:
    """Completion marker written only after every declared session verifies."""

    completion_id: str
    experiment_run_id: str
    status: ExperimentRunnerStatus
    experiment_id: str
    experiment_version: str
    plan_ref: StoredArtifactRef
    content_ids: tuple[str, ...]
    sessions: tuple[ExperimentSessionCompletion, ...]
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
            raise ValueError("experiment completion identity fields must not be empty")
        if self.status is not ExperimentRunnerStatus.VERIFIED:
            raise ValueError("experiment completion status must be verified")
        if self.completion_id != f"{self.experiment_run_id}:experiment-completion":
            raise ValueError("completion_id must derive from experiment_run_id")
        if self.plan_ref.artifact_id != self.experiment_id:
            raise ValueError("plan reference must identify the experiment")
        if len(self.content_ids) < 2:
            raise ValueError("multi-content completion requires at least two content IDs")
        if len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("completion content IDs must be unique")
        if len(self.sessions) != len(self.content_ids):
            raise ValueError("completion requires one session per content ID")
        if tuple(item.position for item in self.sessions) != tuple(
            range(len(self.sessions))
        ):
            raise ValueError("completion session positions must be contiguous and ordered")
        if tuple(item.content_id for item in self.sessions) != self.content_ids:
            raise ValueError("completion session order must match content_ids")
        for item in self.sessions:
            expected_run_id = _run_id(
                self.experiment_run_id,
                item.position,
                item.content_id,
            )
            if item.run_id != expected_run_id:
                raise ValueError("session run_id must derive from experiment content order")
        if self.verified_checks != EXPERIMENT_VERIFIED_CHECKS:
            raise ValueError("completion manifest must preserve every verification check")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedExperimentReceipt:
    """Proof that every declared content session and the completion manifest verified."""

    experiment_run_id: str
    status: ExperimentRunnerStatus
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    session_receipts: tuple[VerifiedExecutionReceipt, ...]
    session_receipt_refs: tuple[StoredArtifactRef, ...]
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
            raise ValueError("verified experiment identity fields must not be empty")
        if self.status is not ExperimentRunnerStatus.VERIFIED:
            raise ValueError("verified experiment receipt status must be verified")
        if len(self.content_ids) < 2:
            raise ValueError("verified experiment requires multiple content items")
        if len(self.session_receipts) != len(self.content_ids):
            raise ValueError("verified experiment requires one receipt per content item")
        if len(self.session_receipt_refs) != len(self.session_receipts):
            raise ValueError("every session receipt must have one stored reference")
        if tuple(item.content_id for item in self.session_receipts) != self.content_ids:
            raise ValueError("session receipt order must match the frozen content order")
        for receipt, reference in zip(
            self.session_receipts,
            self.session_receipt_refs,
            strict=True,
        ):
            if receipt.status is not ExecutionSessionStatus.VERIFIED:
                raise ValueError("every session receipt must be verified")
            if reference.artifact_id != f"{receipt.session_id}:receipt":
                raise ValueError("stored receipt reference must identify the session receipt")
        expected_completion = f"{self.experiment_run_id}:experiment-completion"
        if self.completion_manifest_ref.artifact_id != expected_completion:
            raise ValueError("completion manifest reference must identify this experiment run")
        if self.verified_checks != EXPERIMENT_VERIFIED_CHECKS:
            raise ValueError("verified experiment must preserve every verification check")
        _parse_timestamp(self.completed_at, "completed_at")


class MultiContentExperimentRunner:
    """Execute one governed session for every content item in a frozen plan."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._session = GovernedExecutionSession(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        requests: tuple[ContentExecutionRequest, ...],
        experiment_run_id: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("multi-content execution requires a frozen plan")
        if len(requests) < 2:
            raise ValueError("multi-content execution requires at least two requests")
        request_content_ids = tuple(item.content.content_id for item in requests)
        if request_content_ids != plan.content_ids:
            raise ValueError(
                "execution requests must match the frozen content IDs exactly and in order"
            )
        if len(request_content_ids) != len(set(request_content_ids)):
            raise ValueError("execution request content IDs must be unique")
        planned_dimensions = {item.dimension_id for item in plan.instrument_revisions}
        if len(planned_dimensions) != 1:
            raise ValueError("multi-content runner currently requires exactly one dimension")
        for request in requests:
            _require_sha256(request.content.content_hash, "content_hash")
        validate_candidate_eligibility(plan, candidate_registry)

    def _persist_receipt(
        self,
        receipt: VerifiedExecutionReceipt,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{receipt.session_id}:receipt",
            receipt,
        )
        reference = self._store.append(artifact)
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored session receipt differs from the verified receipt"
            )
        return reference

    def _verify_receipt(
        self,
        receipt: VerifiedExecutionReceipt,
        reference: StoredArtifactRef,
    ) -> None:
        expected = serialize_artifact(reference.artifact_id, receipt)
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored session receipt differs from the expected canonical receipt"
            )

    def _verify_completion(
        self,
        *,
        manifest: ExperimentCompletionManifest,
        manifest_ref: StoredArtifactRef,
        receipts: tuple[VerifiedExecutionReceipt, ...],
        receipt_refs: tuple[StoredArtifactRef, ...],
    ) -> None:
        expected_manifest = serialize_artifact(manifest.completion_id, manifest)
        stored_manifest = self._store.get(
            manifest_ref.artifact_id,
            expected_hash=manifest_ref.artifact_hash,
        )
        if stored_manifest.payload != expected_manifest.payload:
            raise ArtifactIntegrityError(
                "stored experiment completion manifest differs from the expected manifest"
            )
        self._store.get(
            manifest.plan_ref.artifact_id,
            expected_hash=manifest.plan_ref.artifact_hash,
        )
        for completion, receipt, receipt_ref in zip(
            manifest.sessions,
            receipts,
            receipt_refs,
            strict=True,
        ):
            self._verify_receipt(receipt, receipt_ref)
            load_experiment_bundle(
                self._store,
                completion.bundle_manifest_ref,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        environment: ExecutionEnvironment,
        requests: tuple[ContentExecutionRequest, ...],
        experiment_run_id: str,
    ) -> VerifiedExperimentReceipt:
        """Return only after all sessions and the completion manifest re-verify."""

        try:
            self._preflight(
                plan=plan,
                candidate_registry=candidate_registry,
                requests=requests,
                experiment_run_id=experiment_run_id,
            )
        except (CandidateEligibilityError, ValueError) as exc:
            raise MultiContentExperimentError(
                ExperimentRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        receipts: list[VerifiedExecutionReceipt] = []
        receipt_refs: list[StoredArtifactRef] = []
        for position, request in enumerate(requests):
            content_id = request.content.content_id
            run_id = _run_id(experiment_run_id, position, content_id)
            try:
                receipt = self._session.execute(
                    plan=plan,
                    candidate_registry=candidate_registry,
                    environment=environment,
                    content=request.content,
                    run_id=run_id,
                    started_at=request.started_at,
                    completed_at=request.completed_at,
                )
            except GovernedExecutionError as exc:
                raise MultiContentExperimentError(
                    ExperimentRunnerStage.SESSION_EXECUTION,
                    str(exc),
                    content_id=content_id,
                    completed_content_ids=tuple(
                        item.content_id for item in receipts
                    ),
                ) from exc

            try:
                receipt_ref = self._persist_receipt(receipt)
            except (
                ArtifactStoreError,
                CanonicalSerializationError,
                OSError,
                ValueError,
            ) as exc:
                raise MultiContentExperimentError(
                    ExperimentRunnerStage.RECEIPT_PERSISTENCE,
                    str(exc),
                    content_id=content_id,
                    completed_content_ids=tuple(
                        item.content_id for item in receipts
                    ),
                ) from exc
            receipts.append(receipt)
            receipt_refs.append(receipt_ref)

        receipt_tuple = tuple(receipts)
        receipt_ref_tuple = tuple(receipt_refs)
        try:
            plan_hash = canonical_sha256(plan)
            plan_ref = self._store.reference(plan.experiment_id)
            if plan_ref.artifact_hash != plan_hash:
                raise ArtifactIntegrityError(
                    "stored plan hash differs from the frozen experiment plan"
                )
            sessions = tuple(
                ExperimentSessionCompletion(
                    position=position,
                    content_id=receipt.content_id,
                    run_id=receipt.run_id,
                    session_id=receipt.session_id,
                    receipt_ref=receipt_ref,
                    bundle_manifest_ref=receipt.manifest_ref,
                    result_statuses=receipt.result_statuses,
                    workbench_status=receipt.workbench_status,
                )
                for position, (receipt, receipt_ref) in enumerate(
                    zip(receipt_tuple, receipt_ref_tuple, strict=True)
                )
            )
            for completion, receipt, receipt_ref in zip(
                sessions,
                receipt_tuple,
                receipt_ref_tuple,
                strict=True,
            ):
                self._verify_receipt(receipt, receipt_ref)
                load_experiment_bundle(
                    self._store,
                    completion.bundle_manifest_ref,
                )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise MultiContentExperimentError(
                ExperimentRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=tuple(item.content_id for item in receipts),
            ) from exc

        completed_request = max(
            requests,
            key=lambda item: _parse_timestamp(item.completed_at, "completed_at"),
        )
        manifest = ExperimentCompletionManifest(
            completion_id=f"{experiment_run_id}:experiment-completion",
            experiment_run_id=experiment_run_id,
            status=ExperimentRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            plan_ref=plan_ref,
            content_ids=plan.content_ids,
            sessions=sessions,
            verified_checks=EXPERIMENT_VERIFIED_CHECKS,
            completed_at=completed_request.completed_at,
        )
        try:
            manifest_artifact = serialize_artifact(manifest.completion_id, manifest)
            manifest_ref = self._store.append(manifest_artifact)
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise MultiContentExperimentError(
                ExperimentRunnerStage.COMPLETION_PERSISTENCE,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        try:
            self._verify_completion(
                manifest=manifest,
                manifest_ref=manifest_ref,
                receipts=receipt_tuple,
                receipt_refs=receipt_ref_tuple,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise MultiContentExperimentError(
                ExperimentRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=plan.content_ids,
            ) from exc

        return VerifiedExperimentReceipt(
            experiment_run_id=experiment_run_id,
            status=ExperimentRunnerStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            session_receipts=receipt_tuple,
            session_receipt_refs=receipt_ref_tuple,
            completion_manifest_ref=manifest_ref,
            verified_checks=EXPERIMENT_VERIFIED_CHECKS,
            completed_at=manifest.completed_at,
        )
