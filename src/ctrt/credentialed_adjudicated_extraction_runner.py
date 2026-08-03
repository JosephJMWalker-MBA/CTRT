"""Gate review-adjudicated extraction execution on reviewer credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicated_extraction_runner import (
    AdjudicatedExtractionExperimentError,
    AdjudicatedExtractionExperimentRunner,
    VerifiedAdjudicatedExtractionReceipt,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import ExtractionQualityPolicySnapshot
from ctrt.extraction_review_adjudication import (
    ReviewAdjudicationPolicySnapshot,
    ReviewDecisionOutcome,
    ReviewerRegistrySnapshot,
    load_review_adjudication_evidence,
)
from ctrt.reviewer_credential_attestation import (
    CredentialBoundReviewCorpusSnapshot,
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
    ReviewerCredentialDecisionReport,
    ReviewerCredentialError,
    ReviewerCredentialPolicySnapshot,
    StoredReviewerCredentialEvidence,
    load_reviewer_credential_evidence,
    validate_reviewer_credential_attestations,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class CredentialedAdjudicatedRunnerStage(StrEnum):
    """Boundary at which credential-attested execution failed."""

    PREFLIGHT = "preflight"
    CREDENTIAL_LOADING = "credential-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    ADJUDICATED_EXECUTION = "adjudicated-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CredentialedAdjudicatedRunnerStatus(StrEnum):
    """A receipt exists only after credential and final reverification."""

    VERIFIED = "verified"


class CredentialedAdjudicatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CredentialedAdjudicatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS = (
    "exact-credential-issuer-registry-bound",
    "reviewer-identity-revisions-attested",
    "reviewer-roles-attested",
    "credential-validity-and-revocation-evaluated",
    "credential-decision-persisted",
    "credential-outcome-finalized",
)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


@dataclass(frozen=True, slots=True)
class CredentialedAdjudicatedFinalManifest:
    """Final marker for credential-permitted execution or abstention."""

    final_id: str
    experiment_run_id: str
    status: CredentialedAdjudicatedRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    reviewer_registry_ref: StoredArtifactRef
    credential_issuer_registry_ref: StoredArtifactRef
    reviewer_credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    credential_decision_ref: StoredArtifactRef
    adjudicated_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.final_id,
                self.experiment_run_id,
                self.experiment_id,
                self.experiment_version,
            )
        ):
            raise ValueError(
                "credentialed adjudication identity fields must not be empty"
            )
        if self.status is not CredentialedAdjudicatedRunnerStatus.VERIFIED:
            raise ValueError("credentialed adjudication status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError(
                "credentialed adjudication requires unique multiple content items"
            )
        if not self.credential_attestation_refs:
            raise ValueError(
                "credentialed adjudication requires credential attestations"
            )
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError(
                    "credential abstention must be terminal abstention"
                )
            if self.adjudicated_final_ref is not None:
                raise ValueError(
                    "credential abstention may not reference adjudicated execution"
                )
        elif self.adjudicated_final_ref is None:
            raise ValueError(
                "credential-permitted outcome requires adjudicated final"
            )
        expected_id = (
            f"{self.experiment_run_id}:credential-attested-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else f"{self.experiment_run_id}:credential-attestation-abstention"
        )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from terminal outcome")
        if self.verified_checks != CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS:
            raise ValueError(
                "credentialed adjudication final must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCredentialedAdjudicatedReceipt:
    """Proof of credential-bound execution or governed abstention."""

    experiment_run_id: str
    status: CredentialedAdjudicatedRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    reviewer_registry_ref: StoredArtifactRef
    credential_issuer_registry_ref: StoredArtifactRef
    reviewer_credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    credential_decision_ref: StoredArtifactRef
    adjudicated_receipt: VerifiedAdjudicatedExtractionReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CredentialedAdjudicatedRunnerStatus.VERIFIED:
            raise ValueError("verified credentialed status must be verified")
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.adjudicated_receipt is not None:
                raise ValueError(
                    "credential abstention may not contain adjudicated receipt"
                )
        else:
            if self.adjudicated_receipt is None:
                raise ValueError(
                    "credential-permitted receipt requires adjudicated receipt"
                )
            if self.adjudicated_receipt.terminal_outcome is not (
                self.terminal_outcome
            ):
                raise ValueError(
                    "adjudicated receipt differs from terminal outcome"
                )
        expected_id = (
            f"{self.experiment_run_id}:credential-attested-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else f"{self.experiment_run_id}:credential-attestation-abstention"
        )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest must identify terminal outcome")
        if self.verified_checks != CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS:
            raise ValueError("verified receipt must preserve every check")
        _parse_timestamp(self.completed_at, "completed_at")


class CredentialedAdjudicatedExtractionExperimentRunner:
    """Evaluate reviewer credentials before review adjudication."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = AdjudicatedExtractionExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundReviewCorpusSnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: ReviewerCredentialPolicySnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            credential_evaluated_at,
            "credential_evaluated_at",
        )
        _parse_timestamp(quality_evaluated_at, "quality_evaluated_at")
        _parse_timestamp(review_evaluated_at, "review_evaluated_at")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError(
                "credential-attested execution requires a frozen plan"
            )
        if plan.corpus_ref != corpus.reference():
            raise ValueError(
                "plan corpus_ref must match credential-bound corpus"
            )
        if plan.content_ids != corpus.content_ids:
            raise ValueError(
                "plan content order must match credential-bound corpus"
            )
        if corpus.corpus.reviewer_registry_ref != reviewer_registry.reference():
            raise ValueError("reviewer registry reference must match corpus")
        if corpus.credential_issuer_registry_ref != issuer_registry.reference():
            raise ValueError(
                "credential issuer registry reference must match corpus"
            )
        if corpus.reviewer_credential_policy_ref != credential_policy.reference():
            raise ValueError(
                "reviewer credential policy reference must match corpus"
            )
        window_ids = tuple(item.content_id for item in windows)
        if window_ids != corpus.content_ids or len(window_ids) < 2:
            raise ValueError(
                "execution windows must match frozen content order"
            )

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: ReviewerCredentialDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:reviewer-credential-decision",
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored credential decision differs from report"
            )
        self._store.append(
            serialize_artifact(
                decision.artifact_id,
                {
                    "experiment_id": decision.experiment_id,
                    "experiment_version": decision.experiment_version,
                    "credential_corpus_ref": decision.credential_corpus_ref,
                    "reviewer_registry_ref": decision.reviewer_registry_ref,
                    "credential_issuer_registry_ref": (
                        decision.credential_issuer_registry_ref
                    ),
                    "reviewer_credential_policy_ref": (
                        decision.reviewer_credential_policy_ref
                    ),
                },
            )
        )
        return reference

    def _verify_final(
        self,
        *,
        final: CredentialedAdjudicatedFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CredentialBoundReviewCorpusSnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: ReviewerCredentialPolicySnapshot,
        evidence: StoredReviewerCredentialEvidence,
        decision: ReviewerCredentialDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored credentialed final differs from expected"
            )
        if self._store.get(
            final.credential_corpus_ref.artifact_id,
            expected_hash=final.credential_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "credential corpus differs during verification"
            )
        if self._store.get(
            final.reviewer_registry_ref.artifact_id,
            expected_hash=final.reviewer_registry_ref.artifact_hash,
        ).payload != reviewer_registry.canonical_payload:
            raise ArtifactIntegrityError(
                "reviewer registry differs during verification"
            )
        if self._store.get(
            final.credential_issuer_registry_ref.artifact_id,
            expected_hash=final.credential_issuer_registry_ref.artifact_hash,
        ).payload != issuer_registry.canonical_payload:
            raise ArtifactIntegrityError(
                "credential issuer registry differs during verification"
            )
        if self._store.get(
            final.reviewer_credential_policy_ref.artifact_id,
            expected_hash=final.reviewer_credential_policy_ref.artifact_hash,
        ).payload != credential_policy.canonical_payload:
            raise ArtifactIntegrityError(
                "reviewer credential policy differs during verification"
            )
        for reference in evidence.attestation_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        decision_artifact = serialize_artifact(
            f"{final.experiment_run_id}:reviewer-credential-decision",
            decision,
        )
        if self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        ).payload != decision_artifact.payload:
            raise ArtifactIntegrityError(
                "credential decision differs during verification"
            )
        if final.adjudicated_final_ref is not None:
            self._store.get(
                final.adjudicated_final_ref.artifact_id,
                expected_hash=final.adjudicated_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        candidate_registry: CandidateRegistrySnapshot,
        method_registry: ExtractionMethodRegistrySnapshot,
        quality_policy: ExtractionQualityPolicySnapshot,
        reviewer_registry: ReviewerRegistrySnapshot,
        review_policy: ReviewAdjudicationPolicySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: ReviewerCredentialPolicySnapshot,
        corpus: CredentialBoundReviewCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedCredentialedAdjudicatedReceipt:
        """Return a verified credential abstention or adjudicated outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                windows=windows,
                experiment_run_id=experiment_run_id,
                credential_evaluated_at=credential_evaluated_at,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except ValueError as exc:
            raise CredentialedAdjudicatedExperimentError(
                CredentialedAdjudicatedRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            credential_evidence = load_reviewer_credential_evidence(
                self._store,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
            )
            review_evidence = load_review_adjudication_evidence(
                self._store,
                corpus=corpus.corpus,
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
            )
        except (
            ArtifactStoreError,
            ReviewerCredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatedExperimentError(
                CredentialedAdjudicatedRunnerStage.CREDENTIAL_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_reviewer_credential_attestations(
                plan=plan,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                attestations=credential_evidence.attestations,
                adjudications=review_evidence.adjudications,
                evaluated_at=credential_evaluated_at,
            )
        except (ReviewerCredentialError, ValueError) as exc:
            raise CredentialedAdjudicatedExperimentError(
                CredentialedAdjudicatedRunnerStage.CREDENTIAL_VALIDATION,
                str(exc),
            ) from exc

        try:
            decision_ref = self._persist_decision(
                experiment_run_id=experiment_run_id,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatedExperimentError(
                CredentialedAdjudicatedRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        adjudicated_receipt: VerifiedAdjudicatedExtractionReceipt | None = None
        adjudicated_final_ref: StoredArtifactRef | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = credential_evaluated_at
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            try:
                adjudicated_receipt = self._runner.run(
                    plan=plan,
                    candidate_registry=candidate_registry,
                    method_registry=method_registry,
                    quality_policy=quality_policy,
                    reviewer_registry=reviewer_registry,
                    review_policy=review_policy,
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except AdjudicatedExtractionExperimentError as exc:
                raise CredentialedAdjudicatedExperimentError(
                    CredentialedAdjudicatedRunnerStage.ADJUDICATED_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            adjudicated_final_ref = adjudicated_receipt.final_manifest_ref
            terminal_outcome = adjudicated_receipt.terminal_outcome
            completed_at = adjudicated_receipt.completed_at

        final = CredentialedAdjudicatedFinalManifest(
            final_id=(
                f"{experiment_run_id}:credential-attested-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else f"{experiment_run_id}:credential-attestation-abstention"
            ),
            experiment_run_id=experiment_run_id,
            status=CredentialedAdjudicatedRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=credential_evidence.corpus_ref,
            reviewer_registry_ref=credential_evidence.reviewer_registry_ref,
            credential_issuer_registry_ref=(
                credential_evidence.credential_issuer_registry_ref
            ),
            reviewer_credential_policy_ref=(
                credential_evidence.reviewer_credential_policy_ref
            ),
            credential_attestation_refs=credential_evidence.attestation_refs,
            credential_decision_ref=decision_ref,
            adjudicated_final_ref=adjudicated_final_ref,
            verified_checks=CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(
                serialize_artifact(final.final_id, final)
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatedExperimentError(
                CredentialedAdjudicatedRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                evidence=credential_evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedAdjudicatedExperimentError(
                CredentialedAdjudicatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCredentialedAdjudicatedReceipt(
            experiment_run_id=experiment_run_id,
            status=CredentialedAdjudicatedRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=credential_evidence.corpus_ref,
            reviewer_registry_ref=credential_evidence.reviewer_registry_ref,
            credential_issuer_registry_ref=(
                credential_evidence.credential_issuer_registry_ref
            ),
            reviewer_credential_policy_ref=(
                credential_evidence.reviewer_credential_policy_ref
            ),
            credential_attestation_refs=credential_evidence.attestation_refs,
            credential_decision_ref=decision_ref,
            adjudicated_receipt=adjudicated_receipt,
            final_manifest_ref=final_ref,
            verified_checks=CREDENTIALED_ADJUDICATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
