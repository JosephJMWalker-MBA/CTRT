"""Apply authorized adjudication to preserved checkpoint-conflict witness evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_conflict_revocation_witness import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    validate_witnesses,
)
from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
    ConflictAdjudicationError,
    ConflictDecisionReport,
    StoredConflictAdjudicationEvidence,
    load_checkpoint_conflict_witness_adjudication_evidence,
    validate_checkpoint_conflict_witness_adjudication,
)
from ctrt.checkpoint_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)


class CheckpointExecutor(Protocol):
    """Execute the exact lower checkpoint lifecycle after resolved conflict."""

    def __call__(
        self,
        *,
        plan: ExperimentPlan,
        corpus: Any,
        experiment_run_id: str,
    ) -> VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt: ...


class CheckpointConflictWitnessAdjudicationRunnerStage(StrEnum):
    """Boundary at which adjudication-gated execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    WITNESS_REVALIDATION = "witness-revalidation"
    ADJUDICATION_VALIDATION = "adjudication-validation"
    ADJUDICATION_DECISION_PERSISTENCE = "adjudication-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictWitnessAdjudicationRunnerStatus(StrEnum):
    """A receipt exists only after final storage reverification."""

    VERIFIED = "verified"


class CheckpointConflictWitnessAdjudicationExperimentError(RuntimeError):
    """Fail-closed error preserving the exact failed stage."""

    def __init__(
        self,
        stage: CheckpointConflictWitnessAdjudicationRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS = (
    "original-checkpoint-conflict-witness-outcome-preserved",
    "exact-conflict-adjudicator-registry-and-policy-bound",
    "fork-evidence-and-dissent-reverified",
    "resolved-head-restricted-to-verified-checkpoint-head",
    "pending-and-unresolved-conflicts-abstain",
    "witness-count-never-used-as-authority",
    "adjudication-and-checkpoint-outcomes-finalized-separately",
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
class CheckpointConflictWitnessAdjudicationFinalManifest:
    """Final marker preserving witness, adjudication, and checkpoint outcomes."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictWitnessAdjudicationRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    resolution_status: WitnessConflictResolutionStatus
    adjudication_outcome: WitnessConflictAdjudicationOutcome
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
    adjudication_corpus_ref: StoredArtifactRef
    predecessor_witness_corpus_ref: StoredArtifactRef
    witness_final_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    checkpoint_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictWitnessAdjudicationRunnerStatus.VERIFIED:
            raise ValueError("checkpoint-conflict adjudication status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("checkpoint-conflict adjudication requires unique contents")
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
        if self.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("adjudication abstention may not claim downstream outcomes")
            if self.checkpoint_final_ref is not None:
                raise ValueError("adjudication abstention may not claim checkpoint final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("adjudication abstention must be terminal")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-abstention"
            )
        else:
            if self.checkpoint_final_ref is None or self.revocation_outcome is None:
                raise ValueError("adjudication execution requires checkpoint outcome")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudication-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from adjudication terminal outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint-conflict adjudication final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictWitnessAdjudicationReceipt:
    """Proof of preserved witness abstention and separate adjudication outcome."""

    experiment_run_id: str
    status: CheckpointConflictWitnessAdjudicationRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    resolution_status: WitnessConflictResolutionStatus
    adjudication_outcome: WitnessConflictAdjudicationOutcome
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    adjudication_corpus_ref: StoredArtifactRef
    predecessor_witness_corpus_ref: StoredArtifactRef
    witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt
    adjudicator_registry_ref: StoredArtifactRef
    adjudication_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    adjudication_decision_ref: StoredArtifactRef
    checkpoint_receipt: (
        VerifiedCheckpointConflictAdjudicatorRevocationCheckpointReceipt | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictWitnessAdjudicationRunnerStatus.VERIFIED:
            raise ValueError("verified checkpoint-conflict adjudication status required")
        if (
            self.witness_receipt.checkpoint_witness_outcome
            is not self.checkpoint_witness_outcome
        ):
            raise ValueError("outer witness outcome differs from preserved receipt")
        if self.adjudication_outcome is WitnessConflictAdjudicationOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None:
                raise ValueError("adjudication abstention may not contain checkpoint receipt")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-abstention"
            )
        else:
            if self.checkpoint_receipt is None:
                raise ValueError("adjudication execution requires checkpoint receipt")
            if self.checkpoint_receipt.terminal_outcome is not self.terminal_outcome:
                raise ValueError("checkpoint receipt differs from terminal outcome")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudication-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong adjudication outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS
        ):
            raise ValueError("verified adjudication receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner:
    """Apply adjudication to an exact verified PR #30 witness receipt."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        completed_at: str,
    ) -> None:
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-conflict adjudication requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match adjudication-bound corpus exactly")
        if witness_receipt.experiment_run_id != experiment_run_id:
            raise ValueError("witness receipt run ID differs")
        if (
            witness_receipt.experiment_id != plan.experiment_id
            or witness_receipt.experiment_version != plan.experiment_version
            or witness_receipt.content_ids != plan.content_ids
        ):
            raise ValueError("witness receipt experiment scope differs")
        if (
            witness_receipt.witness_corpus_ref.artifact_id
            != corpus.predecessor_corpus_ref.artifact_id
            or witness_receipt.witness_corpus_ref.artifact_hash
            != corpus.predecessor_corpus_ref.artifact_hash
        ):
            raise ValueError("witness receipt does not bind exact 1.8.0 predecessor")
        if corpus.adjudicator_registry_ref != adjudicator_registry.reference():
            raise ValueError("adjudicator registry reference differs from corpus")
        if corpus.adjudication_policy_ref != adjudication_policy.reference():
            raise ValueError("adjudication policy reference differs from corpus")
        if corpus.adjudication_ref != adjudication.reference():
            raise ValueError("adjudication record reference differs from corpus")
        witness_time = _parse_timestamp(witness_evaluated_at, "witness_evaluated_at")
        adjudication_time = _parse_timestamp(
            adjudication_evaluated_at,
            "adjudication_evaluated_at",
        )
        completed = _parse_timestamp(completed_at, "completed_at")
        if witness_time > adjudication_time or adjudication_time > completed:
            raise ValueError("witness, adjudication, and completion chronology differs")

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: ConflictDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored witness adjudication decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictWitnessAdjudicationFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        evidence: StoredConflictAdjudicationEvidence,
        decision: ConflictDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored witness adjudication final differs")
        if self._store.get(
            final.adjudication_corpus_ref.artifact_id,
            expected_hash=final.adjudication_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("adjudication corpus differs during verification")
        for reference in (
            evidence.adjudicator_registry_ref,
            evidence.adjudication_policy_ref,
            evidence.adjudication_ref,
            final.predecessor_witness_corpus_ref,
            final.witness_final_ref,
        ):
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        decision_artifact = serialize_artifact(
            (
                f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-decision"
            ),
            decision,
        )
        if self._store.get(
            final.adjudication_decision_ref.artifact_id,
            expected_hash=final.adjudication_decision_ref.artifact_hash,
        ).payload != decision_artifact.payload:
            raise ArtifactIntegrityError("adjudication decision differs during verification")
        if final.checkpoint_final_ref is not None:
            self._store.get(
                final.checkpoint_final_ref.artifact_id,
                expected_hash=final.checkpoint_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        witness_evaluated_at: str,
        adjudication_evaluated_at: str,
        completed_at: str,
    ) -> VerifiedCheckpointConflictWitnessAdjudicationReceipt:
        """Return verified adjudication abstention or checkpoint outcome."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_receipt=witness_receipt,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                adjudication=adjudication,
                experiment_run_id=experiment_run_id,
                witness_evaluated_at=witness_evaluated_at,
                adjudication_evaluated_at=adjudication_evaluated_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_checkpoint_conflict_witness_adjudication_evidence(
                self._store,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                adjudication=adjudication,
            )
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            witness_decision: AdjudicatorCheckpointWitnessDecisionReport = (
                validate_witnesses(
                    plan=plan,
                    corpus=corpus.corpus,
                    registry=witness_registry,
                    policy=witness_policy,
                    head_checkpoint=head_checkpoint,
                    attestations=witness_attestations,
                    evaluated_at=witness_evaluated_at,
                )
            )
            if witness_decision.outcome is not witness_receipt.checkpoint_witness_outcome:
                raise ValueError("revalidated witness outcome differs from prior receipt")
            if (
                tuple(item.reference() for item in witness_attestations)
                != witness_receipt.witness_attestation_refs
            ):
                raise ValueError("witness receipt attestation population differs")
            self._store.get(
                witness_receipt.witness_decision_ref.artifact_id,
                expected_hash=witness_receipt.witness_decision_ref.artifact_hash,
            )
            self._store.get(
                witness_receipt.final_manifest_ref.artifact_id,
                expected_hash=witness_receipt.final_manifest_ref.artifact_hash,
            )
        except (AdjudicatorCheckpointWitnessError, ArtifactStoreError, ValueError) as exc:
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.WITNESS_REVALIDATION,
                str(exc),
            ) from exc

        try:
            decision = validate_checkpoint_conflict_witness_adjudication(
                plan=plan,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=adjudicator_registry,
                adjudication_policy=adjudication_policy,
                witness_decision=witness_decision,
                adjudication=adjudication,
                evaluated_at=adjudication_evaluated_at,
            )
        except (ConflictAdjudicationError, ValueError) as exc:
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.ADJUDICATION_VALIDATION,
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
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.ADJUDICATION_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        checkpoint_receipt = witness_receipt.checkpoint_receipt
        if decision.outcome is WitnessConflictAdjudicationOutcome.EXECUTE:
            if checkpoint_receipt is None:
                if checkpoint_executor is None:
                    raise CheckpointConflictWitnessAdjudicationExperimentError(
                        CheckpointConflictWitnessAdjudicationRunnerStage.CHECKPOINT_EXECUTION,
                        "resolved conflict requires checkpoint executor",
                    )
                checkpoint_plan = replace(
                    plan,
                    corpus_ref=corpus.corpus.predecessor_corpus_ref,
                    content_ids=corpus.content_ids,
                )
                try:
                    checkpoint_receipt = checkpoint_executor(
                        plan=checkpoint_plan,
                        corpus=corpus.corpus.corpus,
                        experiment_run_id=experiment_run_id,
                    )
                except Exception as exc:
                    raise CheckpointConflictWitnessAdjudicationExperimentError(
                        CheckpointConflictWitnessAdjudicationRunnerStage.CHECKPOINT_EXECUTION,
                        str(exc),
                    ) from exc
            if (
                checkpoint_receipt.experiment_run_id != experiment_run_id
                or checkpoint_receipt.experiment_id != plan.experiment_id
                or checkpoint_receipt.experiment_version != plan.experiment_version
                or checkpoint_receipt.content_ids != plan.content_ids
            ):
                raise CheckpointConflictWitnessAdjudicationExperimentError(
                    CheckpointConflictWitnessAdjudicationRunnerStage.CHECKPOINT_EXECUTION,
                    "checkpoint receipt experiment scope differs",
                )

        if checkpoint_receipt is None:
            revocation_outcome = None
            credential_outcome = None
            adjudicator_checkpoint_witness_outcome = None
            conflict_adjudication_outcome = None
            adjudicator_revocation_outcome = None
            adjudicator_credential_outcome = None
            reviewer_checkpoint_witness_outcome = None
            reviewer_witness_adjudication_outcome = None
            reviewer_revocation_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            checkpoint_final_ref = None
        else:
            revocation_outcome = checkpoint_receipt.revocation_outcome
            credential_outcome = checkpoint_receipt.credential_outcome
            adjudicator_checkpoint_witness_outcome = (
                checkpoint_receipt.adjudicator_checkpoint_witness_outcome
            )
            conflict_adjudication_outcome = (
                checkpoint_receipt.conflict_adjudication_outcome
            )
            adjudicator_revocation_outcome = (
                checkpoint_receipt.adjudicator_revocation_outcome
            )
            adjudicator_credential_outcome = (
                checkpoint_receipt.adjudicator_credential_outcome
            )
            reviewer_checkpoint_witness_outcome = (
                checkpoint_receipt.reviewer_checkpoint_witness_outcome
            )
            reviewer_witness_adjudication_outcome = (
                checkpoint_receipt.reviewer_witness_adjudication_outcome
            )
            reviewer_revocation_outcome = checkpoint_receipt.reviewer_revocation_outcome
            terminal_outcome = checkpoint_receipt.terminal_outcome
            checkpoint_final_ref = checkpoint_receipt.final_manifest_ref

        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudication-abstention"
            if decision.outcome is WitnessConflictAdjudicationOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudication-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudication-terminal-abstention"
                )
            )
        )
        final = CheckpointConflictWitnessAdjudicationFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessAdjudicationRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            resolution_status=decision.resolution_status,
            adjudication_outcome=decision.outcome,
            revocation_outcome=revocation_outcome,
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
            adjudication_corpus_ref=evidence.corpus_ref,
            predecessor_witness_corpus_ref=witness_receipt.witness_corpus_ref,
            witness_final_ref=witness_receipt.final_manifest_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            adjudication_policy_ref=evidence.adjudication_policy_ref,
            adjudication_ref=evidence.adjudication_ref,
            adjudication_decision_ref=decision_ref,
            checkpoint_final_ref=checkpoint_final_ref,
            verified_checks=CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS,
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
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.FINAL_PERSISTENCE,
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
                evidence=evidence,
                decision=decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CheckpointConflictWitnessAdjudicationExperimentError(
                CheckpointConflictWitnessAdjudicationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictWitnessAdjudicationReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessAdjudicationRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            resolution_status=decision.resolution_status,
            adjudication_outcome=decision.outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            adjudication_corpus_ref=evidence.corpus_ref,
            predecessor_witness_corpus_ref=witness_receipt.witness_corpus_ref,
            witness_receipt=witness_receipt,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            adjudication_policy_ref=evidence.adjudication_policy_ref,
            adjudication_ref=evidence.adjudication_ref,
            adjudication_decision_ref=decision_ref,
            checkpoint_receipt=checkpoint_receipt,
            final_manifest_ref=final_ref,
            verified_checks=CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CHECKPOINT_CONFLICT_WITNESS_ADJUDICATION_VERIFIED_CHECKS",
    "AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner",
    "CheckpointConflictWitnessAdjudicationExperimentError",
    "CheckpointConflictWitnessAdjudicationFinalManifest",
    "CheckpointConflictWitnessAdjudicationRunnerStage",
    "CheckpointConflictWitnessAdjudicationRunnerStatus",
    "CheckpointExecutor",
    "VerifiedCheckpointConflictWitnessAdjudicationReceipt",
]
