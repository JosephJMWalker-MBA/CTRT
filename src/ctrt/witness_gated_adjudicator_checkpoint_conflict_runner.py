"""Gate checkpoint-conflict revocation execution on named checkpoint witnesses."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointLogSnapshot as PriorCheckpointLog,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot as PriorCheckpointPolicy,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot as PriorCheckpoint,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot as PriorRevocationLedger,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationPolicySnapshot as PriorRevocationPolicy,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import CandidateRegistrySnapshot
from ctrt.checkpoint_conflict_revocation_witness import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot,
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence,
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations,
)
from ctrt.checkpoint_gated_adjudicator_checkpoint_conflict_runner import (
    CheckpointConflictAdjudicatorRevocationCheckpointExperimentError,
    CheckpointGatedAdjudicatorCheckpointConflictExperimentRunner,
    VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt,
)
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


load_witness_evidence = (
    load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_evidence
)
validate_witnesses = (
    validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_attestations
)


class CheckpointConflictRevocationWitnessRunnerStage(StrEnum):
    """Boundary at which named checkpoint-witness execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictRevocationWitnessRunnerStatus(StrEnum):
    """A receipt exists only after witness and final reverification."""

    VERIFIED = "verified"


class CheckpointConflictRevocationWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CheckpointConflictRevocationWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_REVOCATION_WITNESS_VERIFIED_CHECKS = (
    "exact-checkpoint-conflict-revocation-witness-registry-bound",
    "exact-checkpoint-conflict-revocation-witness-policy-bound",
    "exact-checkpoint-conflict-revocation-witness-population-bound",
    "exact-checkpoint-conflict-revocation-checkpoint-head-reverified",
    "named-checkpoint-conflict-revocation-observations-preserved",
    "checkpoint-conflict-revocation-witness-decision-persisted",
    "checkpoint-conflict-revocation-witness-outcome-finalized-separately",
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
class CheckpointConflictRevocationWitnessFinalManifest:
    """Final marker for named-witness-gated checkpoint execution."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictRevocationWitnessRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
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
    witness_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    checkpoint_verification_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    checkpoint_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictRevocationWitnessRunnerStatus.VERIFIED:
            raise ValueError("checkpoint-conflict witness status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("checkpoint-conflict witness requires unique multiple contents")
        if not self.witness_attestation_refs:
            raise ValueError("checkpoint-conflict witness final requires attestations")
        if len(self.witness_attestation_refs) != len(set(self.witness_attestation_refs)):
            raise ValueError("checkpoint-conflict witness refs must be unique")
        downstream = (
            self.revocation_outcome,
            self.credential_outcome,
            self.adjudicator_checkpoint_witness_outcome,
            self.conflict_adjudication_outcome,
            self.adjudicator_revocation_outcome,
            self.adjudicator_credential_outcome,
            self.reviewer_checkpoint_witness_outcome,
            self.reviewer_witness_adjudication_outcome,
            self.reviewer_revocation_outcome,
        )
        if self.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("witness abstention must not contain downstream outcomes")
            if self.checkpoint_final_ref is not None:
                raise ValueError("witness abstention must not contain checkpoint final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("witness abstention must be terminal")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-abstention"
            )
        else:
            if self.checkpoint_final_ref is None or self.revocation_outcome is None:
                raise ValueError("witness execution requires delegated checkpoint outcome")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                    "adjudicator-credential-revocation-checkpoint-witness-"
                    "terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from witness and terminal outcomes")
        if self.verified_checks != CHECKPOINT_CONFLICT_REVOCATION_WITNESS_VERIFIED_CHECKS:
            raise ValueError("checkpoint-conflict witness final lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictRevocationWitnessReceipt:
    """Proof of named observations plus optional delegated checkpoint outcome."""

    experiment_run_id: str
    status: CheckpointConflictRevocationWitnessRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
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
    witness_corpus_ref: StoredArtifactRef
    witness_registry_ref: StoredArtifactRef
    witness_policy_ref: StoredArtifactRef
    witness_attestation_refs: tuple[StoredArtifactRef, ...]
    checkpoint_verification_ref: StoredArtifactRef
    witness_decision_ref: StoredArtifactRef
    checkpoint_receipt: (
        VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictRevocationWitnessRunnerStatus.VERIFIED:
            raise ValueError("verified checkpoint-conflict witness status required")
        downstream = (
            self.revocation_outcome,
            self.credential_outcome,
            self.adjudicator_checkpoint_witness_outcome,
            self.conflict_adjudication_outcome,
            self.adjudicator_revocation_outcome,
            self.adjudicator_credential_outcome,
            self.reviewer_checkpoint_witness_outcome,
            self.reviewer_witness_adjudication_outcome,
            self.reviewer_revocation_outcome,
        )
        if self.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None:
                raise ValueError("witness abstention must not contain checkpoint receipt")
            if any(item is not None for item in downstream):
                raise ValueError("witness abstention must not contain downstream outcomes")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-abstention"
            )
        else:
            delegated = self.checkpoint_receipt
            if delegated is None:
                raise ValueError("witness execution requires checkpoint receipt")
            if (
                delegated.revocation_outcome is not self.revocation_outcome
                or delegated.credential_outcome is not self.credential_outcome
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
                raise ValueError("checkpoint receipt differs from witness receipt")
            expected_id = (
                f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:adjudicator-checkpoint-conflict-"
                    "adjudicator-credential-revocation-checkpoint-witness-"
                    "terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong witness outcome")
        if self.verified_checks != CHECKPOINT_CONFLICT_REVOCATION_WITNESS_VERIFIED_CHECKS:
            raise ValueError("verified witness receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class WitnessGatedAdjudicatorCheckpointConflictExperimentRunner:
    """Verify named witnesses before executing the exact PR #29 checkpoint runner."""

    def __init__(
        self,
        *,
        analyzer_registry: AnalyzerRegistry,
        artifact_store: FileSystemArtifactStore,
    ) -> None:
        self._store = artifact_store
        self._runner = CheckpointGatedAdjudicatorCheckpointConflictExperimentRunner(
            analyzer_registry=analyzer_registry,
            artifact_store=artifact_store,
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: (
            WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot
        ),
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_verified_at: str,
        witness_evaluated_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        _parse_timestamp(checkpoint_verified_at, "checkpoint_verified_at")
        _parse_timestamp(witness_evaluated_at, "witness_evaluated_at")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-conflict witness execution requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match witness-bound corpus exactly")
        if corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry reference must match corpus")
        if corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy reference must match corpus")
        if corpus.witness_attestation_refs != tuple(
            item.reference() for item in witness_attestations
        ):
            raise ValueError("witness attestation population must match corpus order")
        if corpus.corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("checkpoint log must match witness predecessor")
        if corpus.corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("checkpoint head must match witness predecessor")
        if tuple(item.content_id for item in windows) != corpus.content_ids:
            raise ValueError("execution windows must match frozen content order")

    def _persist_checkpoint_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            report,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        return reference

    def _persist_witness_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored checkpoint witness decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictRevocationWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: (
            WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot
        ),
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_evidence: StoredAdjudicatorCheckpointWitnessEvidence,
        checkpoint_evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        checkpoint_report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
        witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored checkpoint witness final differs")
        if self._store.get(
            final.witness_corpus_ref.artifact_id,
            expected_hash=final.witness_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("witness corpus differs during verification")
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != witness_registry.canonical_payload:
            raise ArtifactIntegrityError("witness registry differs during verification")
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != witness_policy.canonical_payload:
            raise ArtifactIntegrityError("witness policy differs during verification")
        for reference in witness_evidence.attestation_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        for reference in checkpoint_evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        checkpoint_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-verification"
            ),
            checkpoint_report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != checkpoint_artifact.payload:
            raise ArtifactIntegrityError("checkpoint report differs during verification")
        witness_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-decision"
            ),
            witness_decision,
        )
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != witness_artifact.payload:
            raise ArtifactIntegrityError("witness decision differs during verification")
        if final.checkpoint_final_ref is not None:
            self._store.get(
                final.checkpoint_final_ref.artifact_id,
                expected_hash=final.checkpoint_final_ref.artifact_hash,
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
        adjudicator_revocation_policy: PriorRevocationPolicy,
        adjudicator_revocation_ledger: PriorRevocationLedger,
        adjudicator_checkpoint_policy: PriorCheckpointPolicy,
        adjudicator_checkpoint_log: PriorCheckpointLog,
        adjudicator_checkpoints: tuple[PriorCheckpoint, ...],
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
        checkpoint_conflict_adjudicator_revocation_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_checkpoint_log: (
            AdjudicatorCredentialRevocationCheckpointLogSnapshot
        ),
        checkpoint_conflict_adjudicator_revocation_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        checkpoint_conflict_revocation_witness_registry: (
            CheckpointWitnessRegistrySnapshot
        ),
        checkpoint_conflict_revocation_witness_policy: CheckpointWitnessPolicySnapshot,
        checkpoint_conflict_revocation_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        corpus: (
            WitnessBoundAdjudicatorCheckpointConflictCredentialRevocationCheckpointCorpusSnapshot
        ),
        environment: ExecutionEnvironment,
        windows: tuple[ExtractionExecutionWindow, ...],
        experiment_run_id: str,
        checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at: str,
        checkpoint_conflict_revocation_witness_evaluated_at: str,
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
    ) -> VerifiedCheckpointConflictRevocationWitnessReceipt:
        """Return witness abstention or the independently preserved PR #29 outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_registry=checkpoint_conflict_revocation_witness_registry,
                witness_policy=checkpoint_conflict_revocation_witness_policy,
                witness_attestations=checkpoint_conflict_revocation_witness_attestations,
                checkpoint_log=(
                    checkpoint_conflict_adjudicator_revocation_checkpoint_log
                ),
                windows=windows,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=(
                    checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at
                ),
                witness_evaluated_at=(
                    checkpoint_conflict_revocation_witness_evaluated_at
                ),
            )
        except ValueError as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        checkpoint_plan = replace(
            plan,
            corpus_ref=corpus.predecessor_corpus_ref,
            content_ids=corpus.content_ids,
        )
        try:
            witness_evidence = (
                load_witness_evidence(
                    self._store,
                    corpus=corpus,
                    registry=checkpoint_conflict_revocation_witness_registry,
                    policy=checkpoint_conflict_revocation_witness_policy,
                )
            )
            checkpoint_evidence = (
                load_adjudicator_checkpoint_conflict_credential_revocation_checkpoint_evidence(
                    self._store,
                    corpus=corpus.corpus,
                    policy=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                    ),
                    log=checkpoint_conflict_adjudicator_revocation_checkpoint_log,
                )
            )
        except (
            ArtifactStoreError,
            AdjudicatorCheckpointWitnessError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = (
                validate_adjudicator_checkpoint_conflict_credential_revocation_checkpoints(
                    plan=checkpoint_plan,
                    corpus=corpus.corpus,
                    policy=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                    ),
                    log=checkpoint_conflict_adjudicator_revocation_checkpoint_log,
                    ledger=checkpoint_conflict_adjudicator_revocation_ledger,
                    checkpoints=checkpoint_evidence.checkpoints,
                    verified_at=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at
                    ),
                )
            )
        except (AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc

        try:
            checkpoint_report_ref = self._persist_checkpoint_report(
                experiment_run_id=experiment_run_id,
                report=checkpoint_report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = (
                validate_witnesses(
                    plan=plan,
                    corpus=corpus,
                    registry=checkpoint_conflict_revocation_witness_registry,
                    policy=checkpoint_conflict_revocation_witness_policy,
                    head_checkpoint=checkpoint_evidence.checkpoints[-1],
                    attestations=witness_evidence.attestations,
                    evaluated_at=checkpoint_conflict_revocation_witness_evaluated_at,
                )
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.WITNESS_VALIDATION,
                str(exc),
            ) from exc

        try:
            witness_decision_ref = self._persist_witness_decision(
                experiment_run_id=experiment_run_id,
                decision=witness_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: (
            VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt | None
        ) = None
        revocation_outcome: CredentialDecisionOutcome | None = None
        credential_outcome: CredentialDecisionOutcome | None = None
        prior_witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        conflict_outcome: WitnessConflictAdjudicationOutcome | None = None
        adjudicator_revocation_outcome: CredentialDecisionOutcome | None = None
        adjudicator_credential_outcome: CredentialDecisionOutcome | None = None
        reviewer_witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        reviewer_adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        reviewer_revocation_outcome: CredentialDecisionOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        completed_at = checkpoint_conflict_revocation_witness_evaluated_at
        checkpoint_final_ref: StoredArtifactRef | None = None

        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
            try:
                delegated = self._runner.run(
                    plan=checkpoint_plan,
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
                    checkpoint_conflict_adjudicator_revocation_policy=(
                        checkpoint_conflict_adjudicator_revocation_policy
                    ),
                    checkpoint_conflict_adjudicator_revocation_ledger=(
                        checkpoint_conflict_adjudicator_revocation_ledger
                    ),
                    checkpoint_conflict_adjudicator_revocation_events=(
                        checkpoint_conflict_adjudicator_revocation_events
                    ),
                    checkpoint_conflict_adjudicator_revocation_checkpoint_policy=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_policy
                    ),
                    checkpoint_conflict_adjudicator_revocation_checkpoint_log=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_log
                    ),
                    checkpoint_conflict_adjudicator_revocation_checkpoints=(
                        checkpoint_conflict_adjudicator_revocation_checkpoints
                    ),
                    corpus=corpus.corpus,
                    environment=environment,
                    windows=windows,
                    experiment_run_id=experiment_run_id,
                    checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at=(
                        checkpoint_conflict_adjudicator_revocation_checkpoint_verified_at
                    ),
                    checkpoint_conflict_adjudicator_revocation_evaluated_at=(
                        checkpoint_conflict_adjudicator_revocation_evaluated_at
                    ),
                    checkpoint_conflict_credential_evaluated_at=(
                        checkpoint_conflict_credential_evaluated_at
                    ),
                    adjudicator_checkpoint_verified_at=(
                        adjudicator_checkpoint_verified_at
                    ),
                    adjudicator_witness_evaluated_at=adjudicator_witness_evaluated_at,
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
            except (
                CheckpointConflictAdjudicatorRevocationCheckpointExperimentError
            ) as exc:
                raise CheckpointConflictRevocationWitnessExperimentError(
                    CheckpointConflictRevocationWitnessRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc
            checkpoint_final_ref = delegated.final_manifest_ref
            revocation_outcome = delegated.revocation_outcome
            credential_outcome = delegated.credential_outcome
            prior_witness_outcome = delegated.adjudicator_checkpoint_witness_outcome
            conflict_outcome = delegated.conflict_adjudication_outcome
            adjudicator_revocation_outcome = delegated.adjudicator_revocation_outcome
            adjudicator_credential_outcome = delegated.adjudicator_credential_outcome
            reviewer_witness_outcome = delegated.reviewer_checkpoint_witness_outcome
            reviewer_adjudication_outcome = (
                delegated.reviewer_witness_adjudication_outcome
            )
            reviewer_revocation_outcome = delegated.reviewer_revocation_outcome
            terminal_outcome = delegated.terminal_outcome
            completed_at = delegated.completed_at

        final_id = (
            f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
            "adjudicator-credential-revocation-checkpoint-witness-abstention"
            if witness_decision.outcome is CheckpointWitnessDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                "adjudicator-credential-revocation-checkpoint-witness-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:adjudicator-checkpoint-conflict-"
                    "adjudicator-credential-revocation-checkpoint-witness-"
                    "terminal-abstention"
                )
            )
        )
        final = CheckpointConflictRevocationWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictRevocationWitnessRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
            adjudicator_checkpoint_witness_outcome=prior_witness_outcome,
            conflict_adjudication_outcome=conflict_outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=reviewer_witness_outcome,
            reviewer_witness_adjudication_outcome=reviewer_adjudication_outcome,
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            witness_corpus_ref=witness_evidence.corpus_ref,
            witness_registry_ref=witness_evidence.witness_registry_ref,
            witness_policy_ref=witness_evidence.witness_policy_ref,
            witness_attestation_refs=witness_evidence.attestation_refs,
            checkpoint_verification_ref=checkpoint_report_ref,
            witness_decision_ref=witness_decision_ref,
            checkpoint_final_ref=checkpoint_final_ref,
            verified_checks=CHECKPOINT_CONFLICT_REVOCATION_WITNESS_VERIFIED_CHECKS,
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
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.FINAL_PERSISTENCE,
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
                witness_registry=checkpoint_conflict_revocation_witness_registry,
                witness_policy=checkpoint_conflict_revocation_witness_policy,
                witness_evidence=witness_evidence,
                checkpoint_evidence=checkpoint_evidence,
                checkpoint_report=checkpoint_report,
                witness_decision=witness_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictRevocationWitnessExperimentError(
                CheckpointConflictRevocationWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictRevocationWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictRevocationWitnessRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
            adjudicator_checkpoint_witness_outcome=prior_witness_outcome,
            conflict_adjudication_outcome=conflict_outcome,
            adjudicator_revocation_outcome=adjudicator_revocation_outcome,
            adjudicator_credential_outcome=adjudicator_credential_outcome,
            reviewer_checkpoint_witness_outcome=reviewer_witness_outcome,
            reviewer_witness_adjudication_outcome=reviewer_adjudication_outcome,
            reviewer_revocation_outcome=reviewer_revocation_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            witness_corpus_ref=witness_evidence.corpus_ref,
            witness_registry_ref=witness_evidence.witness_registry_ref,
            witness_policy_ref=witness_evidence.witness_policy_ref,
            witness_attestation_refs=witness_evidence.attestation_refs,
            checkpoint_verification_ref=checkpoint_report_ref,
            witness_decision_ref=witness_decision_ref,
            checkpoint_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=CHECKPOINT_CONFLICT_REVOCATION_WITNESS_VERIFIED_CHECKS,
            completed_at=completed_at,
        )
