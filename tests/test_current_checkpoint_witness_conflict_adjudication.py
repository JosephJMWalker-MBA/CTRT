from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
)
from ctrt.current_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot,
    ConflictAdjudicationError,
    load_current_checkpoint_conflict_adjudication_evidence,
    persist_current_checkpoint_adjudication_bound_corpus,
    validate_current_checkpoint_conflict_adjudication,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)

witness_fx = import_module(
    "test_checkpoint_witness_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness"
)
checkpoint_fx = witness_fx.checkpoint_fx

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-checkpoint-witness-conflict-"
    "adjudicator-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-checkpoint-witness-conflict-"
    "adjudication-policy.v0.1.0.json"
)
EVIDENCE_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-"
    "checkpoint-witness-conflict-adjudicator-credential-revocation"
)
CONFLICT_PATH = EVIDENCE_ROOT / "gamma-conflict-attestation.json"
ADJUDICATION_PATH = EVIDENCE_ROOT / "gamma-conflict-adjudication.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.19.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudicator-registry.schema.json"
)
POLICY_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudication-policy.schema.json"
)
ADJUDICATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-conflict-adjudication.schema.json"
)
CORPUS_SCHEMA = ROOT / "schemas" / (
    "current-checkpoint-witness-conflict-adjudication-bound-corpus.schema.json"
)
ATTESTATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-attestation.schema.json"
)
ADJUDICATION_REF_KEY = (
    "checkpoint_conflict_revocation_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_"
    "checkpoint_witness_conflict_adjudication_ref"
)


def conflict_attestation(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessAttestationSnapshot:
    return CheckpointWitnessAttestationSnapshot.from_document(
        document or load_document(CONFLICT_PATH)
    )


def conflict_attestations() -> tuple[CheckpointWitnessAttestationSnapshot, ...]:
    canonical = witness_fx.witness_attestations()
    return (canonical[0], canonical[1], conflict_attestation())


def conflict_adjudicator_registry(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicatorRegistrySnapshot:
    return WitnessConflictAdjudicatorRegistrySnapshot.from_document(
        document or load_document(REGISTRY_PATH)
    )


def conflict_adjudication_policy(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationPolicySnapshot:
    return WitnessConflictAdjudicationPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def conflict_adjudication(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationSnapshot:
    return WitnessConflictAdjudicationSnapshot.from_document(
        document or load_document(ADJUDICATION_PATH)
    )


def adjudication_corpus(
    document: dict[str, Any] | None = None,
    *,
    checkpoint_predecessor: Any | None = None,
    witness_predecessor: Any | None = None,
) -> AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot:
    snapshot = AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot
    return snapshot.from_document(
        document or load_document(CORPUS_PATH),
        checkpoint_predecessor=(
            checkpoint_predecessor or checkpoint_fx.checkpoint_corpus()
        ),
        witness_predecessor=witness_predecessor or witness_fx.witness_corpus(),
    )


def plan_for(selected: AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot):
    return replace(
        witness_fx.witness_plan(),
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def bound_to(
    record: WitnessConflictAdjudicationSnapshot,
) -> AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot:
    document = deepcopy(load_document(CORPUS_PATH))
    document[ADJUDICATION_REF_KEY] = stored_ref_document(record.reference())
    document["corpus_id"] = (
        "corpus.synthetic-three-items.current-checkpoint-witness-conflict-"
        f"adjudication-bound.{record.status.value}-test"
    )
    document["corpus_version"] = f"1.19.1-test-{record.status.value}"
    return adjudication_corpus(document)


def witness_decision(
    selected: AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot,
):
    return witness_fx.validate_current_checkpoint_witness_attestations(
        plan=plan_for(selected),
        corpus=cast(Any, selected.corpus),
        registry=witness_fx.witness_registry(),
        policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        attestations=conflict_attestations(),
        evaluated_at="2026-08-03T19:58:01Z",
    )


def validate(
    *,
    selected: AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot | None = None,
    record: WitnessConflictAdjudicationSnapshot | None = None,
    evaluated_at: str = "2026-08-03T19:58:01Z",
):
    selected_record = record or conflict_adjudication()
    bound = selected or adjudication_corpus()
    if bound.adjudication_ref != selected_record.reference():
        bound = bound_to(selected_record)
    return validate_current_checkpoint_conflict_adjudication(
        plan=plan_for(bound),
        corpus=bound,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        witness_decision=witness_decision(bound),
        adjudication=selected_record,
        evaluated_at=evaluated_at,
    )


def prepare_adjudication_store(
    tmp_path: Path,
    *,
    run_id: str = "current-adjudication-reconstruction",
) -> tuple[Any, ...]:
    prepared = witness_fx.prepare_witness_store(tmp_path, run_id=run_id)
    store = cast(FileSystemArtifactStore, prepared[0])
    witness_predecessor = prepared[2]
    checkpoint_predecessor = prepared[3]
    selected = adjudication_corpus(
        checkpoint_predecessor=checkpoint_predecessor,
        witness_predecessor=witness_predecessor,
    )
    plan = replace(
        prepared[1],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_current_checkpoint_adjudication_bound_corpus(
        store,
        plan=plan,
        corpus=selected,
        witness_predecessor=witness_predecessor,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        witness_attestations=conflict_attestations(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
        evaluated_at="2026-08-03T19:58:01Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_graph_schemas_and_resolved_decision() -> None:
    selected = adjudication_corpus()
    report = validate()
    assert conflict_attestation().artifact_hash == (
        "sha256:067f8962419550f6df976c14f96e1d084bcddae5ec521b77bebfc75a37e2cece"
    )
    assert conflict_adjudicator_registry().artifact_hash == (
        "sha256:e2acef5f118157df9f77419a939b1920bfa83ea7a34d508d921fe41927909ead"
    )
    assert conflict_adjudication_policy().artifact_hash == (
        "sha256:fb1adf97e37340fac363dfac3f5598d9810a5ff991050b5b3580bbb0bc3cf05e"
    )
    assert conflict_adjudication().artifact_hash == (
        "sha256:75993645d1489767bf26f0828e42148b9b631f0747bfce5d3f4be35841b5d68f"
    )
    assert selected.reference().artifact_hash == (
        "sha256:ec430190b7e75d0f0e5e7a207a9a786edf24c090046098d2e7699b294876e784"
    )
    assert selected.predecessor_corpus_ref == witness_fx.witness_corpus().reference()
    assert report.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert report.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert report.outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert report.fork_evidence == conflict_adjudication().fork_evidence
    assert report.preserved_dissent == conflict_adjudication().preserved_dissent
    validate_schema(REGISTRY_SCHEMA, load_document(REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(ATTESTATION_SCHEMA, load_document(CONFLICT_PATH))
    validate_schema(ADJUDICATION_SCHEMA, load_document(ADJUDICATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_conflicting_population_remains_witness_abstention() -> None:
    decision = witness_decision(adjudication_corpus())
    assert decision.outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert tuple(item.abstention.triggered for item in decision.observations) == (
        False,
        False,
        True,
    )


def test_pending_conflict_abstains() -> None:
    document = deepcopy(load_document(ADJUDICATION_PATH))
    document.update(
        {
            "status": "pending",
            "adjudicator_id": None,
            "adjudicator_identity_revision": None,
            "selected_head_ref": None,
            "preserved_dissent": [],
            "rationale": "Synthetic conflict remains pending authorized review.",
        }
    )
    report = validate(record=conflict_adjudication(document))
    assert report.resolution_status is WitnessConflictResolutionStatus.PENDING
    assert report.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN


def test_unresolved_conflict_abstains_and_preserves_dissent() -> None:
    document = deepcopy(load_document(ADJUDICATION_PATH))
    document.update(
        {
            "status": "unresolved",
            "selected_head_ref": None,
            "rationale": "Available evidence does not authorize resolution.",
        }
    )
    report = validate(record=conflict_adjudication(document))
    assert report.resolution_status is WitnessConflictResolutionStatus.UNRESOLVED
    assert report.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert report.preserved_dissent


def test_resolved_adjudication_cannot_select_alternate_head() -> None:
    document = deepcopy(load_document(ADJUDICATION_PATH))
    document["selected_head_ref"] = deepcopy(
        document["fork_evidence"][0]["observed_head_ref"]
    )
    changed = conflict_adjudication(document)
    with pytest.raises(ConflictAdjudicationError, match="declared checkpoint head"):
        validate(record=changed)


def test_decision_after_evaluation_is_rejected() -> None:
    with pytest.raises(ConflictAdjudicationError, match="after evaluation"):
        validate(evaluated_at="2026-08-03T19:57:58Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_adjudication_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(
        AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot,
        prepared[2],
    )
    first = load_current_checkpoint_conflict_adjudication_evidence(
        store,
        corpus=selected,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
    )
    second = load_current_checkpoint_conflict_adjudication_evidence(
        store,
        corpus=selected,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
    )
    assert first == second
    assert first.witness_evidence.attestations == conflict_attestations()


def test_schema_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
