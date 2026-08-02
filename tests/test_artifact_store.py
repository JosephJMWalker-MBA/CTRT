from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_pipeline import ExperimentArtifactBundle, serialize_experiment_run
from ctrt.artifact_store import (
    ArtifactConflictError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    persist_experiment_bundle,
    verify_experiment_bundle,
)
from ctrt.candidate_eligibility import (
    CandidateRegistrySnapshot,
    validate_candidate_eligibility,
)
from ctrt.contracts import ContentItem, SourceType
from ctrt.experiments import (
    ExecutionEnvironment,
    ExperimentPlan,
    ExperimentPlanStatus,
    InstrumentRevision,
    MetricDefinition,
    VersionedArtifactRef,
)
from ctrt.serialization import serialize_artifact
from ctrt.synthetic import first_signal_fixture, last_signal_fixture
from ctrt.workbench import AnalyzerRegistry, ContentAnalysisWorkbench

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / "synthetic-registry.v0.1.0.json"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _registry_snapshot() -> CandidateRegistrySnapshot:
    document = cast(
        dict[str, Any],
        json.loads(REGISTRY_PATH.read_text(encoding="utf-8")),
    )
    return CandidateRegistrySnapshot.from_document(document)


def _artifact_ref(artifact_id: str, artifact_hash: str) -> VersionedArtifactRef:
    return VersionedArtifactRef(
        artifact_id=artifact_id,
        artifact_version="0.1.0",
        artifact_hash=artifact_hash,
    )


def _plan(registry: CandidateRegistrySnapshot) -> ExperimentPlan:
    return ExperimentPlan(
        experiment_id="experiment.synthetic-store",
        experiment_version="0.1.0",
        status=ExperimentPlanStatus.FROZEN,
        research_question="Can canonical artifacts remain append-only and verifiable?",
        protocol_ref=_artifact_ref("protocol.synthetic-workbench", HASH_A),
        candidate_registry_ref=registry.reference(),
        corpus_ref=_artifact_ref("corpus.synthetic-vocabulary", HASH_B),
        content_ids=("content-001",),
        dimension_ids=("sentiment_valence",),
        instrument_revisions=(
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
        ),
        metrics=(MetricDefinition("signed-valence-agreement", "0.1.0"),),
        exclusion_rules=(),
        stopping_rules=("Stop after the declared fixture run.",),
        created_at="2026-08-02T21:30:00Z",
    )


def _environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        environment_id="environment.synthetic-store",
        environment_version="0.1.0",
        python_version="3.11",
        operating_system="Ubuntu 24.04",
        architecture="x86_64",
        dependency_lock_hash=HASH_A,
        runtime_configuration_hash=HASH_B,
        hardware_profile="Local CPU fixture environment",
    )


def _bundle() -> ExperimentArtifactBundle:
    registry_snapshot = _registry_snapshot()
    plan = _plan(registry_snapshot)
    eligibility = validate_candidate_eligibility(plan, registry_snapshot)
    analyzer_registry = AnalyzerRegistry()
    first = first_signal_fixture()
    last = last_signal_fixture()
    analyzer_registry.register(first)
    analyzer_registry.register(last)
    content = ContentItem(
        content_id="content-001",
        text="The launch was good, but the support was bad.",
        source_type=SourceType.RAW_TEXT,
        content_hash=HASH_C,
        language="en",
    )
    run = ContentAnalysisWorkbench(analyzer_registry).run_content_item(
        run_id="run-store-001",
        content=content,
        analyzer_ids=(first.identity.analyzer_id, last.identity.analyzer_id),
    )
    return serialize_experiment_run(
        plan=plan,
        eligibility=eligibility,
        environment=_environment(),
        run=run,
        started_at="2026-08-02T21:31:00Z",
        completed_at="2026-08-02T21:31:01Z",
    )


def _blob_path(root: Path, artifact_hash: str) -> Path:
    return root / "blobs" / "sha256" / artifact_hash.removeprefix("sha256:")


def test_store_round_trip_reverifies_canonical_bytes(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)
    artifact = serialize_artifact("artifact.example", {"value": 1, "name": "example"})

    reference = store.append(artifact)
    loaded = store.get(artifact.artifact_id, expected_hash=artifact.artifact_hash)

    assert reference.artifact_hash == artifact.artifact_hash
    assert loaded == artifact
    assert store.read_payload(artifact.artifact_hash) == artifact.payload


def test_identical_repeat_is_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)
    artifact = serialize_artifact("artifact.example", {"value": 1})

    first = store.append(artifact)
    second = store.append(artifact)

    assert first == second
    assert store.get(artifact.artifact_id) == artifact


def test_existing_artifact_id_cannot_be_replaced(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)
    store.append(serialize_artifact("artifact.example", {"value": 1}))

    with pytest.raises(ArtifactConflictError, match="append-only"):
        store.append(serialize_artifact("artifact.example", {"value": 2}))


def test_missing_artifact_is_explicit(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)

    with pytest.raises(ArtifactNotFoundError, match="not stored"):
        store.get("artifact.missing")


def test_tampered_blob_fails_read_time_verification(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)
    artifact = serialize_artifact("artifact.example", {"value": 1})
    store.append(artifact)
    _blob_path(tmp_path, artifact.artifact_hash).write_bytes(b"tampered")

    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        store.get(artifact.artifact_id)


def test_complete_experiment_bundle_is_persisted_and_verified(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)
    bundle = _bundle()

    stored = persist_experiment_bundle(store, bundle)
    verify_experiment_bundle(store, stored)

    roles = tuple(item.role for item in stored.manifest.artifacts)
    assert roles == (
        "plan",
        "candidate-eligibility",
        "environment",
        "result:0",
        "result:1",
        "comparison",
        "run-record",
    )
    assert store.get(
        stored.manifest_ref.artifact_id,
        expected_hash=stored.manifest_ref.artifact_hash,
    ).artifact_id == stored.manifest.bundle_id


def test_bundle_verification_detects_tampered_member(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path)
    stored = persist_experiment_bundle(store, _bundle())
    result_ref = next(
        item.artifact
        for item in stored.manifest.artifacts
        if item.role == "result:0"
    )
    _blob_path(tmp_path, result_ref.artifact_hash).write_bytes(b"tampered-result")

    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        verify_experiment_bundle(store, stored)
