"""Versioned experiment plans and append-only execution records for CTRT Phase 1A."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.contracts import ResultStatus
from ctrt.workbench import WorkbenchReportStatus, WorkbenchRun


class ExperimentPlanStatus(StrEnum):
    """Lifecycle state for an immutable experiment plan version."""

    DRAFT = "draft"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"


class ExperimentRunStatus(StrEnum):
    """Preserved outcome of one governed experiment execution."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    FAILED = "failed"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} entries must not be empty")


def _require_sha256(value: str, field_name: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError(f"{field_name} must use a sha256: prefix")
    digest = value[len(prefix) :]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must contain a lowercase 64-character SHA-256 digest")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    _require_non_empty(value, field_name)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


@dataclass(frozen=True, slots=True)
class VersionedArtifactRef:
    """Immutable reference to a versioned machine-readable research artifact."""

    artifact_id: str
    artifact_version: str
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.artifact_id, "artifact_id")
        _require_non_empty(self.artifact_version, "artifact_version")
        _require_sha256(self.artifact_hash, "artifact_hash")


@dataclass(frozen=True, slots=True)
class InstrumentRevision:
    """Exact candidate, analyzer, dimension, adapter, configuration, and revision."""

    candidate_id: str
    analyzer_id: str
    dimension_id: str
    implementation_revision: str
    adapter_version: str
    configuration_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.candidate_id, "candidate_id")
        _require_non_empty(self.analyzer_id, "analyzer_id")
        _require_non_empty(self.dimension_id, "dimension_id")
        _require_non_empty(self.implementation_revision, "implementation_revision")
        _require_non_empty(self.adapter_version, "adapter_version")
        _require_sha256(self.configuration_hash, "configuration_hash")


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """Versioned evaluation metric selected before experiment execution."""

    metric_id: str
    metric_version: str

    def __post_init__(self) -> None:
        _require_non_empty(self.metric_id, "metric_id")
        _require_non_empty(self.metric_version, "metric_version")
        if self.metric_id in {"scalar-confidence", "overall-confidence"}:
            raise ValueError("experiment metrics may not introduce scalar confidence")


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    """Versioned environment identity required to interpret and reproduce a run."""

    environment_id: str
    environment_version: str
    python_version: str
    operating_system: str
    architecture: str
    dependency_lock_hash: str
    runtime_configuration_hash: str
    hardware_profile: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("environment_id", self.environment_id),
            ("environment_version", self.environment_version),
            ("python_version", self.python_version),
            ("operating_system", self.operating_system),
            ("architecture", self.architecture),
            ("hardware_profile", self.hardware_profile),
        ):
            _require_non_empty(value, field_name)
        _require_sha256(self.dependency_lock_hash, "dependency_lock_hash")
        _require_sha256(self.runtime_configuration_hash, "runtime_configuration_hash")


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    """Frozen protocol-bound authorization for a declared set of executions."""

    experiment_id: str
    experiment_version: str
    status: ExperimentPlanStatus
    research_question: str
    protocol_ref: VersionedArtifactRef
    candidate_registry_ref: VersionedArtifactRef
    corpus_ref: VersionedArtifactRef
    content_ids: tuple[str, ...]
    dimension_ids: tuple[str, ...]
    instrument_revisions: tuple[InstrumentRevision, ...]
    metrics: tuple[MetricDefinition, ...]
    exclusion_rules: tuple[str, ...]
    stopping_rules: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.experiment_version, "experiment_version")
        _require_non_empty(self.research_question, "research_question")
        _require_unique(self.content_ids, "content_ids")
        _require_unique(self.dimension_ids, "dimension_ids")
        _require_unique(self.exclusion_rules, "exclusion_rules")
        _require_unique(self.stopping_rules, "stopping_rules")
        _parse_timestamp(self.created_at, "created_at")

        analyzer_ids = tuple(item.analyzer_id for item in self.instrument_revisions)
        _require_unique(analyzer_ids, "instrument analyzer_ids")
        instrument_keys = tuple(
            f"{item.candidate_id}@{item.analyzer_id}@{item.dimension_id}"
            for item in self.instrument_revisions
        )
        _require_unique(instrument_keys, "instrument revisions")
        metric_ids = tuple(f"{item.metric_id}@{item.metric_version}" for item in self.metrics)
        _require_unique(metric_ids, "metrics")
        undeclared_dimensions = {
            item.dimension_id for item in self.instrument_revisions
        } - set(self.dimension_ids)
        if undeclared_dimensions:
            raise ValueError("instrument dimensions must be declared by the experiment plan")

        if self.status is ExperimentPlanStatus.FROZEN:
            if len(self.instrument_revisions) < 2:
                raise ValueError("frozen experiment requires at least two instrument revisions")
            if not self.content_ids or not self.dimension_ids:
                raise ValueError("frozen experiment requires content and dimensions")
            if not self.metrics:
                raise ValueError("frozen experiment requires at least one declared metric")
            if not self.stopping_rules:
                raise ValueError("frozen experiment requires at least one stopping rule")


@dataclass(frozen=True, slots=True)
class ResultArtifactRef:
    """Append-only reference to one serialized immutable analyzer result."""

    result_id: str
    analyzer_id: str
    content_id: str
    status: ResultStatus
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.result_id, "result_id")
        _require_non_empty(self.analyzer_id, "analyzer_id")
        _require_non_empty(self.content_id, "content_id")
        _require_sha256(self.artifact_hash, "result artifact_hash")


@dataclass(frozen=True, slots=True)
class ComparisonArtifactRef:
    """Append-only reference to the serialized comparison assembled from results."""

    comparison_id: str
    content_id: str
    status: WorkbenchReportStatus
    result_ids: tuple[str, ...]
    artifact_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.comparison_id, "comparison_id")
        _require_non_empty(self.content_id, "content_id")
        _require_unique(self.result_ids, "comparison result_ids")
        if len(self.result_ids) < 2:
            raise ValueError("comparison artifact requires at least two results")
        _require_sha256(self.artifact_hash, "comparison artifact_hash")


@dataclass(frozen=True, slots=True)
class ExperimentRunRecord:
    """Immutable execution record linked to frozen plan, eligibility, and artifacts."""

    record_id: str
    experiment_plan_ref: VersionedArtifactRef
    candidate_eligibility_ref: VersionedArtifactRef
    workbench_run_id: str
    status: ExperimentRunStatus
    environment: ExecutionEnvironment
    content_id: str
    instrument_revisions: tuple[InstrumentRevision, ...]
    result_artifacts: tuple[ResultArtifactRef, ...]
    comparison_artifact: ComparisonArtifactRef
    started_at: str
    completed_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.record_id, "record_id")
        _require_non_empty(self.workbench_run_id, "workbench_run_id")
        _require_non_empty(self.content_id, "content_id")
        started = _parse_timestamp(self.started_at, "started_at")
        completed = _parse_timestamp(self.completed_at, "completed_at")
        if completed < started:
            raise ValueError("completed_at may not precede started_at")

        expected_eligibility_id = (
            f"{self.experiment_plan_ref.artifact_id}:candidate-eligibility"
        )
        if self.candidate_eligibility_ref.artifact_id != expected_eligibility_id:
            raise ValueError("candidate eligibility artifact_id must identify the experiment plan")
        if (
            self.candidate_eligibility_ref.artifact_version
            != self.experiment_plan_ref.artifact_version
        ):
            raise ValueError("candidate eligibility version must match the experiment plan")

        analyzer_ids = tuple(item.analyzer_id for item in self.instrument_revisions)
        result_analyzer_ids = tuple(item.analyzer_id for item in self.result_artifacts)
        if analyzer_ids != result_analyzer_ids:
            raise ValueError("result artifacts must follow the frozen instrument order")
        if any(item.content_id != self.content_id for item in self.result_artifacts):
            raise ValueError("result artifacts must reference the run content")
        if self.comparison_artifact.content_id != self.content_id:
            raise ValueError("comparison artifact must reference the run content")
        result_ids = tuple(item.result_id for item in self.result_artifacts)
        if self.comparison_artifact.result_ids != result_ids:
            raise ValueError("comparison artifact must reference every result in order")

        expected_status = ExperimentRunStatus(self.comparison_artifact.status.value)
        if self.status is not expected_status:
            raise ValueError("experiment run status must preserve the comparison status")


def record_workbench_run(
    *,
    plan: ExperimentPlan,
    plan_ref: VersionedArtifactRef,
    candidate_eligibility_ref: VersionedArtifactRef,
    environment: ExecutionEnvironment,
    run: WorkbenchRun,
    result_hashes: Mapping[str, str],
    comparison_hash: str,
    started_at: str,
    completed_at: str,
) -> ExperimentRunRecord:
    """Create a run record after eligibility and artifact serialization complete."""

    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise ValueError("only a frozen experiment plan may authorize execution")
    if (
        plan_ref.artifact_id != plan.experiment_id
        or plan_ref.artifact_version != plan.experiment_version
    ):
        raise ValueError("experiment plan reference must identify the frozen plan")
    expected_eligibility_id = f"{plan.experiment_id}:candidate-eligibility"
    if (
        candidate_eligibility_ref.artifact_id != expected_eligibility_id
        or candidate_eligibility_ref.artifact_version != plan.experiment_version
    ):
        raise ValueError("candidate eligibility reference must identify this plan version")
    if run.content_id not in plan.content_ids:
        raise ValueError("workbench run content is not authorized by the experiment plan")

    planned_analyzer_ids = tuple(item.analyzer_id for item in plan.instrument_revisions)
    if run.analyzer_ids != planned_analyzer_ids:
        raise ValueError("workbench analyzer order must match the frozen experiment plan")
    planned_dimensions = {item.dimension_id for item in plan.instrument_revisions}
    if run.comparison.dimension_id not in planned_dimensions:
        raise ValueError("workbench comparison dimension is not authorized by the plan")

    result_ids = tuple(result.result_id for result in run.results)
    if set(result_hashes) != set(result_ids):
        raise ValueError("result hashes must cover exactly the preserved analyzer results")
    result_artifacts = tuple(
        ResultArtifactRef(
            result_id=result.result_id,
            analyzer_id=result.analyzer.analyzer_id,
            content_id=result.content_id,
            status=result.status,
            artifact_hash=result_hashes[result.result_id],
        )
        for result in run.results
    )
    comparison_artifact = ComparisonArtifactRef(
        comparison_id=run.comparison.comparison_id,
        content_id=run.comparison.content_id,
        status=run.comparison.status,
        result_ids=result_ids,
        artifact_hash=comparison_hash,
    )
    return ExperimentRunRecord(
        record_id=f"{run.run_id}:record",
        experiment_plan_ref=plan_ref,
        candidate_eligibility_ref=candidate_eligibility_ref,
        workbench_run_id=run.run_id,
        status=ExperimentRunStatus(run.comparison.status.value),
        environment=environment,
        content_id=run.content_id,
        instrument_revisions=plan.instrument_revisions,
        result_artifacts=result_artifacts,
        comparison_artifact=comparison_artifact,
        started_at=started_at,
        completed_at=completed_at,
    )


class InMemoryExperimentLedger:
    """Small append-only ledger proving plan and run immutability before persistence."""

    def __init__(self) -> None:
        self._plans: dict[tuple[str, str], tuple[VersionedArtifactRef, ExperimentPlan]] = {}
        self._runs: dict[str, ExperimentRunRecord] = {}
        self._workbench_run_ids: set[str] = set()

    def append_plan(self, reference: VersionedArtifactRef, plan: ExperimentPlan) -> None:
        """Append one immutable plan version; replacement is prohibited."""

        if reference.artifact_id != plan.experiment_id:
            raise ValueError("plan reference artifact_id must match experiment_id")
        if reference.artifact_version != plan.experiment_version:
            raise ValueError("plan reference version must match experiment_version")
        key = (plan.experiment_id, plan.experiment_version)
        if key in self._plans:
            raise ValueError("experiment plan version is append-only and already exists")
        self._plans[key] = (reference, plan)

    def append_run(self, record: ExperimentRunRecord) -> None:
        """Append one run record without rewriting prior results or comparisons."""

        key = (
            record.experiment_plan_ref.artifact_id,
            record.experiment_plan_ref.artifact_version,
        )
        stored = self._plans.get(key)
        if stored is None or stored[0] != record.experiment_plan_ref:
            raise ValueError("run record must reference an appended experiment plan artifact")
        if record.record_id in self._runs:
            raise ValueError("experiment run record is append-only and already exists")
        if record.workbench_run_id in self._workbench_run_ids:
            raise ValueError("workbench run already has an appended experiment record")
        self._runs[record.record_id] = record
        self._workbench_run_ids.add(record.workbench_run_id)

    def plans(self) -> tuple[ExperimentPlan, ...]:
        """Return appended plan versions in insertion order."""

        return tuple(plan for _, plan in self._plans.values())

    def runs(self) -> tuple[ExperimentRunRecord, ...]:
        """Return appended run records in insertion order."""

        return tuple(self._runs.values())
