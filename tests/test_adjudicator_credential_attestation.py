# ruff: noqa: I001
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from jsonschema import ValidationError

from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialError,
    AdjudicatorCredentialPolicySnapshot,
    CredentialBoundAdjudicationCorpusSnapshot,
    load_adjudicator_credential_evidence,
    persist_credential_bound_adjudication_corpus,
    validate_adjudicator_credential_attestations,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.credentialed_adjudicated_witness_runner import (
    CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS,
    CredentialedAdjudicatedWitnessExperimentRunner,
    CredentialedAdjudicatorExperimentError,
    CredentialedAdjudicatorRunnerStage,
    CredentialedAdjudicatorRunnerStatus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.serialization import CanonicalArtifact
from ctrt.witness_conflict_adjudication import WitnessConflictAdjudicationOutcome
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
    analyzers,
    candidate_registry,
    environment,
    experiment_plan,
    windows,
)
from test_witness_conflict_adjudication import (
    adjudication,
    adjudication_corpus,
    adjudication_policy,
    adjudicator_registry,
    conflict_attestations,
    prepare_adjudicated_store,
    witness_policy,
    witness_registry,
)

ROOT = Path(__file__).parents[1]
ISSUER_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-witness-conflict-adjudicator-credential-issuer-registry.v0.1.0.json"
)
POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-witness-conflict-adjudicator-credential-policy.v0.1.0.json"
)
ATTESTATION_PATH = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "revocations"
    / "witnesses"
    / "adjudicator-fork-credential.json"
)
CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v1.0.0.json"
)
ISSUER_SCHEMA = ROOT / "schemas" / "adjudicator-credential-issuer-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "adjudicator-credential-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-attestation.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "adjudicator-credential-bound-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "adjudicator-credential-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "credentialed-adjudicator-final.schema.json"


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":adjudicator-credential-abstention",
                ":adjudicator-credential-completion",
                ":adjudicator-credential-terminal-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic adjudicator final failure")
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def issuer_registry(
    document: dict[str, Any] | None = None,
) -> CredentialIssuerRegistrySnapshot:
    return CredentialIssuerRegistrySnapshot.from_document(
        document or load_document(ISSUER_PATH)
    )


def credential_policy(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialPolicySnapshot:
    return AdjudicatorCredentialPolicySnapshot.from_document(
        document or load_document(POLICY_PATH)
    )


def credential(
    document: dict[str, Any] | None = None,
) -> AdjudicatorCredentialAttestationSnapshot:
    return AdjudicatorCredentialAttestationSnapshot.from_document(
        document or load_document(ATTESTATION_PATH)
    )


def credential_corpus(
    document: dict[str, Any] | None = None,
) -> CredentialBoundAdjudicationCorpusSnapshot:
    return CredentialBoundAdjudicationCorpusSnapshot.from_document(
        document or load_document(CORPUS_PATH)
    )


def rebuild_credential_case(
    *,
    suffix: str,
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[
    CredentialBoundAdjudicationCorpusSnapshot,
    AdjudicatorCredentialAttestationSnapshot,
]:
    document = load_document(ATTESTATION_PATH)
    mutate(document)
    record = credential(document)
    corpus_document = load_document(CORPUS_PATH)
    corpus_document.update(
        {
            "corpus_id": (
                "corpus.synthetic-three-items.adjudicator-credential-bound."
                f"{suffix}"
            ),
            "corpus_version": f"1.0.1-test-{suffix}",
            "created_at": "2026-08-03T13:08:30Z",
            "witness_conflict_adjudicator_credentials": [
                {
                    "adjudicator_id": record.adjudicator_id,
                    "identity_revision": record.identity_revision,
                    "credential_attestation_ref": {
                        "artifact_id": record.reference().artifact_id,
                        "artifact_hash": record.reference().artifact_hash,
                        "canonicalization_version": (
                            record.reference().canonicalization_version
                        ),
                        "media_type": record.reference().media_type,
                    },
                }
            ],
        }
    )
    return credential_corpus(corpus_document), record


def plan_for(corpus: CredentialBoundAdjudicationCorpusSnapshot):
    return experiment_plan(
        candidate_registry(),
        corpus.corpus.corpus.corpus.corpus.corpus.corpus,
        analyzers(),
    )


def prepare_credentialed_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    bound_corpus: CredentialBoundAdjudicationCorpusSnapshot | None = None,
    bound_credential: AdjudicatorCredentialAttestationSnapshot | None = None,
) -> tuple[Any, ...]:
    prepared = prepare_adjudicated_store(tmp_path, store=store)
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
        bound_ledger,
        _,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
    ) = prepared
    corpus = bound_corpus or credential_corpus()
    attestation = bound_credential or credential()
    plan = experiment_plan(
        candidate,
        corpus.corpus.corpus.corpus.corpus.corpus.corpus,
        fixture_analyzers,
    )
    persist_credential_bound_adjudication_corpus(
        artifact_store,
        plan=plan,
        corpus=corpus,
        predecessor_corpus=adjudication_corpus(),
        adjudicator_registry=adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(attestation,),
        adjudication=bound_adjudication,
        evaluated_at="2026-08-03T13:08:00Z",
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
        corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
        attestation,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    evaluated_at: str = "2026-08-03T13:08:00Z",
    runtime_registry: Any | None = None,
    run_id: str = "adjudicator-credential-run-001",
):
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
        corpus,
        bound_ledger,
        plan,
        fixture_analyzers,
        witness_records,
        bound_adjudication,
        attestation,
    ) = prepared
    runner = CredentialedAdjudicatedWitnessExperimentRunner(
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
        issuer_registry=reviewer_issuers,
        credential_policy=reviewer_credentials,
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
        adjudication=bound_adjudication,
        adjudicator_issuer_registry=issuer_registry(),
        adjudicator_credential_policy=credential_policy(),
        adjudicator_credentials=(attestation,),
        corpus=corpus,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        adjudicator_credential_evaluated_at=evaluated_at,
        checkpoint_verified_at="2026-08-03T13:08:00Z",
        witness_evaluated_at="2026-08-03T13:08:00Z",
        adjudication_evaluated_at="2026-08-03T13:08:00Z",
        revocation_evaluated_at="2026-08-03T13:08:00Z",
        credential_evaluated_at="2026-08-03T13:08:00Z",
        quality_evaluated_at="2026-08-03T13:08:00Z",
        review_evaluated_at="2026-08-03T13:08:00Z",
    )
    return receipt, artifact_store


def test_active_credential_executes_and_preserves_adjudication(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is CredentialedAdjudicatorRunnerStatus.VERIFIED
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.witness_outcome is not None
    assert receipt.adjudication_outcome is WitnessConflictAdjudicationOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.adjudicated_witness_receipt is not None
    assert receipt.verified_checks == CREDENTIALED_ADJUDICATOR_VERIFIED_CHECKS

    validate_schema(ISSUER_SCHEMA, load_document(ISSUER_PATH))
    validate_schema(POLICY_SCHEMA, load_document(POLICY_PATH))
    validate_schema(ATTESTATION_SCHEMA, load_document(ATTESTATION_PATH))
    validate_schema(CORPUS_SCHEMA, load_document(CORPUS_PATH))

    decision = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.credential_decision_ref.artifact_id,
                expected_hash=receipt.credential_decision_ref.artifact_hash,
            ).text
        ),
    )
    validate_schema(DECISION_SCHEMA, decision)
    assert decision["outcome"] == "execute"
    assert decision["credentials"][0]["adjudicator_id"] == (
        "adjudicator.synthetic.fork"
    )
    assert "real_name" not in decision["credentials"][0]

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
    assert final["credential_outcome"] == "execute"
    assert final["adjudication_outcome"] == "execute"


@pytest.mark.parametrize(
    ("evaluated_at", "reason"),
    (
        ("2026-08-03T13:06:59Z", "credential-not-yet-valid"),
        ("2027-08-03T13:07:00Z", "credential-expired"),
    ),
)
def test_time_invalid_credential_abstains_before_downstream(
    tmp_path: Path,
    evaluated_at: str,
    reason: str,
) -> None:
    run_id = f"adjudicator-credential-{reason}"
    receipt, store = execute(
        tmp_path,
        evaluated_at=evaluated_at,
        run_id=run_id,
    )

    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.witness_outcome is None
    assert receipt.adjudication_outcome is None
    assert receipt.revocation_outcome is None
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudicated_witness_receipt is None

    decision = cast(
        dict[str, Any],
        json.loads(store.get(receipt.credential_decision_ref.artifact_id).text),
    )
    assert reason in decision["credentials"][0]["abstention"]["reasons"]
    for suffix in (
        "credential-revocation-checkpoint-verification",
        "checkpoint-witness-decision",
        "witness-conflict-adjudication-decision",
    ):
        with pytest.raises(ArtifactNotFoundError):
            store.get(f"{run_id}:{suffix}")


@pytest.mark.parametrize("status", ("suspended", "revoked"))
def test_inactive_status_produces_credential_abstention(status: str) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["status"] = status
        if status == "revoked":
            document["revoked_at"] = "2026-08-03T13:07:30Z"
            document["revocation_reason"] = "Synthetic governance revocation."

    corpus, attestation = rebuild_credential_case(suffix=status, mutate=mutate)
    decision = validate_adjudicator_credential_attestations(
        plan=plan_for(corpus),
        corpus=corpus,
        adjudicator_registry=adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=(attestation,),
        adjudication=adjudication(),
        evaluated_at="2026-08-03T13:08:00Z",
    )

    assert decision.outcome is CredentialDecisionOutcome.ABSTAIN
    assert decision.credentials[0].abstention.reasons == (
        f"credential-status:{status}",
    )


def test_identity_revision_drift_fails_publication(tmp_path: Path) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["identity_revision"] = "synthetic-adjudicator@9.9.9"
        document["subject_reference"] = (
            "witness-conflict-adjudicator:adjudicator.synthetic.fork@"
            "synthetic-adjudicator@9.9.9"
        )

    corpus, attestation = rebuild_credential_case(suffix="identity-drift", mutate=mutate)
    prepared = prepare_adjudicated_store(tmp_path)
    plan = experiment_plan(
        prepared[1],
        corpus.corpus.corpus.corpus.corpus.corpus.corpus,
        prepared[11],
    )
    with pytest.raises(AdjudicatorCredentialError, match="identity"):
        persist_credential_bound_adjudication_corpus(
            prepared[0],
            plan=plan,
            corpus=corpus,
            predecessor_corpus=adjudication_corpus(),
            adjudicator_registry=adjudicator_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            attestations=(attestation,),
            adjudication=adjudication(),
            evaluated_at="2026-08-03T13:08:00Z",
        )


def test_issuer_revision_drift_fails_structurally() -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["issuer_revision"] = "synthetic-witness-conflict-governance@9.9.9"

    corpus, attestation = rebuild_credential_case(suffix="issuer-drift", mutate=mutate)
    with pytest.raises(AdjudicatorCredentialError, match="issuer revision"):
        validate_adjudicator_credential_attestations(
            plan=plan_for(corpus),
            corpus=corpus,
            adjudicator_registry=adjudicator_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            attestations=(attestation,),
            adjudication=adjudication(),
            evaluated_at="2026-08-03T13:08:00Z",
        )


def test_private_identity_fields_are_rejected() -> None:
    document = load_document(ATTESTATION_PATH)
    document["real_name"] = "Not permitted"
    with pytest.raises(ValidationError):
        validate_schema(ATTESTATION_SCHEMA, document)
    with pytest.raises(AdjudicatorCredentialError, match="unsupported fields"):
        credential(document)


def test_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.credential_decision_ref == second.credential_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


def test_stored_credential_graph_reconstructs_exactly(tmp_path: Path) -> None:
    prepared = prepare_credentialed_store(tmp_path)
    evidence = load_adjudicator_credential_evidence(
        prepared[0],
        corpus=credential_corpus(),
        adjudicator_registry=adjudicator_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        adjudication=adjudication(),
    )

    assert evidence.attestations == (credential(),)
    assert evidence.adjudication_ref == adjudication().reference()


def test_downstream_failure_preserves_credential_evidence(tmp_path: Path) -> None:
    prepared = prepare_credentialed_store(tmp_path)
    fixture_analyzers = prepared[11]
    runtime = analyzer_registry(
        FailOnContentAnalyzer(
            base=fixture_analyzers[0],
            fail_content_id="content-002",
        ),
        *fixture_analyzers[1:],
    )
    run_id = "adjudicator-credential-downstream-failure"
    with pytest.raises(CredentialedAdjudicatorExperimentError) as caught:
        execute(
            tmp_path,
            store=prepared[0],
            runtime_registry=runtime,
            run_id=run_id,
        )

    assert caught.value.stage is (
        CredentialedAdjudicatorRunnerStage.ADJUDICATED_WITNESS_EXECUTION
    )
    assert caught.value.completed_content_ids == ("content-001",)
    prepared[0].get(f"{run_id}:adjudicator-credential-decision")
    with pytest.raises(ArtifactNotFoundError):
        prepared[0].get(f"{run_id}:adjudicator-credential-completion")


def test_final_persistence_failure_preserves_credential_decision(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")
    run_id = "adjudicator-credential-final-failure"
    with pytest.raises(CredentialedAdjudicatorExperimentError) as caught:
        execute(tmp_path, store=store, run_id=run_id)

    assert caught.value.stage is CredentialedAdjudicatorRunnerStage.FINAL_PERSISTENCE
    store.get(f"{run_id}:adjudicator-credential-decision")
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:adjudicator-credential-completion")


def test_policy_and_corpus_reject_vote_or_identity_aggregation_fields() -> None:
    policy_document = load_document(POLICY_PATH)
    policy_document["credential_score"] = 1.0
    with pytest.raises(ValidationError):
        validate_schema(POLICY_SCHEMA, policy_document)
    with pytest.raises(AdjudicatorCredentialError, match="unsupported fields"):
        credential_policy(policy_document)

    corpus_document = deepcopy(load_document(CORPUS_PATH))
    corpus_document["adjudicator_consensus_percentage"] = 100
    parsed = credential_corpus(corpus_document)
    assert parsed.reference().artifact_hash != credential_corpus().reference().artifact_hash
