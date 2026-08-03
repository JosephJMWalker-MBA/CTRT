"""Gate credentialed review execution on an append-only revocation ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.credential_revocation_ledger import (
    CredentialRevocationDecisionReport,
    CredentialRevocationError,
    CredentialRevocationLedgerSnapshot,
    CredentialRevocationPolicySnapshot,
    RevocationBoundCredentialCorpusSnapshot,
    StoredCredentialRevocationEvidence,
    load_credential_revocation_evidence,
    validate_credential_revocation_ledger,
)
from ctrt.credentialed_adjudicated_extraction_runner import (
    CredentialedAdjudicatedExperimentError,
    CredentialedAdjudicatedExtractionExperimentRunner,
    VerifiedCredentialedAdjudicatedReceipt,
)
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
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
    ReviewerCredentialPolicySnapshot,
    load_reviewer_credential_evidence,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.workbench import AnalyzerRegistry


class RevocationGatedRunnerStage(StrEnum):
    """Boundary at which revocation-gated execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIALED_EXECUTION = "credentialed-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class RevocationGatedRunnerStatus(StrEnum):
    """A receipt exists only after revocation and final reverification."""

    VERIFIED = "verified"


class RevocationGatedExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: RevocationGatedRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


REVOCATION_GATED_VERIFIED_CHECKS = (
    "exact-revocation-policy-bound",
    "exact-revocation-ledger-bound",
    "issuer-authority-and-event-supersession-verified",
    "credential-status-evaluated-as-of-experiment-time",
    "revocation-decision-persisted",
    "revocation-outcome-finalized",
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
class RevocationGatedFinalManifest:
    """Final marker for revocation-permitted execution or abstention."""

    final_id: str
    experiment_run_id: str
    status: RevocationGatedRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    revocation_decision_ref: StoredArtifactRef
    credentialed_final_ref: StoredArtifactRef | None
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
                "revocation-gated identity fields must not be empty"
            )
        if self.status is not RevocationGatedRunnerStatus.VERIFIED:
            raise ValueError("revocation-gated status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(
            set(self.content_ids)
        ):
            raise ValueError(
                "revocation-gated execution requires unique multiple content items"
            )
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError(
                    "revocation abstention must be terminal abstention"
                )
            if self.credentialed_final_ref is not None:
                raise ValueError(
                    "revocation abstention may not reference credentialed execution"
                )
        elif self.credentialed_final_ref is None:
            raise ValueError(
                "revocation-permitted outcome requires credentialed final"
            )
        expected_id = (
            f"{self.experiment_run_id}:revocation-ledger-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else f"{self.experiment_run_id}:credential-revocation-abstention"
        )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from terminal outcome")
        if self.verified_checks != REVOCATION_GATED_VERIFIED_CHECKS:
            raise ValueError(
                "revocation-gated final must preserve every check"
            )
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedRevocationGatedReceipt:
    """Proof of revocation-ledger execution or governed abstention."""

    experiment_run_id: str
    status: RevocationGatedRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    revocation_decision_ref: StoredArtifactRef
    credentialed_receipt: VerifiedCredentialedAdjudicatedReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not RevocationGatedRunnerStatus.VERIFIED:
            raise ValueError(
                "verified revocation-gated status must be verified"
            )
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.credentialed_receipt is not None:
                raise ValueError(
                    "revocation abstention may not contain credentialed receipt"
                )
        else:
            if self.credentialed_receipt is None:
                raise ValueError(
                    "revocation-permitted receipt requires credentialed receipt"
                )
            if self.credentialed_receipt.terminal_outcome is not (
                self.terminal_outcome
            ):
                raise ValueError(
                    "credentialed receipt differs from terminal outcome"
                )
        expected_id = (
            f"{self.experiment_run_id}:revocation-ledger-completion"
            if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
            else f"{self.experiment_run_id}:credential-revocation-abstention"
        )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest must identify terminal outcome")
        if self.verified_checks != REVOCATION_GATED_VERIFIED_CHECKS:
            raise ValueError("verified receipt must preserve every check")
        _parse_timestamp(self.completed_at, "completed_at")


class RevocationGatedCredentialedExtractionExperimentRunner:
    """Evaluate immutable revocation history before credentialed execution."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CredentialedAdjudicatedExtractionExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundCredentialCorpusSnapshot,
        revocation_policy: CredentialRevocationPolicySnapshot,
        ledger: CredentialRevocationLedgerSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        for value, field_name in (
            (revocation_evaluated_at, "revocation_evaluated_at"),
            (credential_evaluated_at, "credential_evaluated_at"),
            (quality_evaluated_at, "quality_evaluated_at"),
            (review_evaluated_at, "review_evaluated_at"),
        ):
            _parse_timestamp(value, field_name)
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError(
                "revocation-gated execution requires a frozen plan"
            )
        if plan.corpus_ref != corpus.reference() or plan.content_ids != (
            corpus.content_ids
        ):
            raise ValueError(
                "plan must match revocation-bound corpus exactly"
            )
        if corpus.revocation_policy_ref != revocation_policy.reference():
            raise ValueError(
                "revocation policy reference must match corpus"
            )
        if corpus.revocation_ledger_ref != ledger.reference():
            raise ValueError(
                "revocation ledger reference must match corpus"
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
        decision: CredentialRevocationDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            f"{experiment_run_id}:credential-revocation-decision",
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored revocation decision differs from report"
            )
        self._store.append(
            serialize_artifact(
                decision.artifact_id,
                {
                    "experiment_id": decision.experiment_id,
                    "experiment_version": decision.experiment_version,
                    "revocation_corpus_ref": decision.revocation_corpus_ref,
                    "revocation_policy_ref": decision.revocation_policy_ref,
                    "revocation_ledger_ref": decision.revocation_ledger_ref,
                },
            )
        )
        return reference

    def _verify_final(
        self,
        *,
        final: RevocationGatedFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: RevocationBoundCredentialCorpusSnapshot,
        revocation_policy: CredentialRevocationPolicySnapshot,
        ledger: CredentialRevocationLedgerSnapshot,
        evidence: StoredCredentialRevocationEvidence,
        decision: CredentialRevocationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored revocation-gated final differs from expected"
            )
        if self._store.get(
            final.revocation_corpus_ref.artifact_id,
            expected_hash=final.revocation_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "revocation corpus differs during verification"
            )
        if self._store.get(
            final.revocation_policy_ref.artifact_id,
            expected_hash=final.revocation_policy_ref.artifact_hash,
        ).payload != revocation_policy.canonical_payload:
            raise ArtifactIntegrityError(
                "revocation policy differs during verification"
            )
        if self._store.get(
            final.revocation_ledger_ref.artifact_id,
            expected_hash=final.revocation_ledger_ref.artifact_hash,
        ).payload != ledger.canonical_payload:
            raise ArtifactIntegrityError(
                "revocation ledger differs during verification"
            )
        for reference in evidence.event_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        decision_artifact = serialize_artifact(
            f"{final.experiment_run_id}:credential-revocation-decision",
            decision,
        )
        if self._store.get(
            final.revocation_decision_ref.artifact_id,
            expected_hash=final.revocation_decision_ref.artifact_hash,
        ).payload != decision_artifact.payload:
            raise ArtifactIntegrityError(
                "revocation decision differs during verification"
            )
        if final.credentialed_final_ref is not None:
            self._store.get(
                final.credentialed_final_ref.artifact_id,
                expected_hash=final.credentialed_final_ref.artifact_hash,
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
        revocation_policy: CredentialRevocationPolicySnapshot,
        ledger: CredentialRevocationLedgerSnapshot,
        corpus: RevocationBoundCredentialCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedRevocationGatedReceipt:
        """Return a verified revocation abstention or credentialed outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_policy=revocation_policy,
                ledger=ledger,
                windows=windows,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                quality_evaluated_at=quality_evaluated_at,
                review_evaluated_at=review_evaluated_at,
            )
        except ValueError as exc:
            raise RevocationGatedExperimentError(
                RevocationGatedRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            revocation_evidence = load_credential_revocation_evidence(
                self._store,
                corpus=corpus,
                policy=revocation_policy,
                ledger=ledger,
            )
            credential_evidence = load_reviewer_credential_evidence(
                self._store,
                corpus=corpus.corpus,
                reviewer_registry=reviewer_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
            )
            review_evidence = load_review_adjudication_evidence(
                self._store,
                corpus=corpus.corpus.corpus,
                reviewer_registry=reviewer_registry,
                review_policy=review_policy,
            )
        except (
            ArtifactStoreError,
            CredentialRevocationError,
            OSError,
            ValueError,
        ) as exc:
            raise RevocationGatedExperimentError(
                RevocationGatedRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_credential_revocation_ledger(
                plan=plan,
                corpus=corpus,
                reviewer_registry=reviewer_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                revocation_policy=revocation_policy,
                ledger=ledger,
                attestations=credential_evidence.attestations,
                adjudications=review_evidence.adjudications,
                events=revocation_evidence.events,
                evaluated_at=revocation_evaluated_at,
            )
        except (CredentialRevocationError, ValueError) as exc:
            raise RevocationGatedExperimentError(
                RevocationGatedRunnerStage.REVOCATION_VALIDATION,
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
            raise RevocationGatedExperimentError(
                RevocationGatedRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        credentialed_receipt: VerifiedCredentialedAdjudicatedReceipt | None = None
        credentialed_final_ref: StoredArtifactRef | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = revocation_evaluated_at
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            try:
                credentialed_receipt = self._runner.run(
                    plan=plan,
                    candidate_registry=candidate_registry,
                    method_registry=method_registry,
                    quality_policy=quality_policy,
                    reviewer_registry=reviewer_registry,
                    review_policy=review_policy,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except CredentialedAdjudicatedExperimentError as exc:
                raise RevocationGatedExperimentError(
                    RevocationGatedRunnerStage.CREDENTIALED_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            credentialed_final_ref = credentialed_receipt.final_manifest_ref
            terminal_outcome = credentialed_receipt.terminal_outcome
            completed_at = credentialed_receipt.completed_at

        final = RevocationGatedFinalManifest(
            final_id=(
                f"{experiment_run_id}:revocation-ledger-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else f"{experiment_run_id}:credential-revocation-abstention"
            ),
            experiment_run_id=experiment_run_id,
            status=RevocationGatedRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=revocation_evidence.corpus_ref,
            revocation_policy_ref=revocation_evidence.revocation_policy_ref,
            revocation_ledger_ref=revocation_evidence.revocation_ledger_ref,
            revocation_event_refs=revocation_evidence.event_refs,
            revocation_decision_ref=decision_ref,
            credentialed_final_ref=credentialed_final_ref,
            verified_checks=REVOCATION_GATED_VERIFIED_CHECKS,
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
            raise RevocationGatedExperimentError(
                RevocationGatedRunnerStage.FINAL_PERSISTENCE,
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
                revocation_policy=revocation_policy,
                ledger=ledger,
                evidence=revocation_evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise RevocationGatedExperimentError(
                RevocationGatedRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedRevocationGatedReceipt(
            experiment_run_id=experiment_run_id,
            status=RevocationGatedRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=revocation_evidence.corpus_ref,
            revocation_policy_ref=revocation_evidence.revocation_policy_ref,
            revocation_ledger_ref=revocation_evidence.revocation_ledger_ref,
            revocation_event_refs=revocation_evidence.event_refs,
            revocation_decision_ref=decision_ref,
            credentialed_receipt=credentialed_receipt,
            final_manifest_ref=final_ref,
            verified_checks=REVOCATION_GATED_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
