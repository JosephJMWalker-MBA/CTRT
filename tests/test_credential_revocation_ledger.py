# ruff: noqa: I001
from __future__ import annotations

import json
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
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_credentialed_runner import (
    REVOCATION_GATED_VERIFIED_CHECKS,
    RevocationGatedCredentialedExtractionExperimentRunner,
    RevocationGatedExperimentError,
    RevocationGatedRunnerStage,
    RevocationGatedRunnerStatus,
)
from ctrt.serialization import CanonicalArtifact
from test_extraction_review_adjudication import (
    FailOnContentAnalyzer,
    analyzer_registry,
    analyzers,
    candidate_registry,
    environment,
    experiment_plan,
    review_snapshots,
    reviewer_registry,
    windows,
)
from test_reviewer_credential_attestation import (
    credential_policy,
    credential_snapshots,
    issuer_registry,
    load_document,
    prepare_store as prepare_credential_store,
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = (
    ROOT / "docs" / "candidates" / "synthetic-credential-revocation-policy.v0.1.0.json"
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
            (":revocation-ledger-completion", ":credential-revocation-abstention")
        ):
            raise ArtifactIntegrityError("synthetic revocation final failure")
        return super().append(artifact)


def policy() -> CredentialRevocationPolicySnapshot:
    return CredentialRevocationPolicySnapshot.from_document(load_document(POLICY_PATH))


def events() -> tuple[CredentialRevocationEventSnapshot, ...]:
    return (CredentialRevocationEventSnapshot.from_document(load_document(EVENT_PATH)),)


def ledger(document: dict[str, Any] | None = None) -> CredentialRevocationLedgerSnapshot:
    return CredentialRevocationLedgerSnapshot.from_document(
        document or load_document(LEDGER_PATH)
    )


def corpus(
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


def prepare(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    frozen_corpus: RevocationBoundCredentialCorpusSnapshot | None = None,
    frozen_ledger: CredentialRevocationLedgerSnapshot | None = None,
    event_records: tuple[CredentialRevocationEventSnapshot, ...] | None = None,
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
    bound_corpus = frozen_corpus or corpus()
    bound_ledger = frozen_ledger or ledger()
    records = event_records or events()
    plan = experiment_plan(candidate, bound_corpus.corpus.corpus, fixture_analyzers)
    persist_revocation_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=bound_corpus,
        predecessor_corpus=predecessor,
        reviewer_registry=reviewers,
        issuer_registry=issuer_rules,
        credential_policy=credential_rules,
        revocation_policy=policy(),
        ledger=bound_ledger,
        attestations=credential_snapshots(),
        adjudications=review_snapshots(),
        events=records,
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
        bound_corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    frozen_corpus: RevocationBoundCredentialCorpusSnapshot | None = None,
    frozen_ledger: CredentialRevocationLedgerSnapshot | None = None,
    event_records: tuple[CredentialRevocationEventSnapshot, ...] | None = None,
    runtime_registry: Any | None = None,
    run_id: str = "revocation-run-001",
    evaluated_at: str = "2026-08-03T02:04:00Z",
):
    prepared = prepare(
        tmp_path,
        store=store,
        frozen_corpus=frozen_corpus,
        frozen_ledger=frozen_ledger,
        event_records=event_records,
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
        bound_corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
    ) = prepared
    runner = RevocationGatedCredentialedExtractionExperimentRunner(
        analyzer_registry=runtime_registry or analyzer_registry(*fixture_analyzers),
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
        revocation_policy=policy(),
        ledger=bound_ledger,
        corpus=bound_corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        revocation_evaluated_at=evaluated_at,
        credential_evaluated_at=evaluated_at,
        quality_evaluated_at=evaluated_at,
        review_evaluated_at=evaluated_at,
    )
    return receipt, artifact_store


def superseding_graph(
    *,
    supersedes: str = "event.synthetic.secondary.suspension-2027",
    effective_at: str = "2027-02-01T00:00:00Z",
    issuer_id: str = "issuer.synthetic-reviewer-credentials",
    suffix: str = "reinstated",
) -> tuple[
    RevocationBoundCredentialCorpusSnapshot,
    CredentialRevocationLedgerSnapshot,
    tuple[CredentialRevocationEventSnapshot, ...],
]:
    first = events()[0]
    document = load_document(EVENT_PATH)
    document.update(
        {
            "artifact_id": f"credential-revocation-event:event.synthetic.secondary.{suffix}",
            "event_id": f"event.synthetic.secondary.{suffix}",
            "issuer_id": issuer_id,
            "effect": "active",
            "effective_at": effective_at,
            "recorded_at": "2026-08-03T02:05:00Z",
            "reason": "Synthetic superseding credential event.",
            "supersedes_event_id": supersedes,
        }
    )
    second = CredentialRevocationEventSnapshot.from_document(document)
    records = (first, second)
    ledger_document = load_document(LEDGER_PATH)
    ledger_document.update(
        {
            "ledger_id": f"ledger.synthetic-reviewer-credential-revocations.{suffix}",
            "ledger_version": f"0.1.1-test-{suffix}",
            "event_refs": [stored_ref(item.reference()) for item in records],
            "created_at": "2026-08-03T02:06:00Z",
        }
    )
    bound_ledger = ledger(ledger_document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": f"corpus.synthetic-three-items.revocation-bound.{suffix}",
            "corpus_version": f"0.6.1-test-{suffix}",
            "credential_revocation_ledger_ref": versioned_ref(bound_ledger.reference()),
            "created_at": "2026-08-03T02:07:00Z",
        }
    )
    return corpus(corpus_document), bound_ledger, records


def test_future_event_executes_and_validates_schemas(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)
    assert receipt.status is RevocationGatedRunnerStatus.VERIFIED
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.credentialed_receipt is not None
    assert receipt.verified_checks == REVOCATION_GATED_VERIFIED_CHECKS

    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(EVENT_SCHEMA, load_document(EVENT_PATH))
    validate_schema(LEDGER_SCHEMA, load_document(LEDGER_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision)
    assert decision["credentials"][1]["effective_status"] == "active"
    assert decision["credentials"][1]["applied_event_ids"] == []
    final = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final)
    assert "aggregate_score" not in final


def test_effective_suspension_abstains_before_downstream(tmp_path: Path) -> None:
    run_id = "revocation-run-suspended"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        evaluated_at="2027-01-02T00:00:00Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.credentialed_receipt is None
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    secondary = decision["credentials"][1]
    assert secondary["effective_status"] == "suspended"
    assert secondary["applied_event_ids"] == [
        "event.synthetic.secondary.suspension-2027"
    ]
    for artifact_id in (
        f"{run_id}:reviewer-credential-decision",
        f"{run_id}:review-adjudication-decision",
        f"{run_id}:extraction-quality-decision",
        f"{run_id}:experiment-completion",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(artifact_id)


def test_superseding_active_event_restores_without_erasing_history(
    tmp_path: Path,
) -> None:
    bound_corpus, bound_ledger, records = superseding_graph()
    receipt, store = execute(
        tmp_path,
        frozen_corpus=bound_corpus,
        frozen_ledger=bound_ledger,
        event_records=records,
        run_id="revocation-run-reinstated",
        evaluated_at="2027-03-01T00:00:00Z",
    )
    assert receipt.revocation_outcome is CredentialDecisionOutcome.EXECUTE
    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    secondary = decision["credentials"][1]
    assert secondary["effective_status"] == "active"
    assert secondary["applied_event_ids"] == [
        "event.synthetic.secondary.suspension-2027",
        "event.synthetic.secondary.reinstated",
    ]
    for record in records:
        store.get(record.reference().artifact_id)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"supersedes": "event.synthetic.missing", "suffix": "broken"}, "immediately prior"),
        ({"effective_at": "2026-12-01T00:00:00Z", "suffix": "early"}, "precedes prior"),
        ({"issuer_id": "issuer.synthetic.unauthorized", "suffix": "issuer"}, "issuer identity"),
    ),
)
def test_invalid_event_chains_fail(kwargs: dict[str, str], message: str) -> None:
    bound_corpus, bound_ledger, records = superseding_graph(**kwargs)
    plan = experiment_plan(candidate_registry(), bound_corpus.corpus.corpus, analyzers())
    with pytest.raises(CredentialRevocationError, match=message):
        validate_credential_revocation_ledger(
            plan=plan,
            corpus=bound_corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            revocation_policy=policy(),
            ledger=bound_ledger,
            attestations=credential_snapshots(),
            adjudications=review_snapshots(),
            events=records,
            evaluated_at="2027-03-01T00:00:00Z",
        )


def test_unknown_fields_are_rejected() -> None:
    document = load_document(EVENT_PATH)
    document["legal_name"] = "Private Person"
    document["vote_count"] = 3
    with pytest.raises(ValidationError):
        validate_schema(EVENT_SCHEMA, document)
    with pytest.raises(CredentialRevocationError, match="unsupported fields"):
        CredentialRevocationEventSnapshot.from_document(document)


def test_missing_event_fails_before_decision(tmp_path: Path) -> None:
    prepared = prepare(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    bound_ledger = cast(CredentialRevocationLedgerSnapshot, prepared[9])
    failing_store = EventReadFailsStore(
        store.root,
        bound_ledger.event_refs[0].artifact_id,
    )
    runner = RevocationGatedCredentialedExtractionExperimentRunner(
        analyzer_registry=analyzer_registry(*cast(tuple[Any, ...], prepared[11])),
        artifact_store=failing_store,
    )
    with pytest.raises(RevocationGatedExperimentError) as caught:
        runner.run(
            plan=prepared[10],
            candidate_registry=prepared[1],
            method_registry=prepared[2],
            quality_policy=prepared[3],
            reviewer_registry=prepared[4],
            review_policy=prepared[5],
            issuer_registry=prepared[6],
            credential_policy=prepared[7],
            revocation_policy=policy(),
            ledger=prepared[9],
            corpus=prepared[8],
            environment=environment(),
            windows=windows(),
            experiment_run_id="revocation-run-missing",
            revocation_evaluated_at="2026-08-03T02:04:00Z",
            credential_evaluated_at="2026-08-03T02:04:00Z",
            quality_evaluated_at="2026-08-03T02:04:00Z",
            review_evaluated_at="2026-08-03T02:04:00Z",
        )
    assert caught.value.stage is RevocationGatedRunnerStage.EVIDENCE_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("revocation-run-missing:credential-revocation-decision")


def test_downstream_failure_preserves_revocation_decision(tmp_path: Path) -> None:
    first, last = analyzers()
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run_id = "revocation-run-downstream-failure"
    with pytest.raises(RevocationGatedExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=analyzer_registry(
                FailOnContentAnalyzer(first, "content-002"),
                last,
            ),
            run_id=run_id,
        )
    assert caught.value.stage is RevocationGatedRunnerStage.CREDENTIALED_EXECUTION
    assert caught.value.completed_content_ids == ("content-001",)
    store.get(f"{run_id}:credential-revocation-decision")
    store.get(f"{run_id}:0000:content-001:governed-session:receipt")


def test_final_persistence_failure_returns_no_receipt(tmp_path: Path) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")
    with pytest.raises(RevocationGatedExperimentError) as caught:
        execute(tmp_path, store=store)
    assert caught.value.stage is RevocationGatedRunnerStage.FINAL_PERSISTENCE
    store.get("revocation-run-001:credential-revocation-decision")
    with pytest.raises(ArtifactNotFoundError):
        store.get("revocation-run-001:revocation-ledger-completion")


def test_storage_reconstructs_exact_event_population(tmp_path: Path) -> None:
    prepared = prepare(tmp_path)
    evidence = load_credential_revocation_evidence(
        prepared[0],
        corpus=prepared[8],
        policy=policy(),
        ledger=prepared[9],
    )
    assert evidence.events == events()
    assert evidence.event_refs == prepared[9].event_refs
