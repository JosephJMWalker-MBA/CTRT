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
from ctrt.current_revocation_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
    ConflictAdjudicationError,
    load_current_revocation_checkpoint_conflict_adjudication_evidence,
    persist_current_revocation_checkpoint_adjudication_bound_corpus,
    validate_current_revocation_checkpoint_conflict_adjudication,
)
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)

witness_fx = import_module("test_current_revocation_checkpoint_witness")
checkpoint_fx = witness_fx.checkpoint_fx

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-conflict-adjudicator-registry.v0.1.0.json"
)
POLICY_PATH = ROOT / "docs" / "candidates" / (
    "synthetic-current-checkpoint-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-conflict-adjudication-policy.v0.1.0.json"
)
EVIDENCE_ROOT = ROOT / "docs" / "corpora" / "extraction" / "revocations" / (
    "witnesses/adjudicator-checkpoints/witness-conflict-adjudicator-checkpoint-"
    "witness-conflict-adjudicator-credential-revocation/checkpoints/witnesses"
)
CONFLICT_PATH = EVIDENCE_ROOT / "gamma-conflict-attestation.json"
ADJUDICATION_PATH = EVIDENCE_ROOT / "gamma-conflict-adjudication.json"
CORPUS_PATH = ROOT / "docs" / "corpora" / "extraction" / (
    "synthetic-corpus.v1.24.0.json"
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
    "current-revocation-checkpoint-witness-conflict-adjudication-bound-"
    "corpus.schema.json"
)
ATTESTATION_SCHEMA = ROOT / "schemas" / (
    "adjudicator-checkpoint-witness-attestation.schema.json"
)
ADJUDICATION_REF_KEY = (
    "current_checkpoint_witness_conflict_adjudicator_credential_revocation_"
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
) -> AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot:
    snapshot = AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot
    return snapshot.from_document(
        document or load_document(CORPUS_PATH),
        checkpoint_predecessor=(
            checkpoint_predecessor or checkpoint_fx.checkpoint_corpus()
        ),
        witness_predecessor=witness_predecessor or witness_fx.witness_corpus(),
    )


def plan_for(
    selected: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
):
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
) -> AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot:
    document = deepcopy(load_document(CORPUS_PATH))
    document[ADJUDICATION_REF_KEY] = stored_ref_document(record.reference())
    document["corpus_id"] = (
        "corpus.synthetic-three-items.current-revocation-checkpoint-witness-"
        f"conflict-adjudication-bound.{record.status.value}-test"
    )
    document["corpus_version"] = f"1.24.1-test-{record.status.value}"
    return adjudication_corpus(document)


def witness_decision(
    selected: AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
):
    contract = witness_fx.contract
    return contract.validate_current_conflict_adjudicator_revocation_checkpoint_witnesses(
        plan=plan_for(selected),
        corpus=cast(Any, selected.corpus),
        registry=witness_fx.witness_registry(),
        policy=witness_fx.witness_policy(),
        head_checkpoint=checkpoint_fx.checkpoint(),
        attestations=conflict_attestations(),
        evaluated_at="2026-08-03T19:58:37Z",
    )


def validate(
    *,
    selected: (
        AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot | None
    ) = None,
    record: WitnessConflictAdjudicationSnapshot | None = None,
    evaluated_at: str = "2026-08-03T19:58:37Z",
):
    selected_record = record or conflict_adjudication()
    bound = selected or adjudication_corpus()
    if bound.adjudication_ref != selected_record.reference():
        bound = bound_to(selected_record)
    return validate_current_revocation_checkpoint_conflict_adjudication(
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
    run_id: str = "current-revocation-checkpoint-adjudication-reconstruction",
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
    persist_current_revocation_checkpoint_adjudication_bound_corpus(
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
        evaluated_at="2026-08-03T19:58:37Z",
    )
    return (store, plan, selected, *prepared[2:])


def test_fixed_graph_schemas_and_resolved_decision() -> None:
    selected = adjudication_corpus()
    report = validate()
    assert conflict_attestation().artifact_hash == (
        "sha256:914deff79eae3b553c1ff068ac72840e19dd9bd1ebbb38b8c3f664afb666cce9"
    )
    assert conflict_adjudicator_registry().artifact_hash == (
        "sha256:aa657368aa10e3b24c45f550ecb7a897bca900ce34fda72038076370aa196f54"
    )
    assert conflict_adjudication_policy().artifact_hash == (
        "sha256:1df94869e96a2ea024bb50b571a0579637d9e300a91bb20c091c5c0326dc6a6f"
    )
    assert conflict_adjudication().artifact_hash == (
        "sha256:0dd962ff196b63672cf595a8c0d160683f45518962848494490f80a3e1fc62ee"
    )
    assert selected.reference().artifact_hash == (
        "sha256:a98bcdc6c6c146de7d688ea708285f8d4b82bd93a8486ac5e37e76bf3acaa5fb"
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
        validate(evaluated_at="2026-08-03T19:58:34Z")


def test_manifest_last_persistence_and_reconstruction(tmp_path: Path) -> None:
    prepared = prepare_adjudication_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    selected = cast(
        AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
        prepared[2],
    )
    first = load_current_revocation_checkpoint_conflict_adjudication_evidence(
        store,
        corpus=selected,
        witness_registry=witness_fx.witness_registry(),
        witness_policy=witness_fx.witness_policy(),
        adjudicator_registry=conflict_adjudicator_registry(),
        adjudication_policy=conflict_adjudication_policy(),
        adjudication=conflict_adjudication(),
    )
    second = load_current_revocation_checkpoint_conflict_adjudication_evidence(
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
