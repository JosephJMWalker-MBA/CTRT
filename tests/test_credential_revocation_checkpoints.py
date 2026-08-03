# ruff: noqa: I001
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_gated_revocation_runner import (
    CHECKPOINT_GATED_VERIFIED_CHECKS,
    CheckpointGatedExperimentError,
    CheckpointGatedRevocationExperimentRunner,
    CheckpointGatedRunnerStage,
    CheckpointGatedRunnerStatus,
)
from ctrt.credential_revocation_checkpoints import (
    CheckpointBoundRevocationCorpusSnapshot,
    CredentialRevocationCheckpointError,
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationLedgerCheckpointSnapshot,
    load_credential_revocation_checkpoint_evidence,
    persist_checkpoint_bound_corpus,
    validate_credential_revocation_checkpoints,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import CanonicalArtifact, canonical_sha256
from test_credential_revocation_ledger import (
    events as revocation_events,
    ledger as revocation_ledger,
    policy as revocation_policy,
    prepare as prepare_revocation_store,
)
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
CHECKPOINT_POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-credential-revocation-checkpoint-policy.v0.1.0.json"
)
CHECKPOINT_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "checkpoints"
    / "genesis-checkpoint.json"
)
CHECKPOINT_LOG_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "checkpoints"
    / "synthetic-checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.7.0.json"
)
POLICY_SCHEMA = (
    ROOT / "schemas" / "credential-revocation-checkpoint-policy.schema.json"
)
CHECKPOINT_SCHEMA = (
    ROOT / "schemas" / "credential-revocation-ledger-checkpoint.schema.json"
)
LOG_SCHEMA = (
    ROOT / "schemas" / "credential-revocation-checkpoint-log.schema.json"
)
CORPUS_SCHEMA = (
    ROOT / "schemas" / "checkpoint-bound-revocation-corpus.schema.json"
)
REPORT_SCHEMA = (
    ROOT
    / "schemas"
    / "credential-revocation-checkpoint-verification.schema.json"
)
FINAL_SCHEMA = ROOT / "schemas" / "checkpoint-gated-revocation-final.schema.json"


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
                ":revocation-checkpoint-completion",
                ":revocation-checkpoint-terminal-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic checkpoint final failure")
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def policy(
    document: dict[str, Any] | None = None,
) -> CredentialRevocationCheckpointPolicySnapshot:
    return CredentialRevocationCheckpointPolicySnapshot.from_document(
        document or load_document(CHECKPOINT_POLICY_PATH)
    )


def checkpoint(
    document: dict[str, Any] | None = None,
) -> CredentialRevocationLedgerCheckpointSnapshot:
    return CredentialRevocationLedgerCheckpointSnapshot.from_document(
        document or load_document(CHECKPOINT_PATH)
    )


def checkpoint_log(
    document: dict[str, Any] | None = None,
) -> CredentialRevocationCheckpointLogSnapshot:
    return CredentialRevocationCheckpointLogSnapshot.from_document(
        document or load_document(CHECKPOINT_LOG_PATH)
    )


def checkpoint_corpus(
    document: dict[str, Any] | None = None,
) -> CheckpointBoundRevocationCorpusSnapshot:
    return CheckpointBoundRevocationCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def validate_schema(path: Path, document: dict[str, Any]) -> None:
    Draft202012Validator(
        load_document(path),
        format_checker=FormatChecker(),
    ).validate(document)


def stored_ref(reference: StoredArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def versioned_ref(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


def population_hash(refs: list[dict[str, str]]) -> str:
    return canonical_sha256({"event_refs": refs})


def prepare_checkpoint_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
) -> tuple[Any, ...]:
    prepared = prepare_revocation_store(
        tmp_path,
        store=store,
        evaluated_at="2026-08-03T02:35:00Z",
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
        predecessor,
        bound_ledger,
        _,
        fixture_analyzers,
    ) = prepared
    bound_corpus = checkpoint_corpus()
    plan = experiment_plan(
        candidate,
        bound_corpus.corpus.corpus.corpus,
        fixture_analyzers,
    )
    persist_checkpoint_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=bound_corpus,
        predecessor_corpus=predecessor,
        policy=policy(),
        log=checkpoint_log(),
        ledger=bound_ledger,
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T02:35:00Z",
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
        bound_corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    runtime_registry: Any | None = None,
    run_id: str = "checkpoint-run-001",
    evaluated_at: str = "2026-08-03T02:35:00Z",
):
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
        bound_corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
    ) = prepared
    runner = CheckpointGatedRevocationExperimentRunner(
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
        checkpoint_policy=policy(),
        checkpoint_log=checkpoint_log(),
        checkpoints=(checkpoint(),),
        corpus=bound_corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        checkpoint_verified_at=evaluated_at,
        revocation_evaluated_at=evaluated_at,
        credential_evaluated_at=evaluated_at,
        quality_evaluated_at=evaluated_at,
        review_evaluated_at=evaluated_at,
    )
    return receipt, artifact_store


def rebuild_chain(
    *,
    first_refs: list[dict[str, str]],
    second_refs: list[dict[str, str]],
    second_sequence: int = 1,
    correct_predecessor: bool = True,
    second_published_at: str = "2026-08-03T02:33:00Z",
) -> tuple[
    CheckpointBoundRevocationCorpusSnapshot,
    CredentialRevocationCheckpointLogSnapshot,
    tuple[CredentialRevocationLedgerCheckpointSnapshot, ...],
]:
    first_document = load_document(CHECKPOINT_PATH)
    first_document.update(
        {
            "artifact_id": (
                "credential-revocation-checkpoint:"
                "checkpoint.synthetic.test-chain.0000"
            ),
            "checkpoint_id": "checkpoint.synthetic.test-chain.0000",
            "event_refs": first_refs,
            "event_count": len(first_refs),
            "event_population_hash": population_hash(first_refs),
            "published_at": "2026-08-03T02:32:00Z",
        }
    )
    first = checkpoint(first_document)

    second_document = deepcopy(first_document)
    second_document.update(
        {
            "artifact_id": (
                "credential-revocation-checkpoint:"
                "checkpoint.synthetic.test-chain.0001"
            ),
            "checkpoint_id": "checkpoint.synthetic.test-chain.0001",
            "sequence_number": second_sequence,
            "event_refs": second_refs,
            "event_count": len(second_refs),
            "event_population_hash": population_hash(second_refs),
            "predecessor_checkpoint_ref": (
                stored_ref(first.reference())
                if correct_predecessor
                else {
                    "artifact_id": "credential-revocation-checkpoint:wrong",
                    "artifact_hash": "sha256:" + "0" * 64,
                    "canonicalization_version": "ctrt-canonical-json@0.1.0",
                    "media_type": "application/json",
                }
            ),
            "published_at": second_published_at,
        }
    )
    second = checkpoint(second_document)
    records = (first, second)
    log_document = load_document(CHECKPOINT_LOG_PATH)
    log_document.update(
        {
            "log_id": "log.synthetic-credential-revocation-checkpoints.test",
            "log_version": "0.1.1-test",
            "checkpoint_refs": [
                stored_ref(item.reference()) for item in records
            ],
            "head_checkpoint_ref": stored_ref(second.reference()),
            "created_at": "2026-08-03T02:34:00Z",
        }
    )
    bound_log = checkpoint_log(log_document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": "corpus.synthetic-three-items.checkpoint-bound.test",
            "corpus_version": "0.7.1-test",
            "credential_revocation_checkpoint_log_ref": versioned_ref(
                bound_log.reference()
            ),
            "credential_revocation_checkpoint_head_ref": stored_ref(
                second.reference()
            ),
            "created_at": "2026-08-03T02:34:30Z",
        }
    )
    return checkpoint_corpus(corpus_document), bound_log, records


def test_checkpoint_gate_executes_and_validates_schemas(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is CheckpointGatedRunnerStatus.VERIFIED
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.verified_checks == CHECKPOINT_GATED_VERIFIED_CHECKS
    assert receipt.revocation_receipt is not None

    validate_schema(POLICY_SCHEMA, load_document(CHECKPOINT_POLICY_PATH))
    validate_schema(CHECKPOINT_SCHEMA, load_document(CHECKPOINT_PATH))
    validate_schema(LOG_SCHEMA, load_document(CHECKPOINT_LOG_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    report = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.checkpoint_verification_ref.artifact_id,
                expected_hash=receipt.checkpoint_verification_ref.artifact_hash,
            ).text
        ),
    )
    validate_schema(REPORT_SCHEMA, report)
    assert report["checkpoint_count"] == 1
    assert report["head_event_count"] == 1

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
    assert "aggregate_score" not in final
    assert "transparency_service" not in final


def test_checkpoint_gate_preserves_revocation_abstention(
    tmp_path: Path,
) -> None:
    receipt, store = execute(
        tmp_path,
        run_id="checkpoint-run-suspended",
        evaluated_at="2027-01-02T00:00:00Z",
    )

    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.revocation_receipt.credentialed_receipt is None
    store.get(receipt.checkpoint_verification_ref.artifact_id)
    with pytest.raises(ArtifactNotFoundError):
        store.get("checkpoint-run-suspended:reviewer-credential-decision")


def test_checkpoint_ingestion_and_execution_are_idempotent(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.checkpoint_refs == second.checkpoint_refs
    assert first.checkpoint_verification_ref == (
        second.checkpoint_verification_ref
    )
    assert first.final_manifest_ref == second.final_manifest_ref


def test_checkpoint_storage_reconstructs_exact_population(
    tmp_path: Path,
) -> None:
    prepared = prepare_checkpoint_store(tmp_path)
    store = prepared[0]
    evidence = load_credential_revocation_checkpoint_evidence(
        store,
        corpus=checkpoint_corpus(),
        policy=policy(),
        log=checkpoint_log(),
    )

    assert evidence.checkpoints == (checkpoint(),)
    assert evidence.checkpoint_refs == (checkpoint().reference(),)


@pytest.mark.parametrize(
    ("second_sequence", "correct_predecessor", "match"),
    (
        (2, True, "contiguous"),
        (1, False, "immediate predecessor"),
    ),
)
def test_sequence_gap_and_broken_predecessor_fail(
    second_sequence: int,
    correct_predecessor: bool,
    match: str,
) -> None:
    event_ref = stored_ref(revocation_events()[0].reference())
    bound_corpus, bound_log, records = rebuild_chain(
        first_refs=[event_ref],
        second_refs=[event_ref],
        second_sequence=second_sequence,
        correct_predecessor=correct_predecessor,
    )
    plan = experiment_plan(
        candidate_registry(),
        bound_corpus.corpus.corpus.corpus,
        analyzers(),
    )

    with pytest.raises(CredentialRevocationCheckpointError, match=match):
        validate_credential_revocation_checkpoints(
            plan=plan,
            corpus=bound_corpus,
            policy=policy(),
            log=bound_log,
            ledger=revocation_ledger(),
            checkpoints=records,
            verified_at="2026-08-03T02:35:00Z",
        )


@pytest.mark.parametrize("mode", ("omission", "reordering"))
def test_omission_reordering_and_rollback_fail(mode: str) -> None:
    event_ref = stored_ref(revocation_events()[0].reference())
    fake_ref = {
        "artifact_id": "credential-revocation-event:synthetic-extra",
        "artifact_hash": "sha256:" + "1" * 64,
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }
    second_refs = (
        [event_ref]
        if mode == "omission"
        else [fake_ref, event_ref]
    )
    bound_corpus, bound_log, records = rebuild_chain(
        first_refs=[event_ref, fake_ref],
        second_refs=second_refs,
    )
    plan = experiment_plan(
        candidate_registry(),
        bound_corpus.corpus.corpus.corpus,
        analyzers(),
    )

    with pytest.raises(
        CredentialRevocationCheckpointError,
        match="preserve prior order",
    ):
        validate_credential_revocation_checkpoints(
            plan=plan,
            corpus=bound_corpus,
            policy=policy(),
            log=bound_log,
            ledger=revocation_ledger(),
            checkpoints=records,
            verified_at="2026-08-03T02:35:00Z",
        )


def test_future_checkpoint_publication_fails() -> None:
    event_ref = stored_ref(revocation_events()[0].reference())
    bound_corpus, bound_log, records = rebuild_chain(
        first_refs=[event_ref],
        second_refs=[event_ref],
        second_published_at="2030-01-01T00:00:00Z",
    )
    plan = experiment_plan(
        candidate_registry(),
        bound_corpus.corpus.corpus.corpus,
        analyzers(),
    )

    with pytest.raises(
        CredentialRevocationCheckpointError,
        match="before publication",
    ):
        validate_credential_revocation_checkpoints(
            plan=plan,
            corpus=bound_corpus,
            policy=policy(),
            log=bound_log,
            ledger=revocation_ledger(),
            checkpoints=records,
            verified_at="2026-08-03T02:35:00Z",
        )


def test_checkpoint_head_must_match_current_ledger() -> None:
    document = load_document(CHECKPOINT_PATH)
    fake_ref = {
        "artifact_id": "credential-revocation-event:wrong",
        "artifact_hash": "sha256:" + "2" * 64,
        "canonicalization_version": "ctrt-canonical-json@0.1.0",
        "media_type": "application/json",
    }
    document.update(
        {
            "event_refs": [fake_ref],
            "event_count": 1,
            "event_population_hash": population_hash([fake_ref]),
        }
    )
    wrong = checkpoint(document)
    log_document = load_document(CHECKPOINT_LOG_PATH)
    log_document.update(
        {
            "log_id": "log.synthetic-checkpoint-head-mismatch",
            "log_version": "0.1.1-test",
            "checkpoint_refs": [stored_ref(wrong.reference())],
            "head_checkpoint_ref": stored_ref(wrong.reference()),
        }
    )
    wrong_log = checkpoint_log(log_document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": "corpus.synthetic.checkpoint-head-mismatch",
            "corpus_version": "0.7.1-test-head",
            "credential_revocation_checkpoint_log_ref": versioned_ref(
                wrong_log.reference()
            ),
            "credential_revocation_checkpoint_head_ref": stored_ref(
                wrong.reference()
            ),
        }
    )
    bound_corpus = checkpoint_corpus(corpus_document)
    plan = experiment_plan(
        candidate_registry(),
        bound_corpus.corpus.corpus.corpus,
        analyzers(),
    )

    with pytest.raises(
        CredentialRevocationCheckpointError,
        match="event order differs",
    ):
        validate_credential_revocation_checkpoints(
            plan=plan,
            corpus=bound_corpus,
            policy=policy(),
            log=wrong_log,
            ledger=revocation_ledger(),
            checkpoints=(wrong,),
            verified_at="2026-08-03T02:35:00Z",
        )


def test_unknown_checkpoint_fields_fail_schema_and_parser() -> None:
    document = load_document(CHECKPOINT_PATH)
    document["event_total"] = 1

    with pytest.raises(ValidationError):
        validate_schema(CHECKPOINT_SCHEMA, document)
    with pytest.raises(
        CredentialRevocationCheckpointError,
        match="unsupported fields",
    ):
        checkpoint(document)


def test_missing_stored_checkpoint_fails_before_revocation(
    tmp_path: Path,
) -> None:
    target = checkpoint().artifact_id
    store = CheckpointReadFailsStore(tmp_path / "artifacts", target)
    prepared = prepare_checkpoint_store(tmp_path, store=store)
    store.fail_enabled = True
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        issuer_rules,
        credential_rules,
        bound_corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
    ) = prepared
    runner = CheckpointGatedRevocationExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=artifact_store,
    )

    with pytest.raises(CheckpointGatedExperimentError) as caught:
        runner.run(
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
            checkpoint_policy=policy(),
            checkpoint_log=checkpoint_log(),
            checkpoints=(checkpoint(),),
            corpus=bound_corpus,
            environment=environment(),
            windows=windows(),
            experiment_run_id="checkpoint-run-missing",
            checkpoint_verified_at="2026-08-03T02:35:00Z",
            revocation_evaluated_at="2026-08-03T02:35:00Z",
            credential_evaluated_at="2026-08-03T02:35:00Z",
            quality_evaluated_at="2026-08-03T02:35:00Z",
            review_evaluated_at="2026-08-03T02:35:00Z",
        )

    assert caught.value.stage is CheckpointGatedRunnerStage.CHECKPOINT_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("checkpoint-run-missing:credential-revocation-decision")


def test_downstream_failure_preserves_checkpoint_report_and_partial_progress(
    tmp_path: Path,
) -> None:
    prepared = prepare_checkpoint_store(tmp_path)
    fixture_analyzers = prepared[-1]
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(
            base=fixture_analyzers[0],
            fail_content_id="content-002",
        ),
        *fixture_analyzers[1:],
    )
    with pytest.raises(CheckpointGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=prepared[0],
            runtime_registry=runtime_registry,
            run_id="checkpoint-run-downstream-failure",
        )

    assert caught.value.stage is CheckpointGatedRunnerStage.REVOCATION_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    prepared[0].get(
        "checkpoint-run-downstream-failure:"
        "credential-revocation-checkpoint-verification"
    )
    with pytest.raises(ArtifactNotFoundError):
        prepared[0].get(
            "checkpoint-run-downstream-failure:"
            "revocation-checkpoint-completion"
        )


def test_final_persistence_failure_preserves_prior_verified_artifacts(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")
    with pytest.raises(CheckpointGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            run_id="checkpoint-run-final-failure",
        )

    assert caught.value.stage is CheckpointGatedRunnerStage.FINAL_PERSISTENCE
    store.get(
        "checkpoint-run-final-failure:"
        "credential-revocation-checkpoint-verification"
    )
    store.get("checkpoint-run-final-failure:revocation-ledger-completion")
    with pytest.raises(ArtifactNotFoundError):
        store.get(
            "checkpoint-run-final-failure:"
            "revocation-checkpoint-completion"
        )
