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
from ctrt.credential_revocation_ledger import (
    CredentialRevocationError,
    CredentialRevocationEventSnapshot,
    CredentialRevocationLedgerSnapshot,
    CredentialRevocationPolicySnapshot,
    RevocationBoundCredentialCorpusSnapshot,
    load_credential_revocation_evidence,
    persist_revocation_bound_corpus,
    validate_credential_revocation_ledger,
)
from ctrt.reviewer_credential_attestation import (
    CredentialAttestationStatus,
    CredentialDecisionOutcome,
)
from ctrt.revocation_gated_credentialed_runner import (
    REVOCATION_GATED_VERIFIED_CHECKS,
    RevocationGatedCredentialedExtractionExperimentRunner,
    RevocationGatedExperimentError,
    RevocationGatedRunnerStage,
    RevocationGatedRunnerStatus,
)
from ctrt.serialization import CanonicalArtifact
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from test_extraction_review_adjudication import (
    FailOnContentAnalyzer,
    analyzer_registry,
    analyzers,
    candidate_registry,
    environment,
    experiment_plan,
    method_registry,
    quality_policy,
    review_policy,
    review_snapshots,
    reviewer_registry,
    windows,
)
from test_reviewer_credential_attestation import (
    credential_corpus,
    credential_policy,
    credential_snapshots,
    issuer_registry,
    load_document,
    prepare_store as prepare_credential_store,
)

ROOT = Path(__file__).parents[1]
REVOCATION_POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-credential-revocation-policy.v0.1.0.json"
)
EVENT_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "secondary-suspension-2027.json"
)
LEDGER_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "synthetic-ledger.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.6.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / "credential-revocation-policy.schema.json"
EVENT_SCHEMA = ROOT / "schemas" / "credential-revocation-event.schema.json"
LEDGER_SCHEMA = ROOT / "schemas" / "credential-revocation-ledger.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "revocation-bound-credential-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "credential-revocation-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "revocation-gated-credentialed-final.schema.json"


class EventReadFailsStore(FileSystemArtifactStore):
    def __init__(self, root: Path, artifact_id: str) -> None:
        super().__init__(root)
        self._artifact_id = artifact_id

    def get(
        self,
        artifact_id: str,
        *,
        expected_hash: str | None = None,
    ) -> CanonicalArtifact:
        if artifact_id == self._artifact_id:
            raise ArtifactIntegrityError("synthetic revocation event read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":revocation-ledger-completion",
                ":credential-revocation-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic revocation final failure")
        return super().append(artifact)


def revocation_policy() -> CredentialRevocationPolicySnapshot:
    return CredentialRevocationPolicySnapshot.from_document(
        load_document(REVOCATION_POLICY_PATH)
    )


def revocation_events() -> tuple[CredentialRevocationEventSnapshot, ...]:
    return (
        CredentialRevocationEventSnapshot.from_document(
            load_document(EVENT_PATH)
        ),
    )


def revocation_ledger(
    document: dict[str, Any] | None = None,
) -> CredentialRevocationLedgerSnapshot:
    return CredentialRevocationLedgerSnapshot.from_document(
        document or load_document(LEDGER_PATH)
    )


def revocation_corpus(
    document: dict[str, Any] | None = None,
) -> RevocationBoundCredentialCorpusSnapshot:
    return RevocationBoundCredentialCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def validate_schema(path: Path, document: dict[str, Any]) -> None:
    Draft202012Validator(
        load_document(path),
        format_checker=FormatChecker(),
    ).validate(document)


def stored_ref_document(reference: StoredArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


def versioned_ref_document(reference: Any) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_version": reference.artifact_version,
        "artifact_hash": reference.artifact_hash,
    }


def prepare_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    corpus: RevocationBoundCredentialCorpusSnapshot | None = None,
    ledger: CredentialRevocationLedgerSnapshot | None = None,
    events: tuple[CredentialRevocationEventSnapshot, ...] | None = None,
    evaluated_at: str = "2026-08-03T02:04:00Z",
) -> tuple[Any, ...]:
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
        _,
        fixture_analyzers,
    ) = prepare_credential_store(tmp_path, store=store)
    frozen_corpus = corpus or revocation_corpus()
    frozen_ledger = ledger or revocation_ledger()
    event_records = events or revocation_events()
    plan = experiment_plan(candidate, frozen_corpus.corpus.corpus, fixture_analyzers)
    persist_revocation_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=frozen_corpus,
        predecessor_corpus=predecessor,
        reviewer_registry=reviewers,
        issuer_registry=issuer_rules,
        credential_policy=credential_rules,
        revocation_policy=revocation_policy(),
        ledger=frozen_ledger,
        attestations=credential_snapshots(),
        adjudications=review_snapshots(),
        events=event_records,
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
        frozen_corpus,
        frozen_ledger,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    corpus: RevocationBoundCredentialCorpusSnapshot | None = None,
    ledger: CredentialRevocationLedgerSnapshot | None = None,
    events: tuple[CredentialRevocationEventSnapshot, ...] | None = None,
    runtime_registry: Any | None = None,
    run_id: str = "revocation-run-001",
    evaluated_at: str = "2026-08-03T02:04:00Z",
):
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        issuer_rules,
        credential_rules,
        frozen_corpus,
        frozen_ledger,
        plan,
        fixture_analyzers,
    ) = prepare_store(
        tmp_path,
        store=store,
        corpus=corpus,
        ledger=ledger,
        events=events,
        evaluated_at=evaluated_at,
    )
    runner = RevocationGatedCredentialedExtractionExperimentRunner(
        analyzer_registry=(
            runtime_registry or analyzer_registry(*fixture_analyzers)
        ),
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
        ledger=frozen_ledger,
        corpus=frozen_corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        revocation_evaluated_at=evaluated_at,
        credential_evaluated_at=evaluated_at,
        quality_evaluated_at=evaluated_at,
        review_evaluated_at=evaluated_at,
    )
    return receipt, artifact_store


def build_superseding_case(
    *,
    effect: str = "active",
    effective_at: str = "2027-02-01T00:00:00Z",
    supersedes_event_id: str = "event.synthetic.secondary.suspension-2027",
    issuer_id: str = "issuer.synthetic-reviewer-credentials",
    issuer_revision: str = "synthetic-issuer@0.1.0",
    suffix: str = "reinstated",
) -> tuple[
    RevocationBoundCredentialCorpusSnapshot,
    CredentialRevocationLedgerSnapshot,
    tuple[CredentialRevocationEventSnapshot, ...],
]:
    first = revocation_events()[0]
    document = load_document(EVENT_PATH)
    document.update(
        {
            "artifact_id": (
                "credential-revocation-event:"
                f"event.synthetic.secondary.{suffix}"
            ),
            "event_id": f"event.synthetic.secondary.{suffix}",
            "issuer_id": issuer_id,
            "issuer_revision": issuer_revision,
            "effect": effect,
            "effective_at": effective_at,
            "recorded_at": "2026-08-03T02:05:00Z",
            "reason": "Synthetic superseding credential event.",
            "supersedes_event_id": supersedes_event_id,
        }
    )
    second = CredentialRevocationEventSnapshot.from_document(document)
    records = (first, second)

    ledger_document = load_document(LEDGER_PATH)
    ledger_document["ledger_id"] = (
        f"ledger.synthetic-reviewer-credential-revocations.{suffix}"
    )
    ledger_document["ledger_version"] = f"0.1.1-test-{suffix}"
    ledger_document["event_refs"] = [
        stored_ref_document(item.reference()) for item in records
    ]
    ledger_document["created_at"] = "2026-08-03T02:06:00Z"
    ledger = revocation_ledger(ledger_document)

    corpus_document = load_document(CORPUS_PATH)
    corpus_document["corpus_id"] = (
        f"corpus.synthetic-three-items.revocation-bound.{suffix}"
    )
    corpus_document["corpus_version"] = f"0.6.1-test-{suffix}"
    corpus_document["credential_revocation_ledger_ref"] = (
        versioned_ref_document(ledger.reference())
    )
    corpus_document["created_at"] = "2026-08-03T02:07:00Z"
    return revocation_corpus(corpus_document), ledger, records


def test_future_event_is_ignored_and_execution_validates_schemas(
    tmp_path: Path,
) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is RevocationGatedRunnerStatus.VERIFIED
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.credentialed_receipt is not None
    assert receipt.verified_checks == REVOCATION_GATED_VERIFIED_CHECKS

    validate_schema(POLICY_SCHEMA, load_document(REVOCATION_POLICY_PATH))
    validate_schema(EVENT_SCHEMA, load_document(EVENT_PATH))
    validate_schema(LEDGER_SCHEMA, load_document(LEDGER_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    decision = store.get(
        receipt.revocation_decision_ref.artifact_id,
        expected_hash=receipt.revocation_decision_ref.artifact_hash,
    )
    decision_document = cast(dict[str, Any], json.loads(decision.text))
    validate_schema(DECISION_SCHEMA, decision_document)
    secondary = decision_document["credentials"][1]
    assert secondary["effective_status"] == "active"
    assert secondary["applied_event_ids"] == []
    assert secondary["effective_event_id"] is None

    final = store.get(
        receipt.final_manifest_ref.artifact_id,
        expected_hash=receipt.final_manifest_ref.artifact_hash,
    )
    final_document = cast(dict[str, Any], json.loads(final.text))
    validate_schema(FINAL_SCHEMA, final_document)
    assert final_document["revocation_outcome"] == "execute"
    assert final_document["terminal_outcome"] == "execute"
    assert "aggregate_score" not in final_document


def test_revocation_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.revocation_event_refs == second.revocation_event_refs
    assert first.revocation_decision_ref == second.revocation_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


def test_effective_suspension_abstains_before_downstream_execution(
    tmp_path: Path,
) -> None:
    run_id = "revocation-run-suspended"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        evaluated_at="2027-01-02T00:00:00Z",
    )

    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credentialed_receipt is None
    decision = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.revocation_decision_ref.artifact_id,
                expected_hash=receipt.revocation_decision_ref.artifact_hash,
            ).text
        ),
    )
    secondary = decision["credentials"][1]
    assert secondary["effective_status"] == "suspended"
    assert secondary["applied_event_ids"] == [
        "event.synthetic.secondary.suspension-2027"
    ]
    assert secondary["abstention"]["reasons"] == [
        "credential-ledger-status:suspended"
    ]
    for artifact_id in (
        f"{run_id}:reviewer-credential-decision",
        f"{run_id}:review-adjudication-decision",
        f"{run_id}:extraction-quality-decision",
        f"{run_id}:0000:content-001:governed-session:receipt",
        f"{run_id}:experiment-completion",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(artifact_id)


def test_superseding_active_event_restores_execution_without_erasing_history(
    tmp_path: Path,
) -> None:
    corpus, ledger, records = build_superseding_case()
    receipt, store = execute(
        tmp_path,
        corpus=corpus,
        ledger=ledger,
        events=records,
        run_id="revocation-run-reinstated",
        evaluated_at="2027-03-01T00:00:00Z",
    )

    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.credentialed_receipt is not None
    decision = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.revocation_decision_ref.artifact_id,
                expected_hash=receipt.revocation_decision_ref.artifact_hash,
            ).text
        ),
    )
    secondary = decision["credentials"][1]
    assert secondary["base_status"] == "active"
    assert secondary["effective_status"] == "active"
    assert secondary["applied_event_ids"] == [
        "event.synthetic.secondary.suspension-2027",
        "event.synthetic.secondary.reinstated",
    ]
    assert secondary["effective_event_id"] == (
        "event.synthetic.secondary.reinstated"
    )
    assert secondary["abstention"] == {"triggered": False, "reasons": []}
    for record in records:
        store.get(
            record.reference().artifact_id,
            expected_hash=record.reference().artifact_hash,
        )


def test_broken_supersession_chain_fails_validation() -> None:
    corpus, ledger, records = build_superseding_case(
        supersedes_event_id="event.synthetic.missing",
        suffix="broken-chain",
    )
    plan = experiment_plan(candidate_registry(), corpus.corpus.corpus, analyzers())

    with pytest.raises(CredentialRevocationError, match="immediately prior"):
        validate_credential_revocation_ledger(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=ledger,
            attestations=credential_snapshots(),
            adjudications=review_snapshots(),
            events=records,
            evaluated_at="2027-03-01T00:00:00Z",
        )


def test_non_monotonic_effective_time_fails_validation() -> None:
    corpus, ledger, records = build_superseding_case(
        effective_at="2026-12-01T00:00:00Z",
        suffix="non-monotonic",
    )
    plan = experiment_plan(candidate_registry(), corpus.corpus.corpus, analyzers())

    with pytest.raises(CredentialRevocationError, match="precedes prior"):
        validate_credential_revocation_ledger(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=ledger,
            attestations=credential_snapshots(),
            adjudications=review_snapshots(),
            events=records,
            evaluated_at="2027-03-01T00:00:00Z",
        )


def test_event_issuer_must_match_attestation_issuer() -> None:
    corpus, ledger, records = build_superseding_case(
        issuer_id="issuer.synthetic.unauthorized",
        suffix="wrong-issuer",
    )
    plan = experiment_plan(candidate_registry(), corpus.corpus.corpus, analyzers())

    with pytest.raises(CredentialRevocationError, match="issuer identity"):
        validate_credential_revocation_ledger(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=ledger,
            attestations=credential_snapshots(),
            adjudications=review_snapshots(),
            events=records,
            evaluated_at="2027-03-01T00:00:00Z",
        )


def test_unknown_attestation_reference_fails_validation() -> None:
    document = load_document(EVENT_PATH)
    document["event_id"] = "event.synthetic.unknown-attestation"
    document["artifact_id"] = (
        "credential-revocation-event:event.synthetic.unknown-attestation"
    )
    document["credential_attestation_ref"]["artifact_hash"] = (
        "sha256:" + "0" * 64
    )
    event = CredentialRevocationEventSnapshot.from_document(document)
    ledger_document = load_document(LEDGER_PATH)
    ledger_document["ledger_id"] += ".unknown-attestation"
    ledger_document["ledger_version"] = "0.1.1-test-unknown-attestation"
    ledger_document["event_refs"] = [stored_ref_document(event.reference())]
    ledger = revocation_ledger(ledger_document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document["corpus_id"] += ".unknown-attestation"
    corpus_document["corpus_version"] = "0.6.1-test-unknown-attestation"
    corpus_document["credential_revocation_ledger_ref"] = (
        versioned_ref_document(ledger.reference())
    )
    corpus = revocation_corpus(corpus_document)
    plan = experiment_plan(candidate_registry(), corpus.corpus.corpus, analyzers())

    with pytest.raises(CredentialRevocationError, match="reference is unknown"):
        validate_credential_revocation_ledger(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            revocation_policy=revocation_policy(),
            ledger=ledger,
            attestations=credential_snapshots(),
            adjudications=review_snapshots(),
            events=(event,),
            evaluated_at="2027-01-02T00:00:00Z",
        )


def test_private_or_vote_fields_are_rejected() -> None:
    document = load_document(EVENT_PATH)
    document["legal_name"] = "Private Person"
    document["vote_count"] = 3

    with pytest.raises(ValidationError):
        validate_schema(EVENT_SCHEMA, document)
    with pytest.raises(CredentialRevocationError, match="unsupported fields"):
        CredentialRevocationEventSnapshot.from_document(document)


def test_missing_stored_event_fails_before_decision(tmp_path: Path) -> None:
    prepared = prepare_store(tmp_path)
    (
        store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        issuer_rules,
        credential_rules,
        corpus,
        ledger,
        plan,
        fixture_analyzers,
    ) = prepared
    failing_store = EventReadFailsStore(
        store.root,
        ledger.event_refs[0].artifact_id,
    )
    runner = RevocationGatedCredentialedExtractionExperimentRunner(
        analyzer_registry=analyzer_registry(*fixture_analyzers),
        artifact_store=failing_store,
    )

    with pytest.raises(RevocationGatedExperimentError) as caught:
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
            ledger=ledger,
            corpus=corpus,
            environment=environment(),
            windows=windows(),
            experiment_run_id="revocation-run-missing-event",
            revocation_evaluated_at="2026-08-03T02:04:00Z",
            credential_evaluated_at="2026-08-03T02:04:00Z",
            quality_evaluated_at="2026-08-03T02:04:00Z",
            review_evaluated_at="2026-08-03T02:04:00Z",
        )

    assert caught.value.stage is RevocationGatedRunnerStage.EVIDENCE_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("revocation-run-missing-event:credential-revocation-decision")


def test_later_analyzer_failure_preserves_revocation_decision_and_receipt(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run_id = "revocation-run-analyzer-failure"

    with pytest.raises(RevocationGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=runtime_registry,
            run_id=run_id,
        )

    assert caught.value.stage is RevocationGatedRunnerStage.CREDENTIALED_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    store.get(f"{run_id}:credential-revocation-decision")
    store.get(f"{run_id}:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:revocation-ledger-completion")


def test_final_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(RevocationGatedExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is RevocationGatedRunnerStage.FINAL_PERSISTENCE
    store.get("revocation-run-001:credential-revocation-decision")
    with pytest.raises(ArtifactNotFoundError):
        store.get("revocation-run-001:revocation-ledger-completion")


def test_stored_revocation_evidence_reconstructs_exact_events(
    tmp_path: Path,
) -> None:
    prepared = prepare_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    corpus = cast(RevocationBoundCredentialCorpusSnapshot, prepared[8])
    ledger = cast(CredentialRevocationLedgerSnapshot, prepared[9])
    evidence = load_credential_revocation_evidence(
        store,
        corpus=corpus,
        policy=revocation_policy(),
        ledger=ledger,
    )

    assert evidence.events == revocation_events()
    assert evidence.event_refs == ledger.event_refs
    assert evidence.revocation_ledger_ref.artifact_hash == ledger.artifact_hash
