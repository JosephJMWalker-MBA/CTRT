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
from ctrt.credentialed_adjudicated_extraction_runner import (
    CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS,
    CredentialedAdjudicatedExperimentError,
    CredentialedAdjudicatedExtractionExperimentRunner,
    CredentialedAdjudicatedRunnerStage,
    CredentialedAdjudicatedRunnerStatus,
)
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialAttestationStatus,
    CredentialBoundReviewCorpusSnapshot,
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
    ReviewerCredentialAttestationSnapshot,
    ReviewerCredentialError,
    ReviewerCredentialPolicySnapshot,
    load_reviewer_credential_evidence,
    persist_credential_bound_corpus,
    validate_reviewer_credential_attestations,
)
from ctrt.serialization import CanonicalArtifact
from test_extraction_review_adjudication import (
    FailOnContentAnalyzer,
    analyzer_registry,
    analyzers,
    candidate_registry,
    content_snapshots,
    environment,
    experiment_plan,
    extraction_snapshots,
    method_registry,
    persist_review_bound_corpus,
    quality_policy,
    quality_snapshots,
    review_corpus,
    review_policy,
    review_snapshots,
    reviewer_registry,
    source_snapshots,
    windows,
)

ROOT = Path(__file__).parents[1]
ISSUER_REGISTRY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-reviewer-credential-issuer-registry.v0.1.0.json"
)
CREDENTIAL_POLICY_PATH = (
    ROOT
    / "docs"
    / "candidates"
    / "synthetic-reviewer-credential-policy.v0.1.0.json"
)
PREDECESSOR_CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.4.0.json"
)
CREDENTIAL_CORPUS_PATH = (
    ROOT / "docs" / "corpora" / "extraction" / "synthetic-corpus.v0.5.0.json"
)
ATTESTATION_PATHS = (
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "credentials"
    / "reviewer-primary.json",
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "credentials"
    / "reviewer-secondary.json",
    ROOT
    / "docs"
    / "corpora"
    / "extraction"
    / "credentials"
    / "reviewer-adjudicator.json",
)
ISSUER_SCHEMA = ROOT / "schemas" / "credential-issuer-registry.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "reviewer-credential-policy.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas" / "reviewer-credential-attestation.schema.json"
CORPUS_SCHEMA = ROOT / "schemas" / "credential-bound-review-corpus.schema.json"
DECISION_SCHEMA = ROOT / "schemas" / "reviewer-credential-decision.schema.json"
FINAL_SCHEMA = ROOT / "schemas" / "credentialed-adjudicated-final.schema.json"


class AttestationReadFailsStore(FileSystemArtifactStore):
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
            raise ArtifactIntegrityError("synthetic credential read failure")
        return super().get(artifact_id, expected_hash=expected_hash)


class FinalAppendFailsStore(FileSystemArtifactStore):
    def append(self, artifact: CanonicalArtifact) -> StoredArtifactRef:
        if artifact.artifact_id.endswith(
            (
                ":credential-attested-completion",
                ":credential-attestation-abstention",
            )
        ):
            raise ArtifactIntegrityError("synthetic credential final failure")
        return super().append(artifact)


def load_document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def issuer_registry() -> CredentialIssuerRegistrySnapshot:
    return CredentialIssuerRegistrySnapshot.from_document(
        load_document(ISSUER_REGISTRY_PATH)
    )


def credential_policy() -> ReviewerCredentialPolicySnapshot:
    return ReviewerCredentialPolicySnapshot.from_document(
        load_document(CREDENTIAL_POLICY_PATH)
    )


def credential_corpus(
    document: dict[str, Any] | None = None,
) -> CredentialBoundReviewCorpusSnapshot:
    return CredentialBoundReviewCorpusSnapshot.from_document(
        document or load_document(CREDENTIAL_CORPUS_PATH)
    )


def credential_snapshots() -> tuple[ReviewerCredentialAttestationSnapshot, ...]:
    return tuple(
        ReviewerCredentialAttestationSnapshot.from_document(load_document(path))
        for path in ATTESTATION_PATHS
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


def rebuild_credential_case(
    *,
    index: int,
    mutate: Any,
    corpus_version: str,
) -> tuple[
    CredentialBoundReviewCorpusSnapshot,
    tuple[ReviewerCredentialAttestationSnapshot, ...],
]:
    documents = [load_document(path) for path in ATTESTATION_PATHS]
    changed = deepcopy(documents[index])
    mutate(changed)
    changed["attestation_id"] = f"{changed['attestation_id']}.{corpus_version}"
    changed["artifact_id"] = f"reviewer-credential:{changed['attestation_id']}"
    documents[index] = changed
    attestations = tuple(
        ReviewerCredentialAttestationSnapshot.from_document(document)
        for document in documents
    )

    corpus_document = load_document(CREDENTIAL_CORPUS_PATH)
    corpus_document["corpus_version"] = corpus_version
    corpus_document["created_at"] = "2026-08-03T01:24:00Z"
    corpus_document["reviewer_credentials"][index][
        "credential_attestation_ref"
    ] = stored_ref_document(attestations[index].reference())
    return credential_corpus(corpus_document), attestations


def prepare_store(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
) -> tuple[Any, ...]:
    artifact_store = store or FileSystemArtifactStore(tmp_path / "artifacts")
    candidate = candidate_registry()
    methods = method_registry()
    quality = quality_policy()
    reviewers = reviewer_registry()
    review_rules = review_policy()
    predecessor = review_corpus(load_document(PREDECESSOR_CORPUS_PATH))
    credentials = credential_corpus()
    issuer_rules = issuer_registry()
    credential_rules = credential_policy()
    fixture_analyzers = analyzers()

    predecessor_plan = experiment_plan(candidate, predecessor, fixture_analyzers)
    persist_review_bound_corpus(
        artifact_store,
        plan=predecessor_plan,
        corpus=predecessor,
        quality_policy=quality,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        sources=source_snapshots(),
        extractions=extraction_snapshots(),
        contents=content_snapshots(),
        assessments=quality_snapshots(),
        adjudications=review_snapshots(),
        evaluated_at="2026-08-03T01:20:00Z",
    )

    plan = experiment_plan(candidate, credentials.corpus, fixture_analyzers)
    persist_credential_bound_corpus(
        artifact_store,
        plan=plan,
        corpus=credentials,
        predecessor_corpus=predecessor,
        reviewer_registry=reviewers,
        review_policy=review_rules,
        issuer_registry=issuer_rules,
        credential_policy=credential_rules,
        attestations=credential_snapshots(),
        adjudications=review_snapshots(),
        evaluated_at="2026-08-03T01:23:00Z",
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
        credentials,
        plan,
        fixture_analyzers,
    )


def execute(
    tmp_path: Path,
    *,
    store: FileSystemArtifactStore | None = None,
    runtime_registry: Any | None = None,
    run_id: str = "credential-run-001",
    evaluated_at: str = "2026-08-03T01:23:00Z",
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
        credentials,
        plan,
        fixture_analyzers,
    ) = prepare_store(tmp_path, store=store)
    runner = CredentialedAdjudicatedExtractionExperimentRunner(
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
        corpus=credentials,
        environment=environment(),
        windows=windows(),
        experiment_run_id=run_id,
        credential_evaluated_at=evaluated_at,
        quality_evaluated_at="2026-08-03T01:23:10Z",
        review_evaluated_at="2026-08-03T01:23:20Z",
    )
    return receipt, artifact_store


def test_active_credentials_execute_and_validate_schemas(tmp_path: Path) -> None:
    receipt, store = execute(tmp_path)

    assert receipt.status is CredentialedAdjudicatedRunnerStatus.VERIFIED
    assert receipt.credential_outcome is CredentialDecisionOutcome.EXECUTE
    assert receipt.terminal_outcome is ReviewDecisionOutcome.EXECUTE
    assert receipt.adjudicated_receipt is not None
    assert receipt.verified_checks == CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS

    validate_schema(ISSUER_SCHEMA, load_document(ISSUER_REGISTRY_PATH))
    validate_schema(POLICY_SCHEMA, load_document(CREDENTIAL_POLICY_PATH))
    for path in ATTESTATION_PATHS:
        validate_schema(ATTESTATION_SCHEMA, load_document(path))
    validate_schema(CORPUS_SCHEMA, load_document(CREDENTIAL_CORPUS_PATH))

    decision = store.get(
        receipt.credential_decision_ref.artifact_id,
        expected_hash=receipt.credential_decision_ref.artifact_hash,
    )
    decision_document = cast(dict[str, Any], json.loads(decision.text))
    validate_schema(DECISION_SCHEMA, decision_document)
    assert "legal_name" not in decision_document
    assert "government_id" not in decision_document

    final = store.get(
        receipt.final_manifest_ref.artifact_id,
        expected_hash=receipt.final_manifest_ref.artifact_hash,
    )
    final_document = cast(dict[str, Any], json.loads(final.text))
    validate_schema(FINAL_SCHEMA, final_document)
    assert final_document["credential_outcome"] == "execute"
    assert final_document["terminal_outcome"] == "execute"
    assert "aggregate_score" not in final_document


def test_credential_ingestion_and_execution_are_idempotent(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first, _ = execute(tmp_path, store=store)
    second, _ = execute(tmp_path, store=store)

    assert first.credential_attestation_refs == second.credential_attestation_refs
    assert first.credential_decision_ref == second.credential_decision_ref
    assert first.final_manifest_ref == second.final_manifest_ref


@pytest.mark.parametrize(
    ("evaluated_at", "reason"),
    (
        ("2026-08-03T01:20:00Z", "credential-not-yet-valid"),
        ("2027-08-03T01:21:00Z", "credential-expired"),
    ),
)
def test_invalid_validity_window_abstains_before_review_or_analysis(
    tmp_path: Path,
    evaluated_at: str,
    reason: str,
) -> None:
    run_id = f"credential-run-{reason}"
    receipt, store = execute(
        tmp_path,
        run_id=run_id,
        evaluated_at=evaluated_at,
    )

    assert receipt.credential_outcome is CredentialDecisionOutcome.ABSTAIN
    assert receipt.terminal_outcome is ReviewDecisionOutcome.ABSTAIN
    assert receipt.adjudicated_receipt is None
    decision = cast(
        dict[str, Any],
        json.loads(
            store.get(
                receipt.credential_decision_ref.artifact_id,
                expected_hash=receipt.credential_decision_ref.artifact_hash,
            ).text
        ),
    )
    assert any(
        reason in item["abstention"]["reasons"]
        for item in decision["credentials"]
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:review-adjudication-decision")
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:extraction-quality-decision")
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{run_id}:experiment-completion")


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        ("suspended", "credential-status:suspended"),
        ("revoked", "credential-status:revoked"),
    ),
)
def test_suspended_and_revoked_credentials_produce_abstention(
    status: str,
    reason: str,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["status"] = status
        if status == "revoked":
            document["revoked_at"] = "2026-08-03T01:22:00Z"
            document["revocation_reason"] = "Synthetic credential withdrawn."

    corpus, attestations = rebuild_credential_case(
        index=1,
        mutate=mutate,
        corpus_version=f"0.5.1-test-{status}",
    )
    plan = experiment_plan(candidate_registry(), corpus.corpus, analyzers())
    decision = validate_reviewer_credential_attestations(
        plan=plan,
        corpus=corpus,
        reviewer_registry=reviewer_registry(),
        issuer_registry=issuer_registry(),
        credential_policy=credential_policy(),
        attestations=attestations,
        adjudications=review_snapshots(),
        evaluated_at="2026-08-03T01:23:00Z",
    )

    assert decision.outcome is CredentialDecisionOutcome.ABSTAIN
    assert reason in decision.credentials[1].abstention.reasons


def test_identity_revision_and_role_drift_fail_validation() -> None:
    def identity_drift(document: dict[str, Any]) -> None:
        document["identity_revision"] = "synthetic-reviewer@9.9.9"
        document["subject_reference"] = (
            "reviewer:reviewer.synthetic.primary@synthetic-reviewer@9.9.9"
        )

    corpus, attestations = rebuild_credential_case(
        index=0,
        mutate=identity_drift,
        corpus_version="0.5.1-test-identity",
    )
    plan = experiment_plan(candidate_registry(), corpus.corpus, analyzers())
    with pytest.raises(ReviewerCredentialError, match="identity revision"):
        validate_reviewer_credential_attestations(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            attestations=attestations,
            adjudications=review_snapshots(),
            evaluated_at="2026-08-03T01:23:00Z",
        )

    def role_drift(document: dict[str, Any]) -> None:
        document["authorized_roles"] = ["secondary_reviewer"]

    corpus, attestations = rebuild_credential_case(
        index=0,
        mutate=role_drift,
        corpus_version="0.5.1-test-role",
    )
    plan = experiment_plan(candidate_registry(), corpus.corpus, analyzers())
    with pytest.raises(ReviewerCredentialError, match="roles differ"):
        validate_reviewer_credential_attestations(
            plan=plan,
            corpus=corpus,
            reviewer_registry=reviewer_registry(),
            issuer_registry=issuer_registry(),
            credential_policy=credential_policy(),
            attestations=attestations,
            adjudications=review_snapshots(),
            evaluated_at="2026-08-03T01:23:00Z",
        )


def test_attestation_schema_and_parser_reject_private_identity_fields() -> None:
    document = load_document(ATTESTATION_PATHS[0])
    document["legal_name"] = "Private Person"

    with pytest.raises(ValidationError):
        validate_schema(ATTESTATION_SCHEMA, document)
    with pytest.raises(ReviewerCredentialError, match="unsupported fields"):
        ReviewerCredentialAttestationSnapshot.from_document(document)


def test_missing_attestation_fails_before_credential_decision(
    tmp_path: Path,
) -> None:
    prepared = prepare_store(tmp_path)
    store = prepared[0]
    credentials = prepared[8]
    failing_store = AttestationReadFailsStore(
        store.root,
        credentials.credential_entries[1].credential_attestation_ref.artifact_id,
    )
    runner = CredentialedAdjudicatedExtractionExperimentRunner(
        analyzer_registry=analyzer_registry(*prepared[10]),
        artifact_store=failing_store,
    )

    with pytest.raises(CredentialedAdjudicatedExperimentError) as caught:
        runner.run(
            plan=prepared[9],
            candidate_registry=prepared[1],
            method_registry=prepared[2],
            quality_policy=prepared[3],
            reviewer_registry=prepared[4],
            review_policy=prepared[5],
            issuer_registry=prepared[6],
            credential_policy=prepared[7],
            corpus=credentials,
            environment=environment(),
            windows=windows(),
            experiment_run_id="credential-run-missing",
            credential_evaluated_at="2026-08-03T01:23:00Z",
            quality_evaluated_at="2026-08-03T01:23:10Z",
            review_evaluated_at="2026-08-03T01:23:20Z",
        )

    assert caught.value.stage is CredentialedAdjudicatedRunnerStage.CREDENTIAL_LOADING
    with pytest.raises(ArtifactNotFoundError):
        store.get("credential-run-missing:reviewer-credential-decision")


def test_later_analyzer_failure_preserves_credential_decision_and_receipt(
    tmp_path: Path,
) -> None:
    first, last = analyzers()
    runtime_registry = analyzer_registry(
        FailOnContentAnalyzer(first, "content-002"),
        last,
    )
    store = FileSystemArtifactStore(tmp_path / "artifacts")

    with pytest.raises(CredentialedAdjudicatedExperimentError) as caught:
        execute(
            tmp_path,
            store=store,
            runtime_registry=runtime_registry,
        )

    assert caught.value.stage is (
        CredentialedAdjudicatedRunnerStage.ADJUDICATED_EXECUTION
    )
    assert caught.value.completed_content_ids == ("content-001",)
    store.get("credential-run-001:reviewer-credential-decision")
    store.get("credential-run-001:0000:content-001:governed-session:receipt")
    with pytest.raises(ArtifactNotFoundError):
        store.get("credential-run-001:credential-attested-completion")


def test_final_persistence_failure_returns_no_verified_receipt(
    tmp_path: Path,
) -> None:
    store = FinalAppendFailsStore(tmp_path / "artifacts")

    with pytest.raises(CredentialedAdjudicatedExperimentError) as caught:
        execute(tmp_path, store=store)

    assert caught.value.stage is CredentialedAdjudicatedRunnerStage.FINAL_PERSISTENCE
    assert caught.value.completed_content_ids == (
        "content-001",
        "content-002",
        "content-003",
    )
    with pytest.raises(ArtifactNotFoundError):
        store.get("credential-run-001:credential-attested-completion")


def test_stored_credential_evidence_reconstructs_exact_attestations(
    tmp_path: Path,
) -> None:
    prepared = prepare_store(tmp_path)
    loaded = load_reviewer_credential_evidence(
        prepared[0],
        corpus=prepared[8],
        reviewer_registry=prepared[4],
        issuer_registry=prepared[6],
        credential_policy=prepared[7],
    )

    assert loaded.attestations == credential_snapshots()
    assert tuple(item.status for item in loaded.attestations) == (
        CredentialAttestationStatus.ACTIVE,
        CredentialAttestationStatus.ACTIVE,
        CredentialAttestationStatus.ACTIVE,
    )
