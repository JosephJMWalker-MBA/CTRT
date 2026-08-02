"""End-to-end canonical serialization for governed workbench executions."""

from __future__ import annotations

from dataclasses import dataclass

from ctrt.candidate_eligibility import CandidateEligibilityReport
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentRunRecord,
    VersionedArtifactRef,
    record_workbench_run,
)
from ctrt.serialization import CanonicalArtifact, serialize_artifact
from ctrt.workbench import WorkbenchRun


@dataclass(frozen=True, slots=True)
class ExperimentArtifactBundle:
    """Canonical artifacts produced for one governed workbench run."""

    plan: CanonicalArtifact
    candidate_eligibility: CanonicalArtifact
    environment: CanonicalArtifact
    results: tuple[CanonicalArtifact, ...]
    comparison: CanonicalArtifact
    run_record: ExperimentRunRecord
    run_record_artifact: CanonicalArtifact

    def __post_init__(self) -> None:
        if len(self.results) < 2:
            raise ValueError("experiment artifact bundle requires at least two result artifacts")
        result_hashes = tuple(item.artifact_hash for item in self.results)
        recorded_hashes = tuple(
            item.artifact_hash for item in self.run_record.result_artifacts
        )
        if result_hashes != recorded_hashes:
            raise ValueError("run record result hashes must match canonical result artifacts")
        if self.comparison.artifact_hash != self.run_record.comparison_artifact.artifact_hash:
            raise ValueError("run record comparison hash must match canonical comparison artifact")
        if (
            self.candidate_eligibility.artifact_hash
            != self.run_record.candidate_eligibility_ref.artifact_hash
        ):
            raise ValueError(
                "run record eligibility hash must match canonical eligibility artifact"
            )


def _artifact_reference(
    artifact: CanonicalArtifact,
    artifact_version: str,
) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact.artifact_id,
        artifact_version=artifact_version,
        artifact_hash=artifact.artifact_hash,
    )


def serialize_experiment_run(
    *,
    plan: ExperimentPlan,
    eligibility: CandidateEligibilityReport,
    environment: ExecutionEnvironment,
    run: WorkbenchRun,
    started_at: str,
    completed_at: str,
) -> ExperimentArtifactBundle:
    """Serialize all artifacts and create a run record using only computed hashes."""

    if eligibility.experiment_id != plan.experiment_id:
        raise ValueError("eligibility report must identify the experiment plan")
    if eligibility.experiment_version != plan.experiment_version:
        raise ValueError("eligibility report version must match the experiment plan")
    if eligibility.candidate_registry_ref != plan.candidate_registry_ref:
        raise ValueError("eligibility report must preserve the plan registry reference")

    plan_artifact = serialize_artifact(plan.experiment_id, plan)
    eligibility_artifact = eligibility.artifact()
    environment_artifact = serialize_artifact(
        f"{run.run_id}:environment",
        environment,
    )
    result_artifacts = tuple(
        serialize_artifact(result.result_id, result) for result in run.results
    )
    comparison_artifact = serialize_artifact(
        run.comparison.comparison_id,
        run.comparison,
    )
    record = record_workbench_run(
        plan=plan,
        plan_ref=_artifact_reference(plan_artifact, plan.experiment_version),
        candidate_eligibility_ref=eligibility.reference(),
        environment=environment,
        run=run,
        result_hashes={
            artifact.artifact_id: artifact.artifact_hash
            for artifact in result_artifacts
        },
        comparison_hash=comparison_artifact.artifact_hash,
        started_at=started_at,
        completed_at=completed_at,
    )
    record_artifact = serialize_artifact(record.record_id, record)
    return ExperimentArtifactBundle(
        plan=plan_artifact,
        candidate_eligibility=eligibility_artifact,
        environment=environment_artifact,
        results=result_artifacts,
        comparison=comparison_artifact,
        run_record=record,
        run_record_artifact=record_artifact,
    )
