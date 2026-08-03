# ruff: noqa: I001
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicated_witness_checkpoint_runner import (
    ADJUDICATED_WITNESS_VERIFIED_CHECKS,
    AdjudicatedWitnessCheckpointExperimentRunner,
    AdjudicatedWitnessExperimentError,
    AdjudicatedWitnessRunnerStage,
    AdjudicatedWitnessRunnerStatus,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import CanonicalArtifact
from ctrt.witness_conflict_adjudication import (
    AdjudicationBoundWitnessCorpusSnapshot,
    WitnessConflictAdjudicationError,
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
    load_witness_conflict_adjudication_evidence,
    persist_adjudication_bound_witness_corpus,
    validate_witness_conflict_adjudication,
)
from test_checkpoint_witness_attestation import (
    attestations as matching_attestations,
    prepare_witness_store,
    registry as witness_registry,
    witness_corpus,
    witness_policy,
)
from test_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_log,
    policy as checkpoint_policy,
    validate_schema,
)
from test_credential_revocation_ledger import policy as revocation_policy
from test_extraction_review_adjudication import (
    FailOnContentAnalyzer,
    analyzer_registry,
    environment,
    experiment_plan,
    windows,
)

ROOT = Path(__file__).parents[1]
ADJUDICATOR_REGISTRY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-witness-conflict-adjudicator-registry.v0.1.0.json"
)
ADJUDICATION_POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-witness-conflict-adjudication-policy.v0.1.0.json"
)
CONFLICT_ATTESTATION_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "gamma-conflict-attestation.json"
)
ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "gamma-conflict-adjudication.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.9.0.json"
)
REGISTRY_SCHEMA = (
    ROOT / "schemas" / "witness-conflict-adjudicator-registry.schema.json"
)
POLICY_SCHEMA = (
    ROOT / "schemas" / "witness-conflict-adjudication-policy.schema.json"
)
ADJUDICATION_SCHEMA = ROOT / "schemas" / "witness-conflict-adjudication.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "adjudication-bound-witness-corpus.schema.json"
DECISION_SCHEMA = (
    ROOT / "schemas" / "witness-conflict-adjudication-decision.schema.json"
)
FINAL_SCHEMA = ROOT / "schemas" / "adjudicated-witness-final.schema.json"


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":witness-conflict-adjudication-completion",
                ":witness-conflict-adjudication-abstention",
                ":witness-conflict-adjudication-terminal-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic adjudication final failure")
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def adjudicator_registry(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicatorRegistrySnapshot:
    return WitnessConflictAdjudicatorRegistrySnapshot.from_document(
        document or load_document(ADJUDICATOR_REGISTRY_PATH)
    )


def adjudication_policy(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationPolicySnapshot:
    return WitnessConflictAdjudicationPolicySnapshot.from_document(
        document or load_document(ADJUDICATION_POLICY_PATH)
    )


def adjudication(
    document: dict[str, Any] | None = None,
) -> WitnessConflictAdjudicationSnapshot:
    return WitnessConflictAdjudicationSnapshot.from_document(
        document or load_document(ADJUDICATION_PATH)
    )


def adjudication_corpus(
    document: dict[str, Any] | None = None,
) -> AdjudicationBoundWitnessCorpusSnapshot:
    return AdjudicationBoundWitnessCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def conflict_attestations() -> tuple[CheckpointWitnessAttestationSnapshot, ...]:
    alpha, beta, _ = matching_attestations()
    gamma = CheckpointWitnessAttestationSnapshot.from_document(
        load_document(CONFLICT_ATTESTATION_PATH)
    )
    return alpha, beta, gamma


def rebuild_case(
    *,
    suffix: str,
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[AdjudicationBoundWitnessCorpusSnapshot, WitnessConflictAdjudicationSnapshot]:
    document = load_document(ADJUDICATION_PATH)
    mutate(document)
    record = adjudication(document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": (
                "corpus.synthetic-three-items.witness-adjudication-bound."
                f"{suffix}"
            ),
            "corpus_version": f"0.9.1-test-{suffix}",
            "witness_conflict_adjudication_ref": {
                "artifact_id": record.reference().artifact_id,
                "artifact_hash": record.reference().artifact_hash,
                "canonicalization_version": (
                    record.reference().canonicalization_version
                ),
                "media_type": record.reference().media_type,
            },
            "created_at": "2026-08-03T03:39:30Z",
        }
    )
    return adjudication_corpus(corpus_document), record


def prepare_adjudicated_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    bound_corpus: AdjudicationBoundWitnessCorpusSnapshot | None = None,
    record: WitnessConflictAdjudicationSnapshot | None = None,
) -> tuple[Any, ...]:
    prepared = prepare_witness_store(tmp_path, store=store)
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        issuer_rules,
        credential_rules,
        predecessor,
        bound_ledger,
        _,
        fixture_analyzers,
        _,
    ) = prepared
    corpus = bound_corpus or adjudication_corpus()
    bound_record = record or adjudication()
    witness_records = conflict_attestations()
    plan = experiment_plan(
        candidate,
        corpus.corpus.corpus.corpus.corpus,
        fixture_analyzers,
    )
    persist_adjudication_bound_witness_corpus(
        artifact_store,
        plan=plan,
        corpus=corpus,
        predecessor_corpus=predecessor,
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        head_checkpoint=checkpoint(),
        witness_attestations=witness_records,
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=bound_record,
        evaluated_at="2026-08-03T03:40:00Z",
    )
    return (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        issuer_rules,
        credential_rules,
        corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
        witness_records,
        bound_record,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    bound_corpus: AdjudicationBoundWitnessCorpusSnapshot | None = None,
    record: WitnessConflictAdjudicationSnapshot | None = None,
    runtime_registry: Any | None = None,
    run_id: str = "witness-adjudication-run-001",
):
    prepared = prepare_adjudicated_store(
        tmp_path,
        store=store,
        bound_corpus=bound_corpus,
        record=record,
    )
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        issuer_rules,
        credential_rules,
        corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
        witness_records,
        bound_record,
    ) = prepared
    runner = AdjudicatedWitnessCheckpointExperimentRunner(
        analyzer_registry=runtime_registry
        or analyzer_registry(*fixture_analyzers),
        artifact_store=artifact_store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate,
        method_registry=methods,
        quality_policy=quality,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        issuer_registry=issuer_rules,
        credential_policy=credential_rules,
        revocation_policy=revocation_policy(),
        ledger=bound_ledger,
        checkpoint_policy=checkpoint_policy(),
        checkpoint_log=checkpoint_log(),
        checkpoints=(checkpoint(),),
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        witness_attestations=witness_records,
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=bound_record,
        corpus=corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        checkpoint_verified_at="2026-08-03T03:40:00Z",
        witness_evaluated_at="2026-08-03T03:40:00Z",
        adjudication_evaluated_at="2026-08-03T03:40:00Z",
        revocation_evaluated_at="2026-08-03T03:40:00Z",
        credential_evaluated_at="2026-08-03T03:40:00Z",
        quality_evaluated_at="2026-08-03T03:40:00Z",
        review_evaluated_at="2026-08-03T03:40:00Z",
    )
    return receipt, artifact_store


def test_resolved_conflict_executes_and_preserves_dissent(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is AdjudicatedWitnessRunnerStatus.VERIFIED
    assert receipt.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.checkpoint_receipt is not None
    assert receipt.verified_checks == ADJUDICATED_WITNESS_VERIFIED_CHECKS

    validate_schema(REGISTRY_SCHEMA, load_document(ADJUDICATOR_REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(ADJUDICATION_POLICY_PATH))
    validate_schema(ADJUDICATION_SCHEMA, load_document(ADJUDICATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    decision = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.adjudication_decision_ref.artifact_id,
                expected_hash=receipt.adjudication_decision_ref.artifact_hash,
            ).text
        ),
    )
    validate_schema(DECISION_SCHEMA, decision)
    assert decision["witness_outcome"] == "abstain"
    assert decision["resolution_status"] == "resolved"
    assert decision["outcome"] == "execute"
    assert decision["fork_evidence"][0]["witness_id"] == "witness.synthetic.gamma"
    assert decision["preserved_dissent"][0]["witness_id"] == (
        "witness.synthetic.gamma"
    )
    assert "vote_count" not in decision
    assert "consensus_percentage" not in decision

    final = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.final_manifest_ref.artifact_id,
                expected_hash=receipt.final_manifest_ref.artifact_hash,
            ).text
        ),
    )
    validate_schema(FINAL_SCHEMA, final)
    assert final["witness_outcome"] == "abstain"
    assert final["adjudication_outcome"] == "execute"


@pytest.mark.parametrize("status", ("pending", "unresolved"))
def test_pending_and_unresolved_conflicts_abstain_before_downstream(
    tmp_path: Path,
    status: str,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["status"] = status
        document["selected_head_ref"] = None
        if status == "pending":
            document["adjudicator_id"] = None
            document["adjudicator_identity_revision"] = None
            document["preserved_dissent"] = []
        document["rationale"] = f"Synthetic {status} fork remains fail closed."

    corpus, record = rebuild_case(suffix=status, mutate=mutate)
    receipt, store = execute(
        tmp_path,
        bound_corpus=corpus,
        record=record,
        run_id=f"witness-adjudication-{status}",
    )

    assert receipt.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
    assert receipt.revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    store.get(receipt.adjudication_decision_ref.artifact_id)
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"witness-adjudication-{status}:credential-revocation-decision")


def test_resolved_case_cannot_select_unverified_head() -> None:
    document = load_document(ADJUDICATION_PATH)
    document["selected_head_ref"] = deepcopy(document["fork_evidence"][0]["observed_head_ref"])
    record = adjudication(document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document["witness_conflict_adjudication_ref"] = {
        "artifact_id": record.reference().artifact_id,
        "artifact_hash": record.reference().artifact_hash,
        "canonicalization_version": record.reference().canonicalization_version,
        "media_type": record.reference().media_type,
    }
    corpus = adjudication_corpus(corpus_document)
    plan = experiment_plan(
        __import__("test_extraction_review_adjudication").candidate_registry(),
        corpus.corpus.corpus.corpus.corpus,
        __import__("test_extraction_review_adjudication").analyzers(),
    )
    witness_decision = __import__(
        "ctrt.checkpoint_witness_attestation",
        fromlist=["validate_checkpoint_witness_attestations"],
    ).validate_checkpoint_witness_attestations(
        plan=plan,
        corpus=corpus.corpus,
        registry=witness_registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint(),
        attestations=conflict_attestations(),
        evaluated_at="2026-08-03T03:40:00Z",
    )

    with pytest.raises(
        WitnessConflictAdjudicationError,
        match="declared checkpoint head",
    ):
        validate_witness_conflict_adjudication(
            plan=plan,
            corpus=corpus,
            witness_registry=witness_registry(),
            witness_policy=witness_policy(),
            adjudicator_registry=adjudicator_registry(),
            adjudication_policy=adjudication_policy(),
            witness_decision=witness_decision,
            adjudication=record,
            evaluated_at="2026-08-03T03:40:00Z",
        )


def test_unknown_adjudicator_fails_authorization(tmp_path: Path) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["adjudicator_id"] = "adjudicator.synthetic.unknown"

    corpus, record = rebuild_case(suffix="unknown", mutate=mutate)
    with pytest.raises(AdjudicatedWitnessExperimentError) as caught:
        execute(tmp_path, bound_corpus=corpus, record=record)

    assert caught.value.stage is AdjudicatedWitnessRunnerStage.ADJUDICATION_VALIDATION
    assert "unknown adjudicator" in str(caught.value)


def test_missing_preserved_dissent_is_rejected() -> None:
    document = load_document(ADJUDICATION_PATH)
    document["preserved_dissent"] = []
    with pytest.raises(
        WitnessConflictAdjudicationError,
        match="preserve dissent",
    ):
        adjudication(document)


def test_vote_fields_are_rejected_by_schema_and_parser() -> None:
    document = load_document(ADJUDICATION_PATH)
    document["vote_count"] = 3
    with pytest.raises(ValidationError):
        validate_schema(ADJUDICATION_SCHEMA, document)
    with pytest.raises(
        WitnessConflictAdjudicationError,
        match="unsupported fields",
    ):
        adjudication(document)


def test_adjudication_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.adjudication_ref == second.adjudication_ref
    assert first.adjudication_decision_ref == second.adjudication_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


def test_stored_adjudication_graph_reconstructs_exactly(tmp_path: Path) -> None:
    prepared = prepare_adjudicated_store(tmp_path)
    evidence = load_witness_conflict_adjudication_evidence(
        prepared[0],
        corpus=adjudication_corpus(),
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=adjudication(),
    )

    assert evidence.adjudication_ref == adjudication().reference()
    assert evidence.witness_evidence.attestations == conflict_attestations()


def test_downstream_failure_preserves_all_adjudication_evidence(
    tmp_path: Path,
) -> None:
    prepared = prepare_adjudicated_store(tmp_path)
    fixture_analyzers = prepared[11]
    runtime = analyzer_registry(
        FailOnContentAnalyzer(
            base=fixture_analyzers[0],
            fail_content_id="content-002",
        ),
        *fixture_analyzers[1:],
    )
    with pytest.raises(AdjudicatedWitnessExperimentError) as caught:
        execute(
            tmp_path,
            store=prepared[0],
            runtime_registry=runtime,
            run_id="witness-adjudication-downstream-failure",
        )

    assert caught.value.stage is AdjudicatedWitnessRunnerStage.CHECKPOINT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    for suffix in (
        "credential-revocation-checkpoint-verification",
        "checkpoint-witness-decision",
        "witness-conflict-adjudication-decision",
    ):
        prepared[0].get(f"witness-adjudication-downstream-failure:{suffix}")
    with pytest.raises(ArtifactNotFoundError):
        prepared[0].get(
            "witness-adjudication-downstream-failure:"
            "witness-conflict-adjudication-completion"
        )


def test_final_persistence_failure_preserves_prior_verified_artifacts(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")
    with pytest.raises(AdjudicatedWitnessExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            run_id="witness-adjudication-final-failure",
        )

    assert caught.value.stage is AdjudicatedWitnessRunnerStage.FINAL_PERSISTENCE
    for suffix in (
        "credential-revocation-checkpoint-verification",
        "checkpoint-witness-decision",
        "witness-conflict-adjudication-decision",
    ):
        store.get(f"witness-adjudication-final-failure:{suffix}")
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            "witness-adjudication-final-failure:"
            "witness-conflict-adjudication-completion"
        )
