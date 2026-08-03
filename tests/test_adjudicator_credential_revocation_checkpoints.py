# ruff: noqa: I001
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    CheckpointBoundAdjudicatorRevocationCorpusSnapshot,
    load_adjudicator_credential_revocation_checkpoint_evidence,
    persist_checkpoint_bound_adjudicator_revocation_corpus,
    validate_adjudicator_credential_revocation_checkpoints,
)
from ctrt.artifact_store import ArtifactNotFoundError, FileSystemArtifactStore
from ctrt.checkpoint_gated_adjudicator_revocation_runner import (
    ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS,
    AdjudicatorCheckpointGatedRunnerStatus,
    CheckpointGatedAdjudicatorRevocationExperimentRunner,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import canonical_sha256
from test_adjudicator_credential_attestation import (
    credential_policy,
    issuer_registry,
    load_document,
)
from test_adjudicator_credential_revocation_ledger import (
    plan_for,
    prepare_revocation_store,
    revocation_corpus,
    revocation_ledger,
    revocation_policy,
)
from test_credential_revocation_checkpoints import (
    checkpoint as reviewer_checkpoint,
    checkpoint_log as reviewer_checkpoint_log,
    policy as reviewer_checkpoint_policy,
    validate_schema,
)
from test_credential_revocation_ledger import policy as reviewer_revocation_policy
from test_extraction_review_adjudication import (
    analyzer_registry,
    environment,
    windows,
)
from test_witness_conflict_adjudication import (
    adjudication_policy,
    adjudicator_registry,
    witness_policy,
    witness_registry,
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-witness-conflict-adjudicator-revocation-checkpoint-policy.v0.1.0.json"
)
CHECKPOINT_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "checkpoints"
    / "adjudicator-revocation-genesis-checkpoint.json"
)
LOG_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "checkpoints"
    / "adjudicator-revocation-checkpoint-log.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.2.0.json"
)
POLICY_SCHEMA = (
    ROOT
    / "schemas"
    / "adjudicator-credential-revocation-checkpoint-policy.schema.json"
)
CHECKPOINT_SCHEMA = (
    ROOT
    / "schemas"
    / "adjudicator-credential-revocation-ledger-checkpoint.schema.json"
)
LOG_SCHEMA = (
    ROOT
    / "schemas"
    / "adjudicator-credential-revocation-checkpoint-log.schema.json"
)
CORPUS_SCHEMA = (
    ROOT / "schemas" / "adjudicator-revocation-checkpoint-bound-corpus.schema.json"
)
REPORT_SCHEMA = (
    ROOT
    / "schemas"
    / "adjudicator-credential-revocation-checkpoint-verification.schema.json"
)
FINAL_SCHEMA = (
    ROOT / "schemas" / "adjudicator-checkpoint-gated-revocation-final.schema.json"
)


def checkpoint_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationCheckpointPolicySnapshot:
    return AdjudicatorCredentialRevocationCheckpointPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def checkpoint(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationLedgerCheckpointSnapshot:
    return AdjudicatorCredentialRevocationLedgerCheckpointSnapshot.from_document(
        document or load_document(CHECKPOINT_PATH)
    )


def checkpoint_log(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationCheckpointLogSnapshot:
    return AdjudicatorCredentialRevocationCheckpointLogSnapshot.from_document(
        document or load_document(LOG_PATH)
    )


def checkpoint_corpus(
    document: dict[str, Any] | None = None,
) -> CheckpointBoundAdjudicatorRevocationCorpusSnapshot:
    return CheckpointBoundAdjudicatorRevocationCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def stored_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def event_population_hash(refs: list[dict[str, str]]) -> str:
    return canonical_sha256({"event_refs": refs})


def verify(
    *,
    bound_corpus: CheckpointBoundAdjudicatorRevocationCorpusSnapshot | None = None,
    policy: AdjudicatorCredentialRevocationCheckpointPolicySnapshot | None = None,
    log: AdjudicatorCredentialRevocationCheckpointLogSnapshot | None = None,
    ledger: Any | None = None,
    checkpoints: tuple[
        AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
    ] | None = None,
    verified_at: str = "2026-08-03T14:54:00Z",
):
    corpus = bound_corpus or checkpoint_corpus()
    return validate_adjudicator_credential_revocation_checkpoints(
        plan=plan_for(corpus.corpus),
        corpus=corpus,
        policy=policy or checkpoint_policy(),
        log=log or checkpoint_log(),
        ledger=ledger or revocation_ledger(),
        checkpoints=checkpoints if checkpoints is not None else (checkpoint(),),
        verified_at=verified_at,
    )


def prepare_checkpoint_store(tmp_path: Path) -> tuple[Any, ...]:
    prepared = prepare_revocation_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    corpus = checkpoint_corpus()
    plan = replace(
        prepared[9],
        corpus_ref=corpus.reference(),
        content_ids=corpus.content_ids,
    )
    persist_checkpoint_bound_adjudicator_revocation_corpus(
        store,
        plan=plan,
        corpus=corpus,
        predecessor_corpus=revocation_corpus(),
        policy=checkpoint_policy(),
        log=checkpoint_log(),
        ledger=revocation_ledger(),
        checkpoints=(checkpoint(),),
        verified_at="2026-08-03T14:54:00Z",
    )
    return (*prepared, plan, corpus)


def execute_checkpoint(
    tmp_path: Path,
    *,
    revocation_evaluated_at: str,
    run_id: str,
):
    prepared = prepare_checkpoint_store(tmp_path)
    (
        store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        reviewer_issuers,
        reviewer_credentials,
        reviewer_ledger,
        _,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
        attestation,
        _,
        plan,
        corpus,
    ) = prepared
    runner = CheckpointGatedAdjudicatorRevocationExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=store,
    )
    receipt = runner.run(
        plan=plan,
        candidate_registry=candidate,
        method_registry=methods,
        quality_policy=quality,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        issuer_registry=reviewer_issuers,
        credential_policy=reviewer_credentials,
        revocation_policy=reviewer_revocation_policy(),
        ledger=reviewer_ledger,
        checkpoint_policy=reviewer_checkpoint_policy(),
        checkpoint_log=reviewer_checkpoint_log(),
        checkpoints=(reviewer_checkpoint(),),
        witness_registry=witness_registry(),
        witness_policy=witness_policy(),
        witness_attestations=witness_records,
        adjudicator_registry=adjudicator_registry(),
        adjudication_policy=adjudication_policy(),
        adjudication=bound_adjudication,
        adjudicator_issuer_registry=issuer_registry(),
        adjudicator_credential_policy=credential_policy(),
        adjudicator_credentials=(attestation,),
        adjudicator_revocation_policy=revocation_policy(),
        adjudicator_revocation_ledger=revocation_ledger(),
        adjudicator_checkpoint_policy=checkpoint_policy(),
        adjudicator_checkpoint_log=checkpoint_log(),
        adjudicator_checkpoints=(checkpoint(),),
        corpus=corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        adjudicator_checkpoint_verified_at="2026-08-03T14:54:00Z",
        adjudicator_revocation_evaluated_at=revocation_evaluated_at,
        adjudicator_credential_evaluated_at="2026-08-03T14:00:00Z",
        checkpoint_verified_at="2026-08-03T14:00:00Z",
        witness_evaluated_at="2026-08-03T14:00:00Z",
        adjudication_evaluated_at="2026-08-03T14:00:00Z",
        revocation_evaluated_at="2026-08-03T14:00:00Z",
        credential_evaluated_at="2026-08-03T14:00:00Z",
        quality_evaluated_at="2026-08-03T14:00:00Z",
        review_evaluated_at="2026-08-03T14:00:00Z",
    )
    return receipt, store


def test_fixed_checkpoint_graph_and_schemas() -> None:
    report = verify()
    assert report.checkpoint_count == 1
    assert report.head_sequence_number == 0
    assert report.head_event_count == 1
    assert report.head_checkpoint_ref == checkpoint().reference()

    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(CHECKPOINT_SCHEMA, load_document(CHECKPOINT_PATH))
    validate_schema(LOG_SCHEMA, load_document(LOG_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))


def test_pre_effective_execution_preserves_checkpoint_report(tmp_path: Path) -> None:
    receipt, store = execute_checkpoint(
        tmp_path,
        revocation_evaluated_at="2026-08-03T14:00:00Z",
        run_id="adjudicator-checkpoint-pre-effective",
    )
    assert receipt.status is AdjudicatorCheckpointGatedRunnerStatus.VERIFIED
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.adjudicator_credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.verified_checks == ADJUDICATOR_CHECKPOINT_GATED_VERIFIED_CHECKS

    report = cast(
        dict[str, Any],
        json.loads(store.get(receipt.checkpoint_verification_ref.artifact_id).text),
    )
    validate_schema(REPORT_SCHEMA, report)
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)


def test_post_effective_abstention_still_preserves_checkpoint_report(
    tmp_path: Path,
) -> None:
    receipt, store = execute_checkpoint(
        tmp_path,
        revocation_evaluated_at="2027-01-01T00:00:00Z",
        run_id="adjudicator-checkpoint-post-effective",
    )
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.adjudicator_credential_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert store.get(receipt.checkpoint_verification_ref.artifact_id)
    assert receipt.revocation_receipt.credentialed_adjudicator_receipt is None


def test_non_contiguous_sequence_is_rejected() -> None:
    document = load_document(CHECKPOINT_PATH)
    document["sequence_number"] = 1
    changed = checkpoint(document)
    log_document = load_document(LOG_PATH)
    log_document["checkpoint_refs"] = [stored_ref_document(changed.reference())]
    log_document["head_checkpoint_ref"] = stored_ref_document(changed.reference())
    changed_log = checkpoint_log(log_document)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="contiguous",
    ):
        verify(log=changed_log, checkpoints=(changed,))


def test_genesis_predecessor_is_rejected() -> None:
    document = load_document(CHECKPOINT_PATH)
    document["predecessor_checkpoint_ref"] = stored_ref_document(
        checkpoint().reference()
    )
    changed = checkpoint(document)
    log_document = load_document(LOG_PATH)
    log_document["checkpoint_refs"] = [stored_ref_document(changed.reference())]
    log_document["head_checkpoint_ref"] = stored_ref_document(changed.reference())
    changed_log = checkpoint_log(log_document)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="Genesis|genesis",
    ):
        verify(log=changed_log, checkpoints=(changed,))


def test_checkpoint_omission_is_rejected() -> None:
    document = load_document(CHECKPOINT_PATH)
    document["event_refs"] = []
    document["event_count"] = 0
    document["event_population_hash"] = event_population_hash([])
    changed = checkpoint(document)
    log_document = load_document(LOG_PATH)
    log_document["checkpoint_refs"] = [stored_ref_document(changed.reference())]
    log_document["head_checkpoint_ref"] = stored_ref_document(changed.reference())
    changed_log = checkpoint_log(log_document)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="event order|event count",
    ):
        verify(log=changed_log, checkpoints=(changed,))


def test_stale_ledger_reference_is_rejected() -> None:
    document = load_document(CHECKPOINT_PATH)
    document["revocation_ledger_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed = checkpoint(document)
    log_document = load_document(LOG_PATH)
    log_document["checkpoint_refs"] = [stored_ref_document(changed.reference())]
    log_document["head_checkpoint_ref"] = stored_ref_document(changed.reference())
    changed_log = checkpoint_log(log_document)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="ledger reference",
    ):
        verify(log=changed_log, checkpoints=(changed,))


def test_future_checkpoint_verification_is_rejected() -> None:
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="before publication",
    ):
        verify(verified_at="2026-08-03T14:50:59Z")


def test_two_checkpoint_chain_requires_immediate_predecessor() -> None:
    second_document = load_document(CHECKPOINT_PATH)
    second_document.update(
        {
            "artifact_id": (
                "adjudicator-credential-revocation-checkpoint:"
                "checkpoint.synthetic.witness-conflict-adjudicator-revocations.0001"
            ),
            "checkpoint_id": (
                "checkpoint.synthetic.witness-conflict-adjudicator-revocations.0001"
            ),
            "sequence_number": 1,
            "predecessor_checkpoint_ref": None,
            "published_at": "2026-08-03T14:52:00Z",
        }
    )
    second = checkpoint(second_document)
    log_document = load_document(LOG_PATH)
    log_document["checkpoint_refs"] = [
        stored_ref_document(checkpoint().reference()),
        stored_ref_document(second.reference()),
    ]
    log_document["head_checkpoint_ref"] = stored_ref_document(second.reference())
    log_document["created_at"] = "2026-08-03T14:53:00Z"
    changed_log = checkpoint_log(log_document)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="immediate predecessor",
    ):
        verify(log=changed_log, checkpoints=(checkpoint(), second))


def test_non_increasing_publication_time_is_rejected() -> None:
    second_document = load_document(CHECKPOINT_PATH)
    second_document.update(
        {
            "artifact_id": (
                "adjudicator-credential-revocation-checkpoint:"
                "checkpoint.synthetic.witness-conflict-adjudicator-revocations.0001"
            ),
            "checkpoint_id": (
                "checkpoint.synthetic.witness-conflict-adjudicator-revocations.0001"
            ),
            "sequence_number": 1,
            "predecessor_checkpoint_ref": stored_ref_document(
                checkpoint().reference()
            ),
            "published_at": "2026-08-03T14:51:00Z",
        }
    )
    second = checkpoint(second_document)
    log_document = load_document(LOG_PATH)
    log_document["checkpoint_refs"] = [
        stored_ref_document(checkpoint().reference()),
        stored_ref_document(second.reference()),
    ]
    log_document["head_checkpoint_ref"] = stored_ref_document(second.reference())
    log_document["created_at"] = "2026-08-03T14:53:00Z"
    changed_log = checkpoint_log(log_document)
    with pytest.raises(
        AdjudicatorCredentialRevocationCheckpointError,
        match="publication time",
    ):
        verify(log=changed_log, checkpoints=(checkpoint(), second))


def test_storage_reconstruction_is_idempotent(tmp_path: Path) -> None:
    prepared = prepare_checkpoint_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    first = load_adjudicator_credential_revocation_checkpoint_evidence(
        store,
        corpus=checkpoint_corpus(),
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    second = load_adjudicator_credential_revocation_checkpoint_evidence(
        store,
        corpus=checkpoint_corpus(),
        policy=checkpoint_policy(),
        log=checkpoint_log(),
    )
    assert first == second
    assert first.checkpoints == (checkpoint(),)


def test_missing_checkpoint_fails_loading(tmp_path: Path) -> None:
    prepared = prepare_checkpoint_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    reference = checkpoint().reference()
    store._blob_path(reference.artifact_hash).unlink()
    with pytest.raises(ArtifactNotFoundError):
        load_adjudicator_credential_revocation_checkpoint_evidence(
            store,
            corpus=checkpoint_corpus(),
            policy=checkpoint_policy(),
            log=checkpoint_log(),
        )


def test_closed_contracts_reject_score_or_consensus_fields() -> None:
    for field in ("trust_score", "vote_count", "consensus_percentage"):
        policy_document = deepcopy(load_document(POLICY_PATH))
        policy_document[field] = 1
        with pytest.raises(
            AdjudicatorCredentialRevocationCheckpointError,
            match="unsupported",
        ):
            checkpoint_policy(policy_document)

        checkpoint_document = deepcopy(load_document(CHECKPOINT_PATH))
        checkpoint_document[field] = 1
        with pytest.raises(
            AdjudicatorCredentialRevocationCheckpointError,
            match="unsupported",
        ):
            checkpoint(checkpoint_document)


def test_schema_rejects_extra_score_field() -> None:
    document = deepcopy(load_document(CHECKPOINT_PATH))
    document["confidence"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(CHECKPOINT_SCHEMA, document)
