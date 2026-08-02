from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.candidate_eligibility import (
    CandidateEligibilityError,
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.experiments import (
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)

ROOT = Path(__file__).parents[1]
SYNTHETIC_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
INITIAL_PATH = ROOT / "docs" / "candidates" / "initial-registry.v0.1.0.json"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def artifact(artifact_id: str, artifact_hash: str) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=artifact_hash,
    )


def revisions() -> tuple[InstrumentRevision, InstrumentRevision]:
    return (
        InstrumentRevision(
            candidate_id="fixture.first-signal",
            analyzer_id="synthetic.sentiment.first-signal",
            dimension_id="sentiment_valence",
            implementation_revision="ctrt-fixture-first@0.1.0",
            adapter_version="0.1.0",
            configuration_hash=HASH_A,
        ),
        InstrumentRevision(
            candidate_id="fixture.last-signal",
            analyzer_id="synthetic.sentiment.last-signal",
            dimension_id="sentiment_valence",
            implementation_revision="ctrt-fixture-last@0.1.0",
            adapter_version="0.1.0",
            configuration_hash=HASH_B,
        ),
    )


def plan_for(
    registry: CandidateRegistrySnapshot,
    *,
    instrument_revisions: tuple[InstrumentRevision, ...] | None = None,
) -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="experiment.synthetic-disagreement",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Does exact registry authorization gate execution?",
        protocol_ref=artifact("protocol.synthetic-workbench", HASH_A),
        candidate_registry_ref=registry.reference(),
        corpus_ref=artifact("corpus.synthetic-vocabulary", HASH_B),
        content_ids=("content-001",),
        dimension_ids=("sentiment_valence",),
        instrument_revisions=instrument_revisions or revisions(),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=(),
        stopping_rules=("Stop after the declared fixture run.",),
        created_at="2026-08-02T21:15:00Z",
    )


def synthetic_snapshot() -> CandidateRegistrySnapshot:
    return CandidateRegistrySnapshot.from_document(load_document(SYNTHETIC_PATH))


def test_accepted_synthetic_registry_authorizes_exact_plan() -> None:
    registry = synthetic_snapshot()
    plan = plan_for(registry)

    report = validate_candidate_eligibility(plan, registry)

    assert report.candidate_registry_ref == registry.reference()
    assert report.authorized_candidate_ids == (
        "fixture.first-signal",
        "fixture.last-signal",
    )
    assert report.authorized_analyzer_ids == (
        "synthetic.sentiment.first-signal",
        "synthetic.sentiment.last-signal",
    )
    assert report.reference().artifact_hash == report.artifact().artifact_hash


def test_plan_registry_hash_must_match_supplied_snapshot() -> None:
    registry = synthetic_snapshot()
    valid = plan_for(registry)
    mismatched = ExperimentPlan(
        experiment_id=valid.experiment_id,
        experiment_version=valid.experiment_version,
        status=valid.status,
        research_question=valid.research_question,
        protocol_ref=valid.protocol_ref,
        candidate_registry_ref=artifact(registry.registry_id, HASH_A),
        corpus_ref=valid.corpus_ref,
        content_ids=valid.content_ids,
        dimension_ids=valid.dimension_ids,
        instrument_revisions=valid.instrument_revisions,
        metrics=valid.metrics,
        exclusion_rules=valid.exclusion_rules,
        stopping_rules=valid.stopping_rules,
        created_at=valid.created_at,
    )

    with pytest.raises(CandidateEligibilityError, match="does not match"):
        validate_candidate_eligibility(mismatched, registry)


def test_registry_must_be_accepted() -> None:
    document = load_document(SYNTHETIC_PATH)
    document["status"] = "draft"
    registry = CandidateRegistrySnapshot.from_document(document)

    with pytest.raises(CandidateEligibilityError, match="must be accepted"):
        validate_candidate_eligibility(plan_for(registry), registry)


def test_revision_drift_is_rejected() -> None:
    registry = synthetic_snapshot()
    changed = list(revisions())
    changed[0] = InstrumentRevision(
        candidate_id=changed[0].candidate_id,
        analyzer_id=changed[0].analyzer_id,
        dimension_id=changed[0].dimension_id,
        implementation_revision="ctrt-fixture-first@0.2.0",
        adapter_version=changed[0].adapter_version,
        configuration_hash=changed[0].configuration_hash,
    )

    with pytest.raises(CandidateEligibilityError, match="differs from the registry pin"):
        validate_candidate_eligibility(
            plan_for(registry, instrument_revisions=tuple(changed)),
            registry,
        )


def test_blocked_license_and_unauthorized_analyzer_are_rejected() -> None:
    document = copy.deepcopy(load_document(SYNTHETIC_PATH))
    document["candidates"][0]["license_review"]["status"] = "blocked"
    document["candidates"][1]["authorized_analyzer_ids"] = []
    registry = CandidateRegistrySnapshot.from_document(document)

    with pytest.raises(CandidateEligibilityError) as caught:
        validate_candidate_eligibility(plan_for(registry), registry)

    message = str(caught.value)
    assert "license review is blocked" in message
    assert "not explicitly authorized" in message


def test_initial_real_candidate_registry_cannot_authorize_execution_yet() -> None:
    document = load_document(INITIAL_PATH)
    document["status"] = "accepted"
    registry = CandidateRegistrySnapshot.from_document(document)
    real_revisions = (
        InstrumentRevision(
            candidate_id="sentiment.vader",
            analyzer_id="candidate.vader.a",
            dimension_id="sentiment_valence",
            implementation_revision="unverified-revision-a",
            adapter_version="0.1.0",
            configuration_hash=HASH_A,
        ),
        InstrumentRevision(
            candidate_id="sentiment.vader",
            analyzer_id="candidate.vader.b",
            dimension_id="sentiment_valence",
            implementation_revision="unverified-revision-b",
            adapter_version="0.1.0",
            configuration_hash=HASH_B,
        ),
    )

    with pytest.raises(CandidateEligibilityError) as caught:
        validate_candidate_eligibility(
            plan_for(registry, instrument_revisions=real_revisions),
            registry,
        )

    message = str(caught.value)
    assert "not explicitly authorized" in message
    assert "no pinned implementation revision" in message
