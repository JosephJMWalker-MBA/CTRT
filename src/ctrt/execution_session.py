"""Fail-closed orchestration for governed CTRT experiment execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_pipeline import serialize_experiment_run
from ctrt.artifact_store import (
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
    persist_experiment_bundle,
    verify_experiment_bundle,
)
from ctrt.candidate_eligibility import (
    CandidateEligibilityError,
    CandidateEligibilityReport,
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.contracts import ContentItem, ResultStatus
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan
from ctrt.serialization import CanonicalSerializationError, canonical_sha256
from ctrt.workbench import AnalyzerRegistry, ContentAnalysisWorkbench, WorkbenchReportStatus


class ExecutionSessionStage(StrEnum):
    """Boundary at which a governed execution session failed."""

    PREFLIGHT = "preflight"
    EXECUTION = "execution"
    SERIALIZATION = "serialization"
    PERSISTENCE = "persistence"
    VERIFICATION = "verification"


class ExecutionSessionStatus(StrEnum):
    """A session returns a receipt only after complete bundle verification."""

    VERIFIED = "verified"


class GovernedExecutionError(RuntimeError):
    """Fail-closed session error preserving the stage that did not complete."""

    def __init__(self, stage: ExecutionSessionStage, message: str) -> None:
        self.stage = stage
        super().__init__(f"{stage.value} failed: {message}")


VERIFIED_CHECKS = (
    "candidate-eligibility",
    "runtime-revision",
    "canonical-serialization",
    "artifact-persistence",
    "manifest-reverification",
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
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must contain a lowercase 64-character SHA-256 digest")


@dataclass(frozen=True, slots=True)
class VerifiedExecutionReceipt:
    """Proof that a governed run completed and its stored bundle re-verified."""

    session_id: str
    status: ExecutionSessionStatus
    experiment_id: str
    experiment_version: str
    run_id: str
    run_record_id: str
    content_id: str
    analyzer_ids: tuple[str, ...]
    result_statuses: tuple[ResultStatus, ...]
    workbench_status: WorkbenchReportStatus
    bundle_id: str
    manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        identity_fields = (
            self.session_id,
            self.experiment_id,
            self.experiment_version,
            self.run_id,
            self.run_record_id,
            self.content_id,
            self.bundle_id,
        )
        if any(not value.strip() for value in identity_fields):
            raise ValueError("verified receipt identity fields must not be empty")
        if self.status is not ExecutionSessionStatus.VERIFIED:
            raise ValueError("execution receipt status must be verified")
        if len(self.analyzer_ids) < 2:
            raise ValueError("verified receipt requires at least two analyzers")
        if len(self.analyzer_ids) != len(set(self.analyzer_ids)):
            raise ValueError("verified receipt analyzer IDs must be unique")
        if len(self.result_statuses) != len(self.analyzer_ids):
            raise ValueError("verified receipt requires one result status per analyzer")
        if self.run_record_id != f"{self.run_id}:record":
            raise ValueError("verified receipt run_record_id must derive from run_id")
        if self.bundle_id != f"{self.run_record_id}:artifact-bundle":
            raise ValueError("verified receipt bundle_id must derive from run_record_id")
        if self.manifest_ref.artifact_id != self.bundle_id:
            raise ValueError("verified receipt manifest reference must identify the bundle")
        if self.verified_checks != VERIFIED_CHECKS:
            raise ValueError("verified receipt must preserve every required verification check")
        started = _parse_timestamp(self.started_at, "started_at")
        completed = _parse_timestamp(self.completed_at, "completed_at")
        if completed < started:
            raise ValueError("completed_at may not precede started_at")


class GovernedExecutionSession:
    """Authorize, execute, serialize, persist, and re-verify one frozen plan run."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._registry = analyzer_registry
        self._workbench = ContentAnalysisWorkbench(analyzer_registry)
        self._store = artifact_store

    def _preflight(
        self,
        *,
        plan: ExperimentPlan,
        registry: CandidateRegistrySnapshot,
        content: ContentItem,
        run_id: str,
    ) -> tuple[CandidateEligibilityReport, tuple[str, ...]]:
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        _require_sha256(content.content_hash, "content_hash")
        if content.content_id not in plan.content_ids:
            raise ValueError("content item is not authorized by the frozen experiment plan")

        eligibility = validate_candidate_eligibility(plan, registry)
        analyzer_ids = tuple(item.analyzer_id for item in plan.instrument_revisions)
        if eligibility.authorized_analyzer_ids != analyzer_ids:
            raise ValueError("eligibility report analyzer order must match the frozen plan")

        planned_dimensions = {item.dimension_id for item in plan.instrument_revisions}
        if len(planned_dimensions) != 1:
            raise ValueError("one governed workbench session requires exactly one dimension")

        for instrument in plan.instrument_revisions:
            analyzer = self._registry.get(instrument.analyzer_id)
            if analyzer.identity.analyzer_id != instrument.analyzer_id:
                raise ValueError("loaded analyzer identity differs from the frozen plan")
            if analyzer.dimension_id != instrument.dimension_id:
                raise ValueError("loaded analyzer dimension differs from the frozen plan")
            if analyzer.implementation_revision != instrument.implementation_revision:
                raise ValueError("loaded implementation revision differs from the frozen plan")
            if analyzer.identity.adapter_version != instrument.adapter_version:
                raise ValueError("loaded adapter version differs from the frozen plan")
            configuration_hash = canonical_sha256(analyzer.execution_configuration)
            if configuration_hash != instrument.configuration_hash:
                raise ValueError("loaded execution configuration differs from the frozen plan")

        return eligibility, analyzer_ids

    def execute(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        environment: ExecutionEnvironment,
        content: ContentItem,
        run_id: str,
        started_at: str,
        completed_at: str,
    ) -> VerifiedExecutionReceipt:
        """Return a receipt only after the stored canonical bundle fully re-verifies."""

        try:
            eligibility, analyzer_ids = self._preflight(
                plan=plan,
                registry=candidate_registry,
                content=content,
                run_id=run_id,
            )
        except (CandidateEligibilityError, KeyError, ValueError) as exc:
            raise GovernedExecutionError(
                ExecutionSessionStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            run = self._workbench.run_content_item(
                run_id=run_id,
                content=content,
                analyzer_ids=analyzer_ids,
            )
        except Exception as exc:
            raise GovernedExecutionError(
                ExecutionSessionStage.EXECUTION,
                str(exc),
            ) from exc

        try:
            bundle = serialize_experiment_run(
                plan=plan,
                eligibility=eligibility,
                environment=environment,
                run=run,
                started_at=started_at,
                completed_at=completed_at,
            )
        except (CanonicalSerializationError, ValueError) as exc:
            raise GovernedExecutionError(
                ExecutionSessionStage.SERIALIZATION,
                str(exc),
            ) from exc

        try:
            stored = persist_experiment_bundle(self._store, bundle)
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise GovernedExecutionError(
                ExecutionSessionStage.PERSISTENCE,
                str(exc),
            ) from exc

        try:
            verify_experiment_bundle(self._store, stored)
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise GovernedExecutionError(
                ExecutionSessionStage.VERIFICATION,
                str(exc),
            ) from exc

        return VerifiedExecutionReceipt(
            session_id=f"{run_id}:governed-session",
            status=ExecutionSessionStatus.VERIFIED,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            run_id=run.run_id,
            run_record_id=bundle.run_record.record_id,
            content_id=run.content_id,
            analyzer_ids=run.analyzer_ids,
            result_statuses=tuple(result.status for result in run.results),
            workbench_status=run.comparison.status,
            bundle_id=stored.manifest.bundle_id,
            manifest_ref=stored.manifest_ref,
            verified_checks=VERIFIED_CHECKS,
            started_at=started_at,
            completed_at=completed_at,
        )
