# ruff: noqa: I001
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessError,
    CheckpointWitnessObservationKind,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
    WitnessBoundCheckpointCorpusSnapshot,
    load_checkpoint_witness_evidence,
    persist_witness_bound_checkpoint_corpus,
    validate_checkpoint_witness_attestations,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import CanonicalArtifact
from ctrt.witness_gated_checkpoint_runner import (
    WITNESS_GATED_VERIFIED_CHECKS,
    WitnessGatedCheckpointExperimentRunner,
    WitnessGatedExperimentError,
    WitnessGatedRunnerStage,
    WitnessGatedRunnerStatus,
)
from test_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_corpus,
    checkpoint_log,
    load_document,
    policy as checkpoint_policy,
    prepare_checkpoint_store,
    stored_ref,
    validate_schema,
)
from test_credential_revocation_ledger import policy as revocation_policy
from test_extraction_review_adjudication import (
    FailOnContentAnalyzer,
    analyzer_registry,
    analyzers,
    candidate_registry,
    environment,
    experiment_plan,
    windows,
)

ROOT = Path(__file__).parents[1]
REGISTRY_PATH = (
    ROOT / "docs" / "candidates" / "synthetic-checkpoint-witness-registry.v0.1.0.json"
)
POLICY_PATH = (
    ROOT / "docs" / "candidates" / "synthetic-checkpoint-witness-policy.v0.1.0.json"
)
ATTESTATION_PATHS = tuple(
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / f"{name}-attestation.json"
    for name in ("alpha", "beta", "gamma")
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.8.0.json"
)
REGISTRY_SCHEMA = ROOT / "schemas" / "checkpoint-witness-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "checkpoint-witness-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / "checkpoint-witness-attestation.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "witness-bound-checkpoint-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "checkpoint-witness-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "witness-gated-checkpoint-final.schema.json"


class WitnessReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path, artifact_id: str) -> None:
        super().__init__(root)
        self._artifact_id = artifact_id
        self.fail_enabled = False

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if self.fail_enabled and artifact_id == self._artifact_id:
            raise ArtifactIntegrityError("synthetic witness attestation read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class CheckpointReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path, artifact_id: str) -> None:
        super().__init__(root)
        self._artifact_id = artifact_id
        self.fail_enabled = False

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if self.fail_enabled and artifact_id == self._artifact_id:
            raise ArtifactIntegrityError("synthetic checkpoint read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":checkpoint-witness-completion",
                ":checkpoint-witness-abstention",
                ":checkpoint-witness-terminal-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic witness final failure")
        return super().append(artifact)


def registry(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessRegistrySnapshot:
    return CheckpointWitnessRegistrySnapshot.from_document(
        document or load_document(REGISTRY_PATH)
    )


def witness_policy(
    document: dict[str, Any] | None = None,
) -> CheckpointWitnessPolicySnapshot:
    return CheckpointWitnessPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def attestations(
    documents: tuple[dict[str, Any], ...] | None = None,
) -> tuple[CheckpointWitnessAttestationSnapshot, ...]:
    source = documents or tuple(load_document(path) for path in ATTESTATION_PATHS)
    return tuple(
        CheckpointWitnessAttestationSnapshot.from_document(document)
        for document in source
    )


def witness_corpus(
    document: dict[str, Any] | None = None,
) -> WitnessBoundCheckpointCorpusSnapshot:
    return WitnessBoundCheckpointCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def prepare_witness_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    bound_corpus: WitnessBoundCheckpointCorpusSnapshot | None = None,
    records: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
    evaluated_at: str = "2026-08-03T03:05:00Z",
) -> tuple[Any, ...]:
    prepared = prepare_checkpoint_store(tmp_path, store=store)
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
    ) = prepared
    corpus = bound_corpus or witness_corpus()
    evidence = records or attestations()
    plan = experiment_plan(
        candidate,
        corpus.corpus.corpus.corpus.corpus,
        fixture_analyzers,
    )
    persist_witness_bound_checkpoint_corpus(
        artifact_store,
        plan=plan,
        corpus=corpus,
        predecessor_corpus=predecessor,
        registry=registry(),
        policy=witness_policy(),
        head_checkpoint=checkpoint(),
        attestations=evidence,
        evaluated_at=evaluated_at,
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
        evidence,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    bound_corpus: WitnessBoundCheckpointCorpusSnapshot | None = None,
    records: tuple[CheckpointWitnessAttestationSnapshot, ...] | None = None,
    runtime_registry: Any | None = None,
    run_id: str = "witness-run-001",
    evaluated_at: str = "2026-08-03T03:05:00Z",
):
    prepared = prepare_witness_store(
        tmp_path,
        store=store,
        bound_corpus=bound_corpus,
        records=records,
        evaluated_at=evaluated_at,
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
        evidence,
    ) = prepared
    runner = WitnessGatedCheckpointExperimentRunner(
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
        witness_registry=registry(),
        witness_policy=witness_policy(),
        witness_attestations=evidence,
        corpus=corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        checkpoint_verified_at=evaluated_at,
        witness_evaluated_at=evaluated_at,
        revocation_evaluated_at=evaluated_at,
        credential_evaluated_at=evaluated_at,
        quality_evaluated_at=evaluated_at,
        review_evaluated_at=evaluated_at,
    )
    return receipt, artifact_store


def rebuild_case(
    *,
    index: int,
    mutate: Callable[[dict[str, Any]], None],
    suffix: str,
) -> tuple[
    WitnessBoundCheckpointCorpusSnapshot,
    tuple[CheckpointWitnessAttestationSnapshot, ...],
]:
    documents = [load_document(path) for path in ATTESTATION_PATHS]
    mutate(documents[index])
    records = attestations(tuple(documents))
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": f"corpus.synthetic-three-items.witness-bound.{suffix}",
            "corpus_version": f"0.8.1-test-{suffix}",
            "checkpoint_witness_attestation_refs": [
                stored_ref(item.reference()) for item in records
            ],
            "created_at": "2026-08-03T03:04:30Z",
        }
    )
    return witness_corpus(corpus_document), records


def conflict_case() -> tuple[
    WitnessBoundCheckpointCorpusSnapshot,
    tuple[CheckpointWitnessAttestationSnapshot, ...],
]:
    def mutate(document: dict[str, Any]) -> None:
        document["observed_head_ref"] = {
            "artifact_id": (
                "credential-revocation-checkpoint:"
                "checkpoint.synthetic.conflicting-head.0000"
            ),
            "artifact_hash": "sha256:" + "f" * 64,
            "canonicalization_version": "ctrt-canonical-json@0.1.0",
            "media_type": "application/json",
        }
        document["observation_kind"] = "conflicting_head"
        document["note"] = "Synthetic witness observed a conflicting head."

    return rebuild_case(index=1, mutate=mutate, suffix="conflict")


def test_matching_witnesses_execute_and_validate_schemas(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is WitnessGatedRunnerStatus.VERIFIED
    assert receipt.witness_outcome is CheckpointWitnessDecisionOutcome.EXECUTE
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.checkpoint_receipt is not None
    assert receipt.verified_checks == WITNESS_GATED_VERIFIED_CHECKS

    validate_schema(REGISTRY_SCHEMA, load_document(REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    for path in ATTESTATION_PATHS:
        validate_schema(ATTESTATION_SCHEMA, load_document(path))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    decision = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.witness_decision_ref.artifact_id,
                expected_hash=receipt.witness_decision_ref.artifact_hash,
            ).text
        ),
    )
    validate_schema(DECISION_SCHEMA, decision)
    assert [item["observation_kind"] for item in decision["observations"]] == [
        "matches_head",
        "matches_head",
        "matches_head",
    ]
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
    for forbidden in (
        "vote_count",
        "majority",
        "consensus_percentage",
        "aggregate_score",
    ):
        assert forbidden not in json.dumps(decision)
        assert forbidden not in json.dumps(final)


def test_single_conflict_abstains_despite_two_matching_witnesses(
    tmp_path: Path,
) -> None:
    corpus, records = conflict_case()
    run_id = "witness-run-conflict"
    receipt, store = execute(
        tmp_path,
        bound_corpus=corpus,
        records=records,
        run_id=run_id,
    )

    assert receipt.witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
    assert receipt.revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.checkpoint_receipt is None
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.witness_decision_ref.artifact_id).text),
    )
    kinds = [item["observation_kind"] for item in decision["observations"]]
    assert kinds.count("matches_head") == 2
    assert kinds.count("conflicting_head") == 1
    assert decision["outcome"] == "abstain"
    store.get(
        f"{run_id}:credential-revocation-checkpoint-verification"
    )
    for artifact_id in (
        f"{run_id}:revocation-checkpoint-completion",
        f"{run_id}:credential-revocation-decision",
        f"{run_id}:reviewer-credential-decision",
        f"{run_id}:review-adjudication-decision",
        f"{run_id}:extraction-quality-decision",
        f"{run_id}:experiment-completion",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(artifact_id)


def test_witness_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.witness_attestation_refs == second.witness_attestation_refs
    assert first.checkpoint_verification_ref == second.checkpoint_verification_ref
    assert first.witness_decision_ref == second.witness_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


def test_witness_storage_reconstructs_exact_population(tmp_path: Path) -> None:
    prepared = prepare_witness_store(tmp_path)
    evidence = load_checkpoint_witness_evidence(
        prepared[0],
        corpus=witness_corpus(),
        registry=registry(),
        policy=witness_policy(),
    )

    assert evidence.attestations == attestations()
    assert evidence.attestation_refs == tuple(
        item.reference() for item in attestations()
    )


@pytest.mark.parametrize(
    ("mutate", "match"),
    (
        (
            lambda document: document.update(
                {"witness_identity_revision": "synthetic-checkpoint-witness@9.9.9"}
            ),
            "identity revision differs",
        ),
        (
            lambda document: document.update(
                {
                    "checkpoint_log_ref": {
                        "artifact_id": "log.synthetic.wrong",
                        "artifact_version": "9.9.9",
                        "artifact_hash": "sha256:" + "0" * 64,
                    }
                }
            ),
            "checkpoint log reference differs",
        ),
        (
            lambda document: document.update(
                {
                    "expected_head_ref": {
                        "artifact_id": "credential-revocation-checkpoint:wrong",
                        "artifact_hash": "sha256:" + "0" * 64,
                        "canonicalization_version": "ctrt-canonical-json@0.1.0",
                        "media_type": "application/json",
                    },
                    "observed_head_ref": {
                        "artifact_id": "credential-revocation-checkpoint:wrong",
                        "artifact_hash": "sha256:" + "0" * 64,
                        "canonicalization_version": "ctrt-canonical-json@0.1.0",
                        "media_type": "application/json",
                    },
                }
            ),
            "expected checkpoint head differs",
        ),
        (
            lambda document: document.update(
                {"observed_at": "2026-08-03T02:30:00Z"}
            ),
            "observation predates checkpoint publication",
        ),
        (
            lambda document: document.update(
                {"received_at": "2026-08-03T03:06:00Z"}
            ),
            "attestation received after evaluation",
        ),
    ),
)
def test_structural_witness_drift_fails(
    mutate: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    corpus, records = rebuild_case(index=0, mutate=mutate, suffix="drift")
    plan = experiment_plan(
        candidate_registry(),
        corpus.corpus.corpus.corpus.corpus,
        analyzers(),
    )

    with pytest.raises(CheckpointWitnessError, match=match):
        validate_checkpoint_witness_attestations(
            plan=plan,
            corpus=corpus,
            registry=registry(),
            policy=witness_policy(),
            head_checkpoint=checkpoint(),
            attestations=records,
            evaluated_at="2026-08-03T03:05:00Z",
        )


def test_duplicate_witness_identity_fails() -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["witness_id"] = "witness.synthetic.alpha"

    corpus, records = rebuild_case(index=1, mutate=mutate, suffix="duplicate")
    plan = experiment_plan(
        candidate_registry(),
        corpus.corpus.corpus.corpus.corpus,
        analyzers(),
    )

    with pytest.raises(CheckpointWitnessError, match="unique witnesses"):
        validate_checkpoint_witness_attestations(
            plan=plan,
            corpus=corpus,
            registry=registry(),
            policy=witness_policy(),
            head_checkpoint=checkpoint(),
            attestations=records,
            evaluated_at="2026-08-03T03:05:00Z",
        )


def test_observation_kind_must_derive_from_exact_references() -> None:
    document = load_document(ATTESTATION_PATHS[0])
    document["observation_kind"] = "conflicting_head"

    with pytest.raises(CheckpointWitnessError, match="must derive"):
        CheckpointWitnessAttestationSnapshot.from_document(document)


def test_vote_fields_are_forbidden_by_schema_and_parser() -> None:
    document = load_document(POLICY_PATH)
    document["vote_threshold"] = 2

    with pytest.raises(ValidationError):
        Draft202012Validator(
            load_document(POLICY_SCHEMA),
            format_checker=FormatChecker(),
        ).validate(document)
    with pytest.raises(CheckpointWitnessError, match="unsupported fields"):
        witness_policy(document)


def test_missing_stored_attestation_fails_before_witness_decision(
    tmp_path: Path,
) -> None:
    target = attestations()[1].artifact_id
    store = WitnessReadFailsStore(tmp_path / "artifacts", target)
    prepared = prepare_witness_store(tmp_path, store=store)
    store.fail_enabled = True
    runner = WitnessGatedCheckpointExperimentRunner(
        analyzer_registry=analyzer_registry(*prepared[-2]),
        artifact_store=store,
    )

    with pytest.raises(WitnessGatedExperimentError) as caught:
        runner.run(
            plan=prepared[10],
            candidate_registry=prepared[1],
            method_registry=prepared[2],
            quality_policy=prepared[3],
            reviewer_registry=prepared[4],
            review_policy=prepared[5],
            issuer_registry=prepared[6],
            credential_policy=prepared[7],
            revocation_policy=revocation_policy(),
            ledger=prepared[9],
            checkpoint_policy=checkpoint_policy(),
            checkpoint_log=checkpoint_log(),
            checkpoints=(checkpoint(),),
            witness_registry=registry(),
            witness_policy=witness_policy(),
            witness_attestations=prepared[12],
            corpus=prepared[8],
            environment=environment(),
            windows=windows(),
            experiment_run_id="witness-run-missing",
            checkpoint_verified_at="2026-08-03T03:05:00Z",
            witness_evaluated_at="2026-08-03T03:05:00Z",
            revocation_evaluated_at="2026-08-03T03:05:00Z",
            credential_evaluated_at="2026-08-03T03:05:00Z",
            quality_evaluated_at="2026-08-03T03:05:00Z",
            review_evaluated_at="2026-08-03T03:05:00Z",
        )

    assert caught.value.stage is WitnessGatedRunnerStage.EVIDENCE_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("witness-run-missing:checkpoint-witness-decision")


def test_missing_checkpoint_fails_before_witness_decision(tmp_path: Path) -> None:
    store = CheckpointReadFailsStore(tmp_path / "artifacts", checkpoint().artifact_id)
    prepared = prepare_witness_store(tmp_path, store=store)
    store.fail_enabled = True
    runner = WitnessGatedCheckpointExperimentRunner(
        analyzer_registry=analyzer_registry(*prepared[-2]),
        artifact_store=store,
    )

    with pytest.raises(WitnessGatedExperimentError) as caught:
        runner.run(
            plan=prepared[10],
            candidate_registry=prepared[1],
            method_registry=prepared[2],
            quality_policy=prepared[3],
            reviewer_registry=prepared[4],
            review_policy=prepared[5],
            issuer_registry=prepared[6],
            credential_policy=prepared[7],
            revocation_policy=revocation_policy(),
            ledger=prepared[9],
            checkpoint_policy=checkpoint_policy(),
            checkpoint_log=checkpoint_log(),
            checkpoints=(checkpoint(),),
            witness_registry=registry(),
            witness_policy=witness_policy(),
            witness_attestations=prepared[12],
            corpus=prepared[8],
            environment=environment(),
            windows=windows(),
            experiment_run_id="witness-run-checkpoint-missing",
            checkpoint_verified_at="2026-08-03T03:05:00Z",
            witness_evaluated_at="2026-08-03T03:05:00Z",
            revocation_evaluated_at="2026-08-03T03:05:00Z",
            credential_evaluated_at="2026-08-03T03:05:00Z",
            quality_evaluated_at="2026-08-03T03:05:00Z",
            review_evaluated_at="2026-08-03T03:05:00Z",
        )

    assert caught.value.stage is WitnessGatedRunnerStage.EVIDENCE_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("witness-run-checkpoint-missing:checkpoint-witness-decision")


def test_downstream_failure_preserves_witness_decision_and_partial_progress(
    tmp_path: Path,
) -> None:
    prepared = prepare_witness_store(tmp_path)
    fixture_analyzers = prepared[-2]
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(
            base=fixture_analyzers[0],
            fail_content_id="content-002",
        ),
        *fixture_analyzers[1:],
    )

    with pytest.raises(WitnessGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=prepared[0],
            runtime_registry=runtime_registry,
            run_id="witness-run-downstream-failure",
        )

    assert caught.value.stage is WitnessGatedRunnerStage.CHECKPOINT_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    prepared[0].get(
        "witness-run-downstream-failure:"
        "credential-revocation-checkpoint-verification"
    )
    prepared[0].get(
        "witness-run-downstream-failure:checkpoint-witness-decision"
    )
    with pytest.raises(ArtifactNotFoundError):
        prepared[0].get(
            "witness-run-downstream-failure:checkpoint-witness-completion"
        )


def test_final_persistence_failure_preserves_prior_verified_artifacts(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(WitnessGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            run_id="witness-run-final-failure",
        )

    assert caught.value.stage is WitnessGatedRunnerStage.FINAL_PERSISTENCE
    store.get(
        "witness-run-final-failure:"
        "credential-revocation-checkpoint-verification"
    )
    store.get("witness-run-final-failure:checkpoint-witness-decision")
    store.get("witness-run-final-failure:revocation-checkpoint-completion")
    with pytest.raises(ArtifactNotFoundError):
        store.get("witness-run-final-failure:checkpoint-witness-completion")
