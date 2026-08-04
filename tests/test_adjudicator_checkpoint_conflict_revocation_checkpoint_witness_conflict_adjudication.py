from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError
from test_adjudicator_checkpoint_conflict_credential_attestation import frozen_plan
from test_adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
)
from test_adjudicator_checkpoint_conflict_revocation_checkpoint_witness_attestation import (
    ATTESTATION_PATHS,
    prepare_witness_store,
    stored_ref_document,
    validate_witness_attestations,
    witness_attestations,
    witness_corpus,
    witness_policy,
    witness_registry,
)
from test_adjudicator_checkpoint_witness_conflict_adjudication import load_document
from test_credential_revocation_checkpoints import validate_schema

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)

adjudication_contracts = import_module(
    "ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoint_"
    "witness_conflict_adjudication"
)
AdjudicationCorpus = (
    adjudication_contracts.AdjudicationBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointWitnessCorpusSnapshot
)
AdjudicatorCheckpointWitnessConflictAdjudicationError = (
    adjudication_contracts.AdjudicatorCheckpointWitnessConflictAdjudicationError
)
load_adjudication_evidence = (
    adjudication_contracts.load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication_evidence
)
persist_adjudication_corpus = (
    adjudication_contracts.persist_adjudication_bound_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_corpus
)
validate_adjudication = (
    adjudication_contracts.validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication
)


ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-"
    "witness-conflict-adjudicator-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-"
    "witness-conflict-adjudication-policy.v0.1.0.json"
)
ADJUDICATION_PATH = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/checkpoint-conflict-revocation/"
    "witness-conflict-adjudication.json"
)
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.9.0.json"
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
    "adjudicator-checkpoint-conflict-revocation-checkpoint-"
    "witness-conflict-adjudication-bound-corpus.schema.json"
)


def adjudicator_registry(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicatorRegistrySnapshot:
    return WitnessConflictAdjudicatorRegistrySnapshot.from_document(
        document or load_document(REGISTRY_PATH)
    )


def adjudication_policy(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationPolicySnapshot:
    return WitnessConflictAdjudicationPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def adjudication(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationSnapshot:
    return WitnessConflictAdjudicationSnapshot.from_document(
        document or load_document(ADJUDICATION_PATH)
    )


def corpus(
    document: dict[str, Any] | None = None,
) -> Any:
    return AdjudicationCorpus.from_document(
        document or load_document(CORPUS_PATH),
        checkpoint_predecessor=checkpoint_corpus(),
        witness_predecessor=witness_corpus(),
    )


def plan_for(selected: Any | None = None):
    bound = selected or corpus()
    return replace(
        frozen_plan(),
        corpus_ref=bound.reference(),
        content_ids=bound.content_ids,
    )


def validate(
    *,
    selected: Any | None = None,
    attestations: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
    adjudication_record: WitnessConflictAdjudicationSnapshot | None = None,
    evaluated_at: str = "2026-08-03T19:55:30Z",
):
    bound = selected or corpus()
    records = attestations or witness_attestations()
    plan = plan_for(bound)
    witness_decision = validate_witness_attestations(
        plan=plan,
        corpus=bound.corpus,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint(),
        attestations=records,
        evaluated_at=evaluated_at,
    )
    return validate_adjudication(
        plan=plan,
        corpus=bound,
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        witness_decision=witness_decision,
        adjudication=adjudication_record or adjudication(),
        evaluated_at=evaluated_at,
    )


def conflict_case(
    *,
    status: str = "resolved",
) -> tuple[Any, tuple[CheckpointWitnessAttestationSnapshot, ...], WitnessConflictAdjudicationSnapshot]:
    documents = tuple(load_document(path) for path in ATTESTATION_PATHS)
    changed_documents = tuple(deepcopy(item) for item in documents)
    changed_documents[2]["observed_head_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed_documents[2]["observation_kind"] = "conflicting_head"
    records = tuple(
        CheckpointWitnessAttestationSnapshot.from_document(item)
        for item in changed_documents
    )
    conflict = records[2]
    expected_head = stored_ref_document(checkpoint().reference())
    observed_head = deepcopy(changed_documents[2]["observed_head_ref"])
    fork = {
        "witness_id": conflict.witness_id,
        "attestation_ref": stored_ref_document(conflict.reference()),
        "expected_head_ref": expected_head,
        "observed_head_ref": observed_head,
    }
    dissent = {
        "witness_id": conflict.witness_id,
        "attestation_ref": stored_ref_document(conflict.reference()),
        "observed_head_ref": observed_head,
        "note": "Synthetic dissent remains preserved after authorized review.",
    }

    decision_document = deepcopy(load_document(ADJUDICATION_PATH))
    decision_document["status"] = status
    if status == "pending":
        decision_document.update(
            {
                "adjudicator_id": None,
                "adjudicator_identity_revision": None,
                "selected_head_ref": None,
                "fork_evidence": [fork],
                "preserved_dissent": [],
                "rationale": "Synthetic conflict is pending authorized review.",
            }
        )
    elif status == "unresolved":
        decision_document.update(
            {
                "adjudicator_id": (
                    "adjudicator.synthetic.checkpoint-conflict-revocation-"
                    "checkpoint-witness-conflict"
                ),
                "adjudicator_identity_revision": (
                    "synthetic-checkpoint-conflict-revocation-checkpoint-"
                    "witness-conflict-adjudicator@0.1.0"
                ),
                "selected_head_ref": None,
                "fork_evidence": [fork],
                "preserved_dissent": [dissent],
                "rationale": "Available evidence does not authorize resolution.",
            }
        )
    else:
        decision_document.update(
            {
                "adjudicator_id": (
                    "adjudicator.synthetic.checkpoint-conflict-revocation-"
                    "checkpoint-witness-conflict"
                ),
                "adjudicator_identity_revision": (
                    "synthetic-checkpoint-conflict-revocation-checkpoint-"
                    "witness-conflict-adjudicator@0.1.0"
                ),
                "selected_head_ref": expected_head,
                "fork_evidence": [fork],
                "preserved_dissent": [dissent],
                "rationale": (
                    "The independently verified checkpoint head is selected while "
                    "the conflicting witness observation remains preserved."
                ),
            }
        )
    decision = adjudication(decision_document)

    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document["corpus_id"] = (
        "corpus.synthetic-three-items.checkpoint-conflict-witness-"
        f"adjudication-{status}-test"
    )
    corpus_document["corpus_version"] = f"1.9.1-test-{status}"
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_witness_attestation_refs"
    ][2] = stored_ref_document(conflict.reference())
    corpus_document[
        "adjudicator_checkpoint_conflict_adjudicator_credential_revocation_"
        "checkpoint_witness_conflict_adjudication_ref"
    ] = stored_ref_document(decision.reference())
    selected = corpus(corpus_document)
    return selected, records, decision


def test_fixed_not_required_graph_and_schemas() -> None:
    selected = corpus()
    report = validate()
    assert selected.reference().artifact_hash == (
        "sha256:080d41cf305eaf28c120fb20359c4d01392409351af2bae350c8400cdb9b5d43"
    )
    assert selected.predecessor_corpus_ref == witness_corpus().reference()
    assert report.witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert report.resolution_status is WitnessConflictResolutionStatus.NOT_REQUIRED
    assert report.outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert not report.fork_evidence
    assert not report.preserved_dissent
    validate_schema(REGISTRY_SCHEMA, load_document(REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(ADJUDICATION_SCHEMA, load_document(ADJUDICATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_resolved_conflict_preserves_original_abstention_and_dissent() -> None:
    selected, records, decision = conflict_case()
    report = validate(
        selected=selected,
        attestations=records,
        adjudication_record=decision,
    )
    assert report.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert report.resolution_status is WitnessConflictResolutionStatus.RESOLVED
    assert report.outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert len(report.fork_evidence) == 1
    assert report.preserved_dissent[0].witness_id == records[2].witness_id


def test_pending_conflict_abstains() -> None:
    selected, records, decision = conflict_case(status="pending")
    report = validate(
        selected=selected,
        attestations=records,
        adjudication_record=decision,
    )
    assert report.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert report.resolution_status is WitnessConflictResolutionStatus.PENDING
    assert report.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN


def test_unresolved_conflict_abstains_and_preserves_dissent() -> None:
    selected, records, decision = conflict_case(status="unresolved")
    report = validate(
        selected=selected,
        attestations=records,
        adjudication_record=decision,
    )
    assert report.resolution_status is WitnessConflictResolutionStatus.UNRESOLVED
    assert report.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert report.preserved_dissent


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    predecessor = prepared[-1]
    selected = corpus()
    plan = replace(
        prepared[-2],
        corpus_ref=selected.reference(),
        content_ids=selected.content_ids,
    )
    persist_adjudication_corpus(
        store,
        plan=plan,
        corpus=selected,
        predecessor_corpus=predecessor,
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        head_checkpoint=checkpoint(),
        witness_attestations=witness_attestations(),
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=adjudication(),
        evaluated_at="2026-08-03T19:55:30Z",
    )
    first = load_adjudication_evidence(
        store,
        corpus=selected,
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=adjudication(),
    )
    second = load_adjudication_evidence(
        store,
        corpus=selected,
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=adjudication(),
    )
    assert first == second


def test_schema_rejects_confidence_field() -> None:
    document = deepcopy(load_document(CORPUS_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CORPUS_SCHEMA, document)
