"""Gate the exact 1.17.0 checkpoint on immutable named observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

import ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints as cp
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_gated_checkpoint_witness_conflict_adjudication_runner import (
    CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner,
    CheckpointWitnessConflictRevocationCheckpointExperimentError,
    VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_witness import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
    load_current_checkpoint_witness_evidence,
    validate_current_checkpoint_witness_attestations,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import CredentialDecisionOutcome
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictResolutionStatus,
)

CheckpointCorpus = (
    cp.CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
)
CheckpointPolicy = cp.AdjudicatorCredentialRevocationCheckpointPolicySnapshot
CheckpointLog = cp.AdjudicatorCredentialRevocationCheckpointLogSnapshot
CheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
CheckpointReport = cp.AdjudicatorCredentialRevocationCheckpointVerificationReport
CheckpointEvidence = cp.StoredAdjudicatorCredentialRevocationCheckpointEvidence

_ARTIFACT_PREFIX = (
    "checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-"
    "revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint-witness"
)


class CurrentCheckpointWitnessRunnerStage(StrEnum):
    """Boundary at which current named-witness execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CurrentCheckpointWitnessRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CurrentCheckpointWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CurrentCheckpointWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS = (
    "exact-1.17.0-checkpoint-predecessor-preserved",
    "exact-current-checkpoint-witness-registry-bound",
    "exact-current-checkpoint-witness-policy-bound",
    "exact-current-checkpoint-witness-population-bound",
    "exact-current-checkpoint-head-reverified",
    "all-current-named-observations-preserved-separately",
    "current-witness-decision-persisted-before-pr39",
    "witness-and-all-delegated-outcomes-finalized-separately",
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
class CurrentCheckpointWitnessFinalManifest:
    """Final marker preserving current witnesses and optional PR #39 outcomes."""

    final_id: str
    experiment_run_id: str
    status: CurrentCheckpointWitnessRunnerStatus
    current_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
        if self.status is not CurrentCheckpointWitnessRunnerStatus.VERIFIED:
            raise ValueError("current checkpoint witness status must be verified")
        if not self.witness_attestation_refs:
            raise ValueError("current checkpoint witness final requires attestations")
        if len(self.witness_attestation_refs) != len(
            set(self.witness_attestation_refs)
        ):
            raise ValueError("current witness attestation refs must be unique")
        downstream = (
            self.revocation_outcome,
            self.credential_outcome,
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.conflict_adjudication_outcome,
            self.predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if (
            self.current_checkpoint_witness_outcome
            is CheckpointWitnessDecisionOutcome.ABSTAIN
        ):
            if any(item is not None for item in downstream):
                raise ValueError("current witness abstention may not claim downstream outcomes")
            if self.checkpoint_final_ref is not None:
                raise ValueError("current witness abstention may not contain PR #39 final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("current witness abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.checkpoint_final_ref is None or self.revocation_outcome is None:
                raise ValueError("current witness execution requires PR #39 evidence")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from witness terminal outcome")
        if self.verified_checks != CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS:
            raise ValueError("current checkpoint witness final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCurrentCheckpointWitnessReceipt:
    """Proof of current named observations plus optional exact PR #39 result."""

    experiment_run_id: str
    status: CurrentCheckpointWitnessRunnerStatus
    current_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
    credential_outcome: CredentialDecisionOutcome | None
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
        VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CurrentCheckpointWitnessRunnerStatus.VERIFIED:
            raise ValueError("verified current checkpoint witness status required")
        downstream = (
            self.revocation_outcome,
            self.credential_outcome,
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.conflict_adjudication_outcome,
            self.predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        if (
            self.current_checkpoint_witness_outcome
            is CheckpointWitnessDecisionOutcome.ABSTAIN
        ):
            if self.checkpoint_receipt is not None:
                raise ValueError("current witness abstention may not contain PR #39 receipt")
            if any(item is not None for item in downstream):
                raise ValueError("current witness abstention may not contain outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.checkpoint_receipt
            if delegated is None:
                raise ValueError("current witness execution requires PR #39 receipt")
            if delegated.experiment_run_id != self.experiment_run_id:
                raise ValueError("PR #39 receipt belongs to another experiment run")
            if (
                delegated.revocation_outcome is not self.revocation_outcome
                or delegated.credential_outcome is not self.credential_outcome
                or delegated.checkpoint_witness_outcome
                is not self.checkpoint_witness_outcome
                or delegated.resolution_status is not self.resolution_status
                or delegated.conflict_adjudication_outcome
                is not self.conflict_adjudication_outcome
                or delegated.predecessor_witness_outcome
                is not self.predecessor_witness_outcome
                or delegated.inherited_revocation_outcome
                is not self.inherited_revocation_outcome
                or delegated.inherited_credential_outcome
                is not self.inherited_credential_outcome
                or delegated.inherited_checkpoint_witness_outcome
                is not self.inherited_checkpoint_witness_outcome
                or delegated.inherited_resolution_status
                is not self.inherited_resolution_status
                or delegated.inherited_adjudication_outcome
                is not self.inherited_adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("PR #39 receipt differs from current witness receipt")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong current witness outcome")
        if self.verified_checks != CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS:
            raise ValueError("verified current checkpoint witness lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class WitnessGatedCurrentCheckpointExperimentRunner:
    """Verify current named witnesses before executing exact PR #39."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = (
            CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner(
                artifact_store=artifact_store
            )
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: WitnessBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
        current_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        current_checkpoint_policy: CheckpointPolicy,
        current_checkpoint_log: CheckpointLog,
        experiment_run_id: str,
        current_checkpoint_verified_at: str,
        current_witness_evaluated_at: str,
        current_revocation_evaluated_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("current checkpoint witness execution requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match current witness corpus exactly")
        if corpus.predecessor_corpus_ref != checkpoint_corpus.reference():
            raise ValueError("current witness corpus must bind exact 1.17.0 predecessor")
        if corpus.witness_registry_ref != current_witness_registry.reference():
            raise ValueError("current witness registry differs from corpus")
        if corpus.witness_policy_ref != current_witness_policy.reference():
            raise ValueError("current witness policy differs from corpus")
        if corpus.witness_attestation_refs != tuple(
            item.reference() for item in current_witness_attestations
        ):
            raise ValueError("current witness population differs from corpus order")
        if checkpoint_corpus.checkpoint_policy_ref != current_checkpoint_policy.reference():
            raise ValueError("current checkpoint policy differs from 1.17.0")
        if checkpoint_corpus.checkpoint_log_ref != current_checkpoint_log.reference():
            raise ValueError("current checkpoint log differs from 1.17.0")
        if checkpoint_corpus.checkpoint_head_ref != current_checkpoint_log.head_checkpoint_ref:
            raise ValueError("current checkpoint head differs from 1.17.0")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        checkpoint_time = _parse_timestamp(
            current_checkpoint_verified_at,
            "current_checkpoint_verified_at",
        )
        witness_time = _parse_timestamp(
            current_witness_evaluated_at,
            "current_witness_evaluated_at",
        )
        revocation_time = _parse_timestamp(
            current_revocation_evaluated_at,
            "current_revocation_evaluated_at",
        )
        completed_time = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= checkpoint_time
            <= witness_time
            <= revocation_time
            <= completed_time
        ):
            raise ValueError(
                "successor, checkpoint, witness, revocation chronology differs"
            )

    def _persist_checkpoint_report(
        self,
        *,
        experiment_run_id: str,
        report: CheckpointReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-checkpoint-verification"
        artifact = serialize_artifact(artifact_id, report)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored current checkpoint report differs")
        return reference

    def _persist_witness_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision"
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored current witness decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CurrentCheckpointWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: WitnessBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
        registry: CheckpointWitnessRegistrySnapshot,
        policy: CheckpointWitnessPolicySnapshot,
        witness_evidence: StoredAdjudicatorCheckpointWitnessEvidence,
        checkpoint_evidence: CheckpointEvidence,
        checkpoint_report: CheckpointReport,
        witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored current witness final differs")
        if self._store.get(
            final.witness_corpus_ref.artifact_id,
            expected_hash=final.witness_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.18.0 witness corpus differs")
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != registry.canonical_payload:
            raise ArtifactIntegrityError("stored current witness registry differs")
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored current witness policy differs")
        for reference in witness_evidence.attestation_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        for reference in checkpoint_evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        expected_checkpoint = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-checkpoint-verification",
            checkpoint_report,
        )
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != expected_checkpoint.payload:
            raise ArtifactIntegrityError("stored current checkpoint report differs")
        expected_witness = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            witness_decision,
        )
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != expected_witness.payload:
            raise ArtifactIntegrityError("stored current witness decision differs")
        if final.checkpoint_final_ref is not None:
            self._store.get(
                final.checkpoint_final_ref.artifact_id,
                expected_hash=final.checkpoint_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: WitnessBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        current_checkpoint_policy: CheckpointPolicy,
        current_checkpoint_log: CheckpointLog,
        current_checkpoints: tuple[CheckpointSnapshot, ...],
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
        current_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        current_revocation_corpus: Any,
        credential_corpus: Any,
        adjudication_corpus: Any,
        witness_predecessor: Any,
        inherited_checkpoint_corpus: Any,
        inherited_revocation_corpus: Any,
        inherited_credential_corpus: Any,
        inherited_adjudication_corpus: Any,
        inherited_checkpoint_policy: Any,
        inherited_checkpoint_log: Any,
        inherited_checkpoints: tuple[Any, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        predecessor_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        conflict_adjudicator_registry: Any,
        conflict_adjudication_policy: Any,
        conflict_adjudication: Any,
        current_issuer_registry: Any,
        current_credential_policy: Any,
        current_revocation_policy: Any,
        current_revocation_ledger: Any,
        current_revocation_events: tuple[Any, ...],
        inherited_witness_registry: CheckpointWitnessRegistrySnapshot,
        inherited_witness_policy: CheckpointWitnessPolicySnapshot,
        inherited_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        inherited_head_checkpoint: Any,
        inherited_adjudicator_registry: Any,
        inherited_adjudication_policy: Any,
        inherited_adjudication: Any,
        inherited_issuer_registry: Any,
        inherited_credential_policy: Any,
        revocation_policy: Any,
        revocation_ledger: Any,
        revocation_events: tuple[Any, ...],
        inherited_witness_receipt: Any,
        checkpoint_executor: Any,
        experiment_run_id: str,
        current_checkpoint_verified_at: str,
        current_witness_evaluated_at: str,
        current_revocation_evaluated_at: str,
        current_credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_verified_at: str,
        predecessor_witness_evaluated_at: str,
        inherited_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        inherited_credential_evaluated_at: str,
        inherited_adjudication_evaluated_at: str,
        inherited_adjudication_completed_at: str,
        inherited_credential_completed_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        prior_completed_at: str,
        current_revocation_completed_at: str,
        current_checkpoint_completed_at: str,
        completed_at: str,
    ) -> VerifiedCurrentCheckpointWitnessReceipt:
        """Return witness abstention or the exact delegated PR #39 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                checkpoint_corpus=checkpoint_corpus,
                current_witness_registry=current_witness_registry,
                current_witness_policy=current_witness_policy,
                current_witness_attestations=current_witness_attestations,
                current_checkpoint_policy=current_checkpoint_policy,
                current_checkpoint_log=current_checkpoint_log,
                experiment_run_id=experiment_run_id,
                current_checkpoint_verified_at=current_checkpoint_verified_at,
                current_witness_evaluated_at=current_witness_evaluated_at,
                current_revocation_evaluated_at=current_revocation_evaluated_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        checkpoint_plan = replace(
            plan,
            corpus_ref=checkpoint_corpus.reference(),
            content_ids=checkpoint_corpus.content_ids,
        )
        try:
            witness_evidence = load_current_checkpoint_witness_evidence(
                self._store,
                corpus=corpus,
                registry=current_witness_registry,
                policy=current_witness_policy,
            )
            checkpoint_evidence = cp.load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence(
                self._store,
                corpus=checkpoint_corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCheckpointWitnessError,
            cp.AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = cp.validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints(
                plan=checkpoint_plan,
                corpus=checkpoint_corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
                ledger=current_revocation_ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=current_checkpoint_verified_at,
                revocation_evaluated_at=current_revocation_evaluated_at,
            )
        except (cp.AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_current_checkpoint_witness_attestations(
                plan=plan,
                corpus=corpus,
                registry=current_witness_registry,
                policy=current_witness_policy,
                head_checkpoint=checkpoint_evidence.checkpoints[-1],
                attestations=witness_evidence.attestations,
                evaluated_at=current_witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.WITNESS_VALIDATION,
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
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCheckpointWitnessConflictRevocationCheckpointReceipt | None = None
        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
            try:
                delegated = self._runner.run(
                    plan=checkpoint_plan,
                    corpus=checkpoint_corpus,
                    current_revocation_corpus=current_revocation_corpus,
                    credential_corpus=credential_corpus,
                    adjudication_corpus=adjudication_corpus,
                    witness_predecessor=witness_predecessor,
                    checkpoint_corpus=inherited_checkpoint_corpus,
                    revocation_corpus=inherited_revocation_corpus,
                    inherited_credential_corpus=inherited_credential_corpus,
                    inherited_adjudication_corpus=inherited_adjudication_corpus,
                    current_checkpoint_policy=current_checkpoint_policy,
                    current_checkpoint_log=current_checkpoint_log,
                    current_checkpoints=current_checkpoints,
                    checkpoint_policy=inherited_checkpoint_policy,
                    checkpoint_log=inherited_checkpoint_log,
                    checkpoints=inherited_checkpoints,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    conflict_witness_attestations=conflict_witness_attestations,
                    predecessor_witness_attestations=predecessor_witness_attestations,
                    conflict_adjudicator_registry=conflict_adjudicator_registry,
                    conflict_adjudication_policy=conflict_adjudication_policy,
                    conflict_adjudication=conflict_adjudication,
                    current_issuer_registry=current_issuer_registry,
                    current_credential_policy=current_credential_policy,
                    current_revocation_policy=current_revocation_policy,
                    current_revocation_ledger=current_revocation_ledger,
                    current_revocation_events=current_revocation_events,
                    inherited_witness_registry=inherited_witness_registry,
                    inherited_witness_policy=inherited_witness_policy,
                    inherited_witness_attestations=inherited_witness_attestations,
                    inherited_head_checkpoint=inherited_head_checkpoint,
                    inherited_adjudicator_registry=inherited_adjudicator_registry,
                    inherited_adjudication_policy=inherited_adjudication_policy,
                    inherited_adjudication=inherited_adjudication,
                    inherited_issuer_registry=inherited_issuer_registry,
                    inherited_credential_policy=inherited_credential_policy,
                    revocation_policy=revocation_policy,
                    revocation_ledger=revocation_ledger,
                    revocation_events=revocation_events,
                    inherited_witness_receipt=inherited_witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    current_checkpoint_verified_at=current_checkpoint_verified_at,
                    current_revocation_evaluated_at=current_revocation_evaluated_at,
                    current_credential_evaluated_at=current_credential_evaluated_at,
                    conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                    conflict_adjudication_evaluated_at=(
                        conflict_adjudication_evaluated_at
                    ),
                    checkpoint_verified_at=checkpoint_verified_at,
                    predecessor_witness_evaluated_at=predecessor_witness_evaluated_at,
                    inherited_witness_evaluated_at=inherited_witness_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    inherited_credential_evaluated_at=(
                        inherited_credential_evaluated_at
                    ),
                    inherited_adjudication_evaluated_at=(
                        inherited_adjudication_evaluated_at
                    ),
                    inherited_adjudication_completed_at=(
                        inherited_adjudication_completed_at
                    ),
                    inherited_credential_completed_at=(
                        inherited_credential_completed_at
                    ),
                    revocation_completed_at=revocation_completed_at,
                    checkpoint_completed_at=checkpoint_completed_at,
                    prior_completed_at=prior_completed_at,
                    current_revocation_completed_at=current_revocation_completed_at,
                    completed_at=current_checkpoint_completed_at,
                )
            except CheckpointWitnessConflictRevocationCheckpointExperimentError as exc:
                raise CurrentCheckpointWitnessExperimentError(
                    CurrentCheckpointWitnessRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated is None:
            revocation_outcome = None
            credential_outcome = None
            checkpoint_witness_outcome = None
            resolution_status = None
            conflict_adjudication_outcome = None
            predecessor_witness_outcome = None
            inherited_revocation_outcome = None
            inherited_credential_outcome = None
            inherited_checkpoint_witness_outcome = None
            inherited_resolution_status = None
            inherited_adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            checkpoint_final_ref = None
            suffix = "abstention"
        else:
            revocation_outcome = delegated.revocation_outcome
            credential_outcome = delegated.credential_outcome
            checkpoint_witness_outcome = delegated.checkpoint_witness_outcome
            resolution_status = delegated.resolution_status
            conflict_adjudication_outcome = delegated.conflict_adjudication_outcome
            predecessor_witness_outcome = delegated.predecessor_witness_outcome
            inherited_revocation_outcome = delegated.inherited_revocation_outcome
            inherited_credential_outcome = delegated.inherited_credential_outcome
            inherited_checkpoint_witness_outcome = (
                delegated.inherited_checkpoint_witness_outcome
            )
            inherited_resolution_status = delegated.inherited_resolution_status
            inherited_adjudication_outcome = delegated.inherited_adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            checkpoint_final_ref = delegated.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CurrentCheckpointWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CurrentCheckpointWitnessRunnerStatus.VERIFIED,
            current_checkpoint_witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
            inherited_revocation_outcome=inherited_revocation_outcome,
            inherited_credential_outcome=inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=inherited_resolution_status,
            inherited_adjudication_outcome=inherited_adjudication_outcome,
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
            verified_checks=CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
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
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.FINAL_PERSISTENCE,
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
                registry=current_witness_registry,
                policy=current_witness_policy,
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
            raise CurrentCheckpointWitnessExperimentError(
                CurrentCheckpointWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCurrentCheckpointWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=CurrentCheckpointWitnessRunnerStatus.VERIFIED,
            current_checkpoint_witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
            inherited_revocation_outcome=inherited_revocation_outcome,
            inherited_credential_outcome=inherited_credential_outcome,
            inherited_checkpoint_witness_outcome=(
                inherited_checkpoint_witness_outcome
            ),
            inherited_resolution_status=inherited_resolution_status,
            inherited_adjudication_outcome=inherited_adjudication_outcome,
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
            verified_checks=CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CURRENT_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
    "CurrentCheckpointWitnessExperimentError",
    "CurrentCheckpointWitnessFinalManifest",
    "CurrentCheckpointWitnessRunnerStage",
    "CurrentCheckpointWitnessRunnerStatus",
    "VerifiedCurrentCheckpointWitnessReceipt",
    "WitnessGatedCurrentCheckpointExperimentRunner",
]
