# ruff: noqa: I001, F401, UP035
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundAdjudicatorCredentialCorpusSnapshot,
    load_adjudicator_credential_revocation_evidence,
    persist_adjudicator_credential_revocation_bound_corpus,
    validate_adjudicator_credential_revocation_ledger,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.revocation_gated_adjudicated_witness_runner import (
    ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS,
    AdjudicatorRevocationGatedExperimentError,
    AdjudicatorRevocationGatedRunnerStage,
    AdjudicatorRevocationGatedRunnerStatus,
    RevocationGatedAdjudicatedWitnessExperimentRunner,
)
from ctrt.serialization import CanonicalArtifact
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from test_adjudicator_credential_attestation import (
    credential,
    credential_corpus,
    credential_policy,
    issuer_registry,
    load_document,
    prepare_credentialed_store,
)
from test_credential_revocation_checkpoints import (
    checkpoint,
    checkpoint_log,
    policy as checkpoint_policy,
    validate_schema,
)
from test_credential_revocation_ledger import policy as reviewer_revocation_policy
from test_extraction_review_adjudication import (
    FailOnContentAnalyzer,
    analyzer_registry,
    analyzers,
    environment,
    experiment_plan,
    windows,
)
from test_witness_conflict_adjudication import (
    adjudication,
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
    / "synthetic-witness-conflict-adjudicator-credential-revocation-policy.v0.1.0.json"
)
EVENT_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-fork-suspension-event.json"
)
LEDGER_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-credential-revocation-ledger.v0.1.0.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.1.0.json"
)
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-policy.schema.json"
EVENT_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-event.schema.json"
LEDGER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-ledger.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-bound-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-revocation-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "adjudicator-revocation-gated-final.schema.json"


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":adjudicator-credential-revocation-abstention",
                ":adjudicator-credential-revocation-completion",
                ":adjudicator-credential-revocation-terminal-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic adjudicator revocation final failure")
        return super().append(artifact)


def revocation_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationPolicySnapshot:
    return AdjudicatorCredentialRevocationPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def suspension_event(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationEventSnapshot:
    return AdjudicatorCredentialRevocationEventSnapshot.from_document(
        document or load_document(EVENT_PATH)
    )


def revocation_ledger(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialRevocationLedgerSnapshot:
    return AdjudicatorCredentialRevocationLedgerSnapshot.from_document(
        document or load_document(LEDGER_PATH)
    )


def revocation_corpus(
    document: dict[str, Any] | None = None,
) -> RevocationBoundAdjudicatorCredentialCorpusSnapshot:
    return RevocationBoundAdjudicatorCredentialCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def plan_for(corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot):
    return experiment_plan(
        cast(Any, __import__("test_extraction_review_adjudication").candidate_registry()),
        corpus.corpus.corpus.corpus.corpus.corpus.corpus.corpus,
        analyzers(),
    )


def validate(
    *,
    corpus: RevocationBoundAdjudicatorCredentialCorpusSnapshot | None = None,
    policy: AdjudicatorCredentialRevocationPolicySnapshot | None = None,
    ledger: AdjudicatorCredentialRevocationLedgerSnapshot | None = None,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...] | None = None,
    evaluated_at: str = "2026-08-03T14:00:00Z",
):
    bound = corpus or revocation_corpus()
    return validate_adjudicator_credential_revocation_ledger(
        plan=plan_for(bound),
        corpus=bound,
        adjudicator_registry=adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        revocation_policy=policy or revocation_policy(),
        ledger=ledger or revocation_ledger(),
        attestations=(credential(),),
        adjudication=adjudication(),
        events=events if events is not None else (suspension_event(),),
        evaluated_at=evaluated_at,
    )


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


def rebuilt_case(
    *,
    events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
    suffix: str,
) -> tuple[
    RevocationBoundAdjudicatorCredentialCorpusSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
]:
    ledger_document = load_document(LEDGER_PATH)
    ledger_document.update(
        {
            "ledger_id": (
                "ledger.synthetic-witness-conflict-adjudicator-credential-"
                f"revocations.{suffix}"
            ),
            "ledger_version": f"0.1.1-test-{suffix}",
            "event_refs": [stored_ref_document(item.reference()) for item in events],
            "created_at": "2026-08-03T13:49:00Z",
        }
    )
    bound_ledger = revocation_ledger(ledger_document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": (
                "corpus.synthetic-three-items.adjudicator-credential-"
                f"revocation-bound.{suffix}"
            ),
            "corpus_version": f"1.1.1-test-{suffix}",
            "created_at": "2026-08-03T13:49:30Z",
            "adjudicator_credential_revocation_ledger_ref": (
                versioned_ref_document(bound_ledger.reference())
            ),
        }
    )
    return revocation_corpus(corpus_document), bound_ledger


def prepare_revocation_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
) -> tuple[Any, ...]:
    prepared = prepare_credentialed_store(tmp_path, store=store)
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        reviewer_issuers,
        reviewer_credentials,
        _,
        bound_reviewer_ledger,
        _,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
        attestation,
    ) = prepared
    corpus = revocation_corpus()
    plan = experiment_plan(
        candidate,
        corpus.corpus.corpus.corpus.corpus.corpus.corpus.corpus,
        fixture_analyzers,
    )
    persist_adjudicator_credential_revocation_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=corpus,
        predecessor_corpus=credential_corpus(),
        adjudicator_registry=adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        revocation_policy=revocation_policy(),
        ledger=revocation_ledger(),
        attestations=(attestation,),
        adjudication=bound_adjudication,
        events=(suspension_event(),),
        evaluated_at="2026-08-03T14:00:00Z",
    )
    return (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        reviewer_issuers,
        reviewer_credentials,
        bound_reviewer_ledger,
        plan,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
        attestation,
        corpus,
    )


def execute(
    tmp_path: Path,
    *,
    evaluated_at: str,
    run_id: str,
    store: FileSystemArtifactStore | None = None,
    runtime_registry: Any | None = None,
):
    prepared = prepare_revocation_store(tmp_path, store=store)
    (
        artifact_store,
        candidate,
        methods,
        quality,
        reviewers,
        review_rules,
        reviewer_issuers,
        reviewer_credentials,
        bound_reviewer_ledger,
        plan,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
        attestation,
        corpus,
    ) = prepared
    runner = RevocationGatedAdjudicatedWitnessExperimentRunner(
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
        issuer_registry=reviewer_issuers,
        credential_policy=reviewer_credentials,
        revocation_policy=reviewer_revocation_policy(),
        ledger=bound_reviewer_ledger,
        checkpoint_policy=checkpoint_policy(),
        checkpoint_log=checkpoint_log(),
        checkpoints=(checkpoint(),),
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
        corpus=corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        adjudicator_revocation_evaluated_at=evaluated_at,
        adjudicator_credential_evaluated_at="2026-08-03T14:00:00Z",
        checkpoint_verified_at="2026-08-03T14:00:00Z",
        witness_evaluated_at="2026-08-03T14:00:00Z",
        adjudication_evaluated_at="2026-08-03T14:00:00Z",
        revocation_evaluated_at="2026-08-03T14:00:00Z",
        credential_evaluated_at="2026-08-03T14:00:00Z",
        quality_evaluated_at="2026-08-03T14:00:00Z",
        review_evaluated_at="2026-08-03T14:00:00Z",
    )
    return receipt, artifact_store


def test_fixed_graph_and_pre_effective_execution(tmp_path: Path) -> None:
    decision = validate()
    assert decision.outcome is CredentialDecisionOutcome.EXECUTE
    assert decision.credentials[0].base_status.value == "active"
    assert decision.credentials[0].effective_status.value == "active"
    assert decision.credentials[0].applied_event_ids == ()
    assert decision.credentials[0].effective_event_id is None

    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(EVENT_SCHEMA, load_document(EVENT_PATH))
    validate_schema(LEDGER_SCHEMA, load_document(LEDGER_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    receipt, store = execute(
        tmp_path,
        evaluated_at="2026-08-03T14:00:00Z",
        run_id="adjudicator-revocation-pre-effective",
    )
    assert receipt.status is AdjudicatorRevocationGatedRunnerStatus.VERIFIED
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.adjudicator_credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.verified_checks == ADJUDICATOR_REVOCATION_GATED_VERIFIED_CHECKS

    decision_document = cast(
        dict[str, Any],
        json.loads(store.get(receipt.revocation_decision_ref.artifact_id).text),
    )
    validate_schema(DECISION_SCHEMA, decision_document)
    final_document = cast(
        dict[str, Any],
        json.loads(store.get(receipt.final_manifest_ref.artifact_id).text),
    )
    validate_schema(FINAL_SCHEMA, final_document)


def test_post_effective_suspension_abstains_before_downstream(tmp_path: Path) -> None:
    decision = validate(evaluated_at="2027-01-01T00:00:00Z")
    summary = decision.credentials[0]
    assert decision.outcome is CredentialDecisionOutcome.ABSTAIN
    assert summary.effective_status.value == "suspended"
    assert summary.applied_event_ids == ("event.synthetic.fork.suspension.v0.1.0",)
    assert summary.effective_event_id == "event.synthetic.fork.suspension.v0.1.0"
    assert summary.abstention.reasons == (
        "adjudicator-credential-ledger-status:suspended",
    )

    run_id = "adjudicator-revocation-post-effective"
    receipt, store = execute(
        tmp_path,
        evaluated_at="2027-01-01T00:00:00Z",
        run_id=run_id,
    )
    assert receipt.adjudicator_revocation_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.adjudicator_credential_outcome is None
    assert receipt.witness_outcome is None
    assert receipt.adjudication_outcome is None
    assert receipt.reviewer_revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.credentialed_adjudicator_receipt is None
    for suffix in (
        "adjudicator-credential-decision",
        "credential-revocation-checkpoint-verification",
        "checkpoint-witness-decision",
        "witness-conflict-adjudication-decision",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(f"{run_id}:{suffix}")


def test_superseding_reinstatement_preserves_suspension_history() -> None:
    reinstatement_document = load_document(EVENT_PATH)
    reinstatement_document.update(
        {
            "artifact_id": (
                "adjudicator-credential-revocation-event:"
                "event.synthetic.fork.reinstatement.v0.1.0"
            ),
            "event_id": "event.synthetic.fork.reinstatement.v0.1.0",
            "effect": "active",
            "effective_at": "2027-02-01T00:00:00Z",
            "recorded_at": "2026-08-03T13:48:15Z",
            "reason": "Synthetic reinstatement preserving suspension history.",
            "supersedes_event_id": "event.synthetic.fork.suspension.v0.1.0",
        }
    )
    reinstatement = suspension_event(reinstatement_document)
    events = (suspension_event(), reinstatement)
    corpus, ledger = rebuilt_case(events=events, suffix="reinstated")
    decision = validate(
        corpus=corpus,
        ledger=ledger,
        events=events,
        evaluated_at="2027-02-01T00:00:00Z",
    )
    summary = decision.credentials[0]
    assert decision.outcome is CredentialDecisionOutcome.EXECUTE
    assert summary.effective_status.value == "active"
    assert summary.applied_event_ids == (
        "event.synthetic.fork.suspension.v0.1.0",
        "event.synthetic.fork.reinstatement.v0.1.0",
    )
    assert summary.effective_event_id == "event.synthetic.fork.reinstatement.v0.1.0"


def test_broken_linear_supersession_is_rejected() -> None:
    second_document = load_document(EVENT_PATH)
    second_document.update(
        {
            "artifact_id": (
                "adjudicator-credential-revocation-event:"
                "event.synthetic.fork.bad-chain.v0.1.0"
            ),
            "event_id": "event.synthetic.fork.bad-chain.v0.1.0",
            "effect": "active",
            "effective_at": "2027-02-01T00:00:00Z",
            "supersedes_event_id": "event.synthetic.fork.unknown",
        }
    )
    second = suspension_event(second_document)
    events = (suspension_event(), second)
    corpus, ledger = rebuilt_case(events=events, suffix="bad-chain")
    with pytest.raises(AdjudicatorCredentialRevocationError, match="immediately prior"):
        validate(corpus=corpus, ledger=ledger, events=events)


def test_decreasing_effective_time_is_rejected() -> None:
    second_document = load_document(EVENT_PATH)
    second_document.update(
        {
            "artifact_id": (
                "adjudicator-credential-revocation-event:"
                "event.synthetic.fork.time-regression.v0.1.0"
            ),
            "event_id": "event.synthetic.fork.time-regression.v0.1.0",
            "effect": "active",
            "effective_at": "2026-12-31T23:59:59Z",
            "supersedes_event_id": "event.synthetic.fork.suspension.v0.1.0",
        }
    )
    second = suspension_event(second_document)
    events = (suspension_event(), second)
    corpus, ledger = rebuilt_case(events=events, suffix="time-regression")
    with pytest.raises(AdjudicatorCredentialRevocationError, match="precedes prior"):
        validate(corpus=corpus, ledger=ledger, events=events)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("adjudicator_id", "adjudicator.synthetic.other", "adjudicator ID"),
        ("issuer_revision", "synthetic-issuer@9.9.9", "issuer identity"),
    ),
)
def test_identity_or_issuer_drift_is_rejected(
    field: str,
    value: str,
    message: str,
) -> None:
    document = load_document(EVENT_PATH)
    document[field] = value
    changed = suspension_event(document)
    corpus, ledger = rebuilt_case(events=(changed,), suffix=field)
    with pytest.raises(AdjudicatorCredentialRevocationError, match=message):
        validate(corpus=corpus, ledger=ledger, events=(changed,))


def test_unknown_credential_reference_is_rejected() -> None:
    document = load_document(EVENT_PATH)
    document["credential_attestation_ref"]["artifact_hash"] = "sha256:" + "0" * 64
    changed = suspension_event(document)
    corpus, ledger = rebuilt_case(events=(changed,), suffix="unknown-credential")
    with pytest.raises(AdjudicatorCredentialRevocationError, match="unknown"):
        validate(corpus=corpus, ledger=ledger, events=(changed,))


def test_event_population_order_must_match_ledger() -> None:
    reinstatement_document = load_document(EVENT_PATH)
    reinstatement_document.update(
        {
            "artifact_id": (
                "adjudicator-credential-revocation-event:"
                "event.synthetic.fork.population.v0.1.0"
            ),
            "event_id": "event.synthetic.fork.population.v0.1.0",
            "effect": "active",
            "effective_at": "2027-02-01T00:00:00Z",
            "supersedes_event_id": "event.synthetic.fork.suspension.v0.1.0",
        }
    )
    second = suspension_event(reinstatement_document)
    events = (suspension_event(), second)
    corpus, ledger = rebuilt_case(events=events, suffix="population")
    with pytest.raises(AdjudicatorCredentialRevocationError, match="population"):
        validate(corpus=corpus, ledger=ledger, events=tuple(reversed(events)))


def test_closed_event_schema_rejects_private_or_score_fields() -> None:
    for field in ("real_name", "trust_score", "consensus_percentage"):
        document = deepcopy(load_document(EVENT_PATH))
        document[field] = "forbidden"
        with pytest.raises(AdjudicatorCredentialRevocationError, match="unsupported"):
            suspension_event(document)


def test_storage_reconstruction_and_idempotence(tmp_path: Path) -> None:
    prepared = prepare_revocation_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    first = load_adjudicator_credential_revocation_evidence(
        store,
        corpus=revocation_corpus(),
        policy=revocation_policy(),
        ledger=revocation_ledger(),
    )
    second = load_adjudicator_credential_revocation_evidence(
        store,
        corpus=revocation_corpus(),
        policy=revocation_policy(),
        ledger=revocation_ledger(),
    )
    assert first == second
    assert first.events == (suspension_event(),)


def test_missing_stored_event_fails_loading(tmp_path: Path) -> None:
    prepared = prepare_revocation_store(tmp_path)
    store = cast(FileSystemArtifactStore, prepared[0])
    reference = suspension_event().reference()
    store._blob_path(reference.artifact_hash).unlink()
    with pytest.raises(ArtifactNotFoundError):
        load_adjudicator_credential_revocation_evidence(
            store,
            corpus=revocation_corpus(),
            policy=revocation_policy(),
            ledger=revocation_ledger(),
        )


def test_downstream_failure_preserves_revocation_decision(tmp_path: Path) -> None:
    first, last = analyzers()
    runtime = analyzer_registry(
        first,
        FailOnContentAnalyzer(last, "content-002"),
    )
    run_id = "adjudicator-revocation-downstream-failure"
    with pytest.raises(
        AdjudicatorRevocationGatedExperimentError,
        match="credentialed-execution",
    ):
        execute(
            tmp_path,
            evaluated_at="2026-08-03T14:00:00Z",
            run_id=run_id,
            runtime_registry=runtime,
        )
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    assert store.get(f"{run_id}:adjudicator-credential-revocation-decision")
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:adjudicator-credential-revocation-completion")


def test_final_persistence_failure_is_fail_closed(tmp_path: Path) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")
    with pytest.raises(AdjudicatorRevocationGatedExperimentError) as captured:
        execute(
            tmp_path,
            store=store,
            evaluated_at="2027-01-01T00:00:00Z",
            run_id="adjudicator-revocation-final-failure",
        )
    assert captured.value.stage is AdjudicatorRevocationGatedRunnerStage.FINAL_PERSISTENCE
    assert store.get(
        "adjudicator-revocation-final-failure:"
        "adjudicator-credential-revocation-decision"
    )
