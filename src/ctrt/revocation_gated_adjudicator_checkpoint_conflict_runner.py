"""Gate checkpoint-conflict adjudicator credentials on append-only revocation history."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_checkpoint_conflict_credential_attestation import (
    load_adjudicator_checkpoint_conflict_credential_evidence,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
    StoredAdjudicatorCredentialRevocationEvidence,
    load_adjudicator_checkpoint_conflict_credential_revocation_evidence,
    validate_adjudicator_checkpoint_conflict_credential_revocation_ledger,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot as PriorAdjudicatorRevocationLedger,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationPolicySnapshot as PriorAdjudicatorRevocationPolicy,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.credential_revocation_checkpoints import (
    CredentialRevocationCheckpointLogSnapshot,
    CredentialRevocationCheckpointPolicySnapshot,
    CredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.credential_revocation_ledger import (
    CredentialRevocationLedgerSnapshot,
    CredentialRevocationPolicySnapshot,
)
from ctrt.credentialed_adjudicator_checkpoint_conflict_runner import (
    CheckpointConflictCredentialExperimentError,
    CredentialedAdjudicatorCheckpointConflictExperimentRunner,
    VerifiedCheckpointConflictCredentialReceipt,
)
from ctrt.experiments import ExecutionEnvironment, ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_bound_runner import ExtractionExecutionWindow
from ctrt.extraction_method_eligibility import ExtractionMethodRegistrySnapshot
from ctrt.extraction_quality import ExtractionQualityPolicySnapshot
from ctrt.extraction_review_adjudication import (
    ReviewAdjudicationPolicySnapshot,
    ReviewDecisionOutcome,
    ReviewerRegistrySnapshot,
)
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
    ReviewerCredentialPolicySnapshot,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)
from ctrt.workbench import AnalyzerRegistry


class CheckpointConflictAdjudicatorRevocationRunnerStage(StrEnum):
    """Boundary at which revocation-gated checkpoint conflict execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIALED_CONFLICT_EXECUTION = "credentialed-conflict-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictAdjudicatorRevocationRunnerStatus(StrEnum):
    """A receipt exists only after the complete graph re-verifies."""

    VERIFIED = "verified"


class CheckpointConflictAdjudicatorRevocationExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointConflictAdjudicatorRevocationRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS = (
    "exact-checkpoint-conflict-adjudicator-revocation-policy-bound",
    "exact-checkpoint-conflict-adjudicator-revocation-ledger-bound",
    "issuer-authority-and-linear-supersession-reverified",
    "checkpoint-conflict-adjudicator-status-evaluated-as-of-declared-time",
    "revocation-decision-persisted-before-credential-execution",
    "credential-conflict-dissent-and-adjudication-records-left-immutable",
    "revocation-credential-and-downstream-outcomes-finalized-separately",
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
class CheckpointConflictAdjudicatorRevocationFinalManifest:
    """Final marker for revocation abstention or delegated credential execution."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictAdjudicatorRevocationRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    revocation_decision_ref: StoredArtifactRef
    credentialed_conflict_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictAdjudicatorRevocationRunnerStatus.VERIFIED:
            raise ValueError("checkpoint-conflict revocation status must be verified")
        if not self.revocation_event_refs:
            raise ValueError("checkpoint-conflict revocation final requires events")
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(
                value is not None
                for value in (
                    self.credential_outcome,
                    self.adjudicator_checkpoint_witness_outcome,
                    self.conflict_adjudication_outcome,
                    self.adjudicator_revocation_outcome,
                    self.adjudicator_credential_outcome,
                    self.reviewer_checkpoint_witness_outcome,
                    self.reviewer_witness_adjudication_outcome,
                    self.reviewer_revocation_outcome,
                    self.credentialed_conflict_final_ref,
                )
            ):
                raise ValueError("revocation abstention may not claim downstream outcomes")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("revocation abstention must be terminal abstention")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-abstention"
            )
        else:
            if self.credential_outcome is None or self.credentialed_conflict_final_ref is None:
                raise ValueError("revocation execution requires credentialed evidence")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                    "adjudicator-credential-revocation-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from revocation terminal outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint-conflict revocation final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictAdjudicatorRevocationReceipt:
    """Proof of revocation eligibility and optional credentialed execution."""

    experiment_run_id: str
    status: CheckpointConflictAdjudicatorRevocationRunnerStatus
    revocation_outcome: CredentialDecisionOutcome
    credential_outcome: CredentialDecisionOutcome | None
    adjudicator_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    adjudicator_credential_outcome: CredentialDecisionOutcome | None
    reviewer_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    reviewer_witness_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    reviewer_revocation_outcome: CredentialDecisionOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    revocation_corpus_ref: StoredArtifactRef
    revocation_policy_ref: StoredArtifactRef
    revocation_ledger_ref: StoredArtifactRef
    revocation_event_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    revocation_decision_ref: StoredArtifactRef
    credentialed_conflict_receipt: VerifiedCheckpointConflictCredentialReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictAdjudicatorRevocationRunnerStatus.VERIFIED:
            raise ValueError("verified checkpoint-conflict revocation status required")
        if self.revocation_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.credentialed_conflict_receipt is not None:
                raise ValueError("revocation abstention may not contain delegated receipt")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-abstention"
            )
        else:
            delegated = self.credentialed_conflict_receipt
            if delegated is None:
                raise ValueError("revocation execution requires delegated receipt")
            if (
                delegated.credential_outcome is not self.credential_outcome
                or delegated.adjudicator_checkpoint_witness_outcome
                is not self.adjudicator_checkpoint_witness_outcome
                or delegated.conflict_adjudication_outcome
                is not self.conflict_adjudication_outcome
                or delegated.adjudicator_revocation_outcome
                is not self.adjudicator_revocation_outcome
                or delegated.adjudicator_credential_outcome
                is not self.adjudicator_credential_outcome
                or delegated.reviewer_checkpoint_witness_outcome
                is not self.reviewer_checkpoint_witness_outcome
                or delegated.reviewer_witness_adjudication_outcome
                is not self.reviewer_witness_adjudication_outcome
                or delegated.reviewer_revocation_outcome
                is not self.reviewer_revocation_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("delegated receipt differs from revocation receipt")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                    "adjudicator-credential-revocation-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong revocation outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
        ):
            raise ValueError("verified checkpoint-conflict revocation receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class RevocationGatedAdjudicatorCheckpointConflictExperimentRunner:
    """Evaluate revocation history before the PR #27 credential runner."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CredentialedAdjudicatorCheckpointConflictExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        revocation_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(
            revocation_evaluated_at,
            "checkpoint_conflict_adjudicator_revocation_evaluated_at",
        )
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-conflict revocation gate requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match revocation-bound conflict corpus")
        if corpus.revocation_policy_ref != revocation_policy.reference():
            raise ValueError("checkpoint-conflict revocation policy must match corpus")
        if corpus.revocation_ledger_ref != ledger.reference():
            raise ValueError("checkpoint-conflict revocation ledger must match corpus")
        if tuple(window.content_id for window in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint-conflict revocation decision differs"
            )
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictAdjudicatorRevocationFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
        policy: AdjudicatorCredentialRevocationPolicySnapshot,
        ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationEvidence,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored checkpoint-conflict revocation final differs"
            )
        if self._store.get(
            evidence.corpus_ref.artifact_id,
            expected_hash=evidence.corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "checkpoint-conflict revocation corpus differs"
            )
        if self._store.get(
            evidence.revocation_policy_ref.artifact_id,
            expected_hash=evidence.revocation_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError(
                "checkpoint-conflict revocation policy differs"
            )
        if self._store.get(
            evidence.revocation_ledger_ref.artifact_id,
            expected_hash=evidence.revocation_ledger_ref.artifact_hash,
        ).payload != ledger.canonical_payload:
            raise ArtifactIntegrityError(
                "checkpoint-conflict revocation ledger differs"
            )
        for reference in evidence.event_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_decision = serialize_artifact(
            (
                f"{final.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-decision"
            ),
            decision,
        )
        if self._store.get(
            final.revocation_decision_ref.artifact_id,
            expected_hash=final.revocation_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError(
                "checkpoint-conflict revocation decision differs"
            )
        if final.credentialed_conflict_final_ref is not None:
            self._store.get(
                final.credentialed_conflict_final_ref.artifact_id,
                expected_hash=final.credentialed_conflict_final_ref.artifact_hash,
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
        checkpoint_policy: CredentialRevocationCheckpointPolicySnapshot,
        checkpoint_log: CredentialRevocationCheckpointLogSnapshot,
        checkpoints: tuple[CredentialRevocationLedgerCheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        adjudicator_issuer_registry: CredentialIssuerRegistrySnapshot,
        adjudicator_credential_policy: AdjudicatorCredentialPolicySnapshot,
        adjudicator_credentials: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
        adjudicator_revocation_policy: PriorAdjudicatorRevocationPolicy,
        adjudicator_revocation_ledger: PriorAdjudicatorRevocationLedger,
        adjudicator_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        adjudicator_checkpoint_log: (
            AdjudicatorCredentialRevocationCheckpointLogSnapshot
        ),
        adjudicator_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        adjudicator_checkpoint_witness_registry: CheckpointWitnessRegistrySnapshot,
        adjudicator_checkpoint_witness_policy: CheckpointWitnessPolicySnapshot,
        adjudicator_checkpoint_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        adjudicator_checkpoint_conflict_adjudicator_registry: (
            WitnessConflictAdjudicatorRegistrySnapshot
        ),
        adjudicator_checkpoint_conflict_adjudication_policy: (
            WitnessConflictAdjudicationPolicySnapshot
        ),
        adjudicator_checkpoint_conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        checkpoint_conflict_adjudicator_issuer_registry: (
            CredentialIssuerRegistrySnapshot
        ),
        checkpoint_conflict_adjudicator_credential_policy: (
            AdjudicatorCredentialPolicySnapshot
        ),
        checkpoint_conflict_adjudicator_credentials: tuple[
            AdjudicatorCredentialAttestationSnapshot, ...
        ],
        checkpoint_conflict_adjudicator_revocation_policy: (
            AdjudicatorCredentialRevocationPolicySnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_ledger: (
            AdjudicatorCredentialRevocationLedgerSnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_events: tuple[
            AdjudicatorCredentialRevocationEventSnapshot, ...
        ],
        corpus: RevocationBoundAdjudicatorCheckpointConflictCredentialCorpusSnapshot,
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_conflict_adjudicator_revocation_evaluated_at: str,
        checkpoint_conflict_credential_evaluated_at: str,
        adjudicator_checkpoint_verified_at: str,
        adjudicator_witness_evaluated_at: str,
        adjudicator_checkpoint_conflict_adjudication_evaluated_at: str,
        adjudicator_revocation_evaluated_at: str,
        adjudicator_credential_evaluated_at: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        quality_evaluated_at: str,
        review_evaluated_at: str,
    ) -> VerifiedCheckpointConflictAdjudicatorRevocationReceipt:
        """Return verified revocation abstention or delegated credential outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_policy=checkpoint_conflict_adjudicator_revocation_policy,
                ledger=checkpoint_conflict_adjudicator_revocation_ledger,
                windows=windows,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=(
                    checkpoint_conflict_adjudicator_revocation_evaluated_at
                ),
            )
        except ValueError as exc:
            raise CheckpointConflictAdjudicatorRevocationExperimentError(
                CheckpointConflictAdjudicatorRevocationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = (
                load_adjudicator_checkpoint_conflict_credential_revocation_evidence(
                    self._store,
                    corpus=corpus,
                    policy=checkpoint_conflict_adjudicator_revocation_policy,
                    ledger=checkpoint_conflict_adjudicator_revocation_ledger,
                )
            )
            credential_evidence = load_adjudicator_checkpoint_conflict_credential_evidence(
                self._store,
                corpus=corpus.corpus,
                adjudicator_registry=(
                    adjudicator_checkpoint_conflict_adjudicator_registry
                ),
                issuer_registry=checkpoint_conflict_adjudicator_issuer_registry,
                credential_policy=checkpoint_conflict_adjudicator_credential_policy,
                adjudication=adjudicator_checkpoint_conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationExperimentError(
                CheckpointConflictAdjudicatorRevocationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = (
                validate_adjudicator_checkpoint_conflict_credential_revocation_ledger(
                    plan=plan,
                    corpus=corpus,
                    adjudicator_registry=(
                        adjudicator_checkpoint_conflict_adjudicator_registry
                    ),
                    issuer_registry=checkpoint_conflict_adjudicator_issuer_registry,
                    credential_policy=checkpoint_conflict_adjudicator_credential_policy,
                    revocation_policy=(
                        checkpoint_conflict_adjudicator_revocation_policy
                    ),
                    ledger=checkpoint_conflict_adjudicator_revocation_ledger,
                    attestations=credential_evidence.attestations,
                    adjudication=adjudicator_checkpoint_conflict_adjudication,
                    events=checkpoint_conflict_adjudicator_revocation_events,
                    evaluated_at=(
                        checkpoint_conflict_adjudicator_revocation_evaluated_at
                    ),
                )
            )
        except (AdjudicatorCredentialRevocationError, ValueError) as exc:
            raise CheckpointConflictAdjudicatorRevocationExperimentError(
                CheckpointConflictAdjudicatorRevocationRunnerStage.REVOCATION_VALIDATION,
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
            raise CheckpointConflictAdjudicatorRevocationExperimentError(
                CheckpointConflictAdjudicatorRevocationRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCheckpointConflictCredentialReceipt | None = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            delegated_plan = replace(
                plan,
                corpus_ref=corpus.corpus.reference(),
                content_ids=corpus.corpus.content_ids,
            )
            try:
                delegated = self._runner.run(
                    plan=delegated_plan,
                    candidate_registry=candidate_registry,
                    method_registry=method_registry,
                    quality_policy=quality_policy,
                    reviewer_registry=reviewer_registry,
                    review_policy=review_policy,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    revocation_policy=revocation_policy,
                    ledger=ledger,
                    checkpoint_policy=checkpoint_policy,
                    checkpoint_log=checkpoint_log,
                    checkpoints=checkpoints,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    witness_attestations=witness_attestations,
                    adjudicator_registry=adjudicator_registry,
                    adjudication_policy=adjudication_policy,
                    adjudication=adjudication,
                    adjudicator_issuer_registry=adjudicator_issuer_registry,
                    adjudicator_credential_policy=adjudicator_credential_policy,
                    adjudicator_credentials=adjudicator_credentials,
                    adjudicator_revocation_policy=adjudicator_revocation_policy,
                    adjudicator_revocation_ledger=adjudicator_revocation_ledger,
                    adjudicator_checkpoint_policy=adjudicator_checkpoint_policy,
                    adjudicator_checkpoint_log=adjudicator_checkpoint_log,
                    adjudicator_checkpoints=adjudicator_checkpoints,
                    adjudicator_checkpoint_witness_registry=(
                        adjudicator_checkpoint_witness_registry
                    ),
                    adjudicator_checkpoint_witness_policy=(
                        adjudicator_checkpoint_witness_policy
                    ),
                    adjudicator_checkpoint_witness_attestations=(
                        adjudicator_checkpoint_witness_attestations
                    ),
                    adjudicator_checkpoint_conflict_adjudicator_registry=(
                        adjudicator_checkpoint_conflict_adjudicator_registry
                    ),
                    adjudicator_checkpoint_conflict_adjudication_policy=(
                        adjudicator_checkpoint_conflict_adjudication_policy
                    ),
                    adjudicator_checkpoint_conflict_adjudication=(
                        adjudicator_checkpoint_conflict_adjudication
                    ),
                    checkpoint_conflict_adjudicator_issuer_registry=(
                        checkpoint_conflict_adjudicator_issuer_registry
                    ),
                    checkpoint_conflict_adjudicator_credential_policy=(
                        checkpoint_conflict_adjudicator_credential_policy
                    ),
                    checkpoint_conflict_adjudicator_credentials=(
                        checkpoint_conflict_adjudicator_credentials
                    ),
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    checkpoint_conflict_credential_evaluated_at=(
                        checkpoint_conflict_credential_evaluated_at
                    ),
                    adjudicator_checkpoint_verified_at=(
                        adjudicator_checkpoint_verified_at
                    ),
                    adjudicator_witness_evaluated_at=(
                        adjudicator_witness_evaluated_at
                    ),
                    adjudicator_checkpoint_conflict_adjudication_evaluated_at=(
                        adjudicator_checkpoint_conflict_adjudication_evaluated_at
                    ),
                    adjudicator_revocation_evaluated_at=(
                        adjudicator_revocation_evaluated_at
                    ),
                    adjudicator_credential_evaluated_at=(
                        adjudicator_credential_evaluated_at
                    ),
                    checkpoint_verified_at=checkpoint_verified_at,
                    witness_evaluated_at=witness_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    quality_evaluated_at=quality_evaluated_at,
                    review_evaluated_at=review_evaluated_at,
                )
            except CheckpointConflictCredentialExperimentError as exc:
                raise CheckpointConflictAdjudicatorRevocationExperimentError(
                    CheckpointConflictAdjudicatorRevocationRunnerStage.CREDENTIALED_CONFLICT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = checkpoint_conflict_adjudicator_revocation_evaluated_at
        delegated_final_ref: StoredArtifactRef | None = None
        credential_outcome: CredentialDecisionOutcome | None = None
        adjudicator_checkpoint_witness_outcome: (
            CheckpointWitnessDecisionOutcome | None
        ) = None
        conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        adjudicator_revocation_outcome: CredentialDecisionOutcome | None = None
        adjudicator_credential_outcome: CredentialDecisionOutcome | None = None
        reviewer_checkpoint_witness_outcome: (
            CheckpointWitnessDecisionOutcome | None
        ) = None
        reviewer_witness_adjudication_outcome: (
            WitnessConflictAdjudicationOutcome | None
        ) = None
        reviewer_revocation_outcome: CredentialDecisionOutcome | None = None
        if delegated is not None:
            terminal_outcome = delegated.terminal_outcome
            completed_at = delegated.completed_at
            delegated_final_ref = delegated.final_manifest_ref
            credential_outcome = delegated.credential_outcome
            adjudicator_checkpoint_witness_outcome = (
                delegated.adjudicator_checkpoint_witness_outcome
            )
            conflict_adjudication_outcome = delegated.conflict_adjudication_outcome
            adjudicator_revocation_outcome = delegated.adjudicator_revocation_outcome
            adjudicator_credential_outcome = delegated.adjudicator_credential_outcome
            reviewer_checkpoint_witness_outcome = (
                delegated.reviewer_checkpoint_witness_outcome
            )
            reviewer_witness_adjudication_outcome = (
                delegated.reviewer_witness_adjudication_outcome
            )
            reviewer_revocation_outcome = delegated.reviewer_revocation_outcome

        final_id = (
            f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
            "adjudicator-credential-revocation-abstention"
            if decision.outcome is CredentialDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                    "adjudicator-credential-revocation-terminal-abstention"
                )
            )
        )
        final = CheckpointConflictAdjudicatorRevocationFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictAdjudicatorRevocationRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            credential_outcome=credential_outcome,
            adjudicator_checkpoint_witness_outcome=(
                adjudicator_checkpoint_witness_outcome
            ),
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=(
                reviewer_checkpoint_witness_outcome
            ),
            reviewer_witness_adjudication_outcome=(
                reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=evidence.corpus_ref,
            revocation_policy_ref=evidence.revocation_policy_ref,
            revocation_ledger_ref=evidence.revocation_ledger_ref,
            revocation_event_refs=evidence.event_refs,
            adjudication_ref=adjudicator_checkpoint_conflict_adjudication.reference(),
            revocation_decision_ref=decision_ref,
            credentialed_conflict_final_ref=delegated_final_ref,
            verified_checks=(
                CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )
        try:
            final_ref = self._store.append(serialize_artifact(final.final_id, final))
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationExperimentError(
                CheckpointConflictAdjudicatorRevocationRunnerStage.FINAL_PERSISTENCE,
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
                policy=checkpoint_conflict_adjudicator_revocation_policy,
                ledger=checkpoint_conflict_adjudicator_revocation_ledger,
                evidence=evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictAdjudicatorRevocationExperimentError(
                CheckpointConflictAdjudicatorRevocationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictAdjudicatorRevocationReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictAdjudicatorRevocationRunnerStatus.VERIFIED,
            revocation_outcome=decision.outcome,
            credential_outcome=credential_outcome,
            adjudicator_checkpoint_witness_outcome=(
                adjudicator_checkpoint_witness_outcome
            ),
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=(
                reviewer_checkpoint_witness_outcome
            ),
            reviewer_witness_adjudication_outcome=(
                reviewer_witness_adjudication_outcome
            ),
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            revocation_corpus_ref=evidence.corpus_ref,
            revocation_policy_ref=evidence.revocation_policy_ref,
            revocation_ledger_ref=evidence.revocation_ledger_ref,
            revocation_event_refs=evidence.event_refs,
            adjudication_ref=adjudicator_checkpoint_conflict_adjudication.reference(),
            revocation_decision_ref=decision_ref,
            credentialed_conflict_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=(
                CHECKPOINT_CONFLICT_ADJUDICATOR_REVOCATION_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )
