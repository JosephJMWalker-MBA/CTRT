"""Gate the exact 1.22.0 checkpoint on immutable named observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from importlib import import_module
from typing import Any

import ctrt.current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints as cp
from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    StoredAdjudicatorCheckpointWitnessEvidence,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_gated_current_checkpoint_witness_conflict_runner import (
    CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner,
    CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError,
    VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt,
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
    WitnessConflictResolutionStatus,
)

CheckpointCorpus = (
    cp.CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
)
CheckpointPolicy = cp.AdjudicatorCredentialRevocationCheckpointPolicySnapshot
CheckpointLog = cp.AdjudicatorCredentialRevocationCheckpointLogSnapshot
CheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
CheckpointReport = cp.AdjudicatorCredentialRevocationCheckpointVerificationReport
CheckpointEvidence = cp.StoredAdjudicatorCredentialRevocationCheckpointEvidence
WitnessCorpus = Any
_witness = import_module(
    "ctrt.current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_witness"
)


def _module_attribute(module: Any, name: str) -> Any:
    return vars(module)[name]


load_witness_evidence = _module_attribute(
    _witness,
    "load_current_conflict_adjudicator_revocation_checkpoint_witness_evidence",
)
validate_witnesses = _module_attribute(
    _witness,
    "validate_current_conflict_adjudicator_revocation_checkpoint_witnesses",
)
load_checkpoint_evidence = _module_attribute(
    cp,
    "load_current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoint_evidence",
)
validate_checkpoints = _module_attribute(
    cp,
    "validate_current_checkpoint_witness_conflict_adjudicator_credential_"
    "revocation_checkpoints",
)

_ARTIFACT_PREFIX = (
    "current-checkpoint-witness-conflict-adjudicator-credential-revocation-"
    "checkpoint-witness"
)


class CurrentRevocationCheckpointWitnessRunnerStage(StrEnum):
    """Boundary at which current revocation-checkpoint witness execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CurrentRevocationCheckpointWitnessRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CurrentRevocationCheckpointWitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CurrentRevocationCheckpointWitnessRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS = (
    "exact-1.22.0-current-conflict-adjudicator-revocation-checkpoint-preserved",
    "exact-current-revocation-checkpoint-witness-registry-bound",
    "exact-current-revocation-checkpoint-witness-policy-bound",
    "exact-current-revocation-checkpoint-witness-population-bound",
    "exact-current-revocation-checkpoint-head-reverified",
    "all-current-revocation-checkpoint-observations-preserved-separately",
    "current-revocation-checkpoint-witness-decision-persisted-before-pr44",
    "witness-and-all-pr44-outcomes-finalized-separately",
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
class CurrentRevocationCheckpointWitnessFinalManifest:
    """Final marker preserving current witnesses and optional PR #44 outcomes."""

    final_id: str
    experiment_run_id: str
    status: CurrentRevocationCheckpointWitnessRunnerStatus
    current_conflict_adjudicator_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome
    )
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    current_conflict_adjudicator_credential_outcome: CredentialDecisionOutcome | None
    conflicting_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_resolution_status: WitnessConflictResolutionStatus | None
    current_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    resolved_current_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_revocation_outcome: CredentialDecisionOutcome | None
    current_credential_outcome: CredentialDecisionOutcome | None
    lower_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    lower_resolution_status: WitnessConflictResolutionStatus | None
    lower_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    lower_predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
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
        expected_status = CurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("current revocation-checkpoint witness status must be verified")
        if not self.witness_attestation_refs:
            raise ValueError("current witness final requires attestations")
        if len(self.witness_attestation_refs) != len(
            set(self.witness_attestation_refs)
        ):
            raise ValueError("current witness attestation refs must be unique")
        downstream = (
            self.current_conflict_adjudicator_revocation_outcome,
            self.current_conflict_adjudicator_credential_outcome,
            self.conflicting_witness_outcome,
            self.current_resolution_status,
            self.current_conflict_adjudication_outcome,
            self.resolved_current_witness_outcome,
            self.current_revocation_outcome,
            self.current_credential_outcome,
            self.lower_checkpoint_witness_outcome,
            self.lower_resolution_status,
            self.lower_conflict_adjudication_outcome,
            self.lower_predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        witness_outcome = (
            self.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
        )
        if witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("current witness abstention may not claim PR #44 outcomes")
            if self.checkpoint_final_ref is not None:
                raise ValueError("current witness abstention may not contain PR #44 final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("current witness abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if (
                self.checkpoint_final_ref is None
                or self.current_conflict_adjudicator_revocation_outcome is None
            ):
                raise ValueError("current witness execution requires PR #44 evidence")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from current witness outcome")
        if self.verified_checks != CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS:
            raise ValueError("current revocation-checkpoint witness final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCurrentRevocationCheckpointWitnessReceipt:
    """Proof of named observations plus optional exact PR #44 result."""

    experiment_run_id: str
    status: CurrentRevocationCheckpointWitnessRunnerStatus
    current_conflict_adjudicator_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome
    )
    current_conflict_adjudicator_revocation_outcome: CredentialDecisionOutcome | None
    current_conflict_adjudicator_credential_outcome: CredentialDecisionOutcome | None
    conflicting_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_resolution_status: WitnessConflictResolutionStatus | None
    current_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    resolved_current_witness_outcome: CheckpointWitnessDecisionOutcome | None
    current_revocation_outcome: CredentialDecisionOutcome | None
    current_credential_outcome: CredentialDecisionOutcome | None
    lower_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    lower_resolution_status: WitnessConflictResolutionStatus | None
    lower_conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    lower_predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
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
        VerifiedCurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointReceipt
        | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = CurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("verified current revocation-checkpoint witness required")
        downstream = (
            self.current_conflict_adjudicator_revocation_outcome,
            self.current_conflict_adjudicator_credential_outcome,
            self.conflicting_witness_outcome,
            self.current_resolution_status,
            self.current_conflict_adjudication_outcome,
            self.resolved_current_witness_outcome,
            self.current_revocation_outcome,
            self.current_credential_outcome,
            self.lower_checkpoint_witness_outcome,
            self.lower_resolution_status,
            self.lower_conflict_adjudication_outcome,
            self.lower_predecessor_witness_outcome,
            self.inherited_revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = f"{self.experiment_run_id}:{_ARTIFACT_PREFIX}-"
        witness_outcome = (
            self.current_conflict_adjudicator_revocation_checkpoint_witness_outcome
        )
        if witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None:
                raise ValueError("current witness abstention may not contain PR #44 receipt")
            if any(item is not None for item in downstream):
                raise ValueError("current witness abstention may not contain outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.checkpoint_receipt
            if delegated is None:
                raise ValueError("current witness execution requires PR #44 receipt")
            if delegated.experiment_run_id != self.experiment_run_id:
                raise ValueError("PR #44 receipt belongs to another experiment run")
            if (
                delegated.current_conflict_adjudicator_revocation_outcome
                is not self.current_conflict_adjudicator_revocation_outcome
                or delegated.current_conflict_adjudicator_credential_outcome
                is not self.current_conflict_adjudicator_credential_outcome
                or delegated.conflicting_witness_outcome
                is not self.conflicting_witness_outcome
                or delegated.current_resolution_status
                is not self.current_resolution_status
                or delegated.current_conflict_adjudication_outcome
                is not self.current_conflict_adjudication_outcome
                or delegated.resolved_current_witness_outcome
                is not self.resolved_current_witness_outcome
                or delegated.current_revocation_outcome
                is not self.current_revocation_outcome
                or delegated.current_credential_outcome
                is not self.current_credential_outcome
                or delegated.lower_checkpoint_witness_outcome
                is not self.lower_checkpoint_witness_outcome
                or delegated.lower_resolution_status
                is not self.lower_resolution_status
                or delegated.lower_conflict_adjudication_outcome
                is not self.lower_conflict_adjudication_outcome
                or delegated.lower_predecessor_witness_outcome
                is not self.lower_predecessor_witness_outcome
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
                raise ValueError("PR #44 receipt differs from current witness receipt")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong current witness outcome")
        if self.verified_checks != CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS:
            raise ValueError("verified current revocation-checkpoint witness lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class WitnessGatedCurrentRevocationCheckpointExperimentRunner:
    """Verify named witnesses before executing the exact PR #44 lifecycle."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: WitnessCorpus,
        checkpoint_corpus: CheckpointCorpus,
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
        current_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        current_checkpoint_policy: CheckpointPolicy,
        current_checkpoint_log: CheckpointLog,
        experiment_run_id: str,
        witness_checkpoint_verified_at: str,
        current_witness_evaluated_at: str,
        current_checkpoint_verified_at: str,
        current_conflict_adjudicator_revocation_evaluated_at: str,
        revocation_completed_at: str,
        current_checkpoint_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("current revocation-checkpoint witnesses require frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match current witness corpus exactly")
        if corpus.predecessor_corpus_ref != checkpoint_corpus.reference():
            raise ValueError("current witness corpus must bind exact 1.22.0 predecessor")
        if corpus.witness_registry_ref != current_witness_registry.reference():
            raise ValueError("current witness registry differs from corpus")
        if corpus.witness_policy_ref != current_witness_policy.reference():
            raise ValueError("current witness policy differs from corpus")
        expected_attestations = tuple(
            item.reference() for item in current_witness_attestations
        )
        if corpus.witness_attestation_refs != expected_attestations:
            raise ValueError("current witness population differs from corpus order")
        if checkpoint_corpus.checkpoint_policy_ref != current_checkpoint_policy.reference():
            raise ValueError("current checkpoint policy differs from 1.22.0")
        if checkpoint_corpus.checkpoint_log_ref != current_checkpoint_log.reference():
            raise ValueError("current checkpoint log differs from 1.22.0")
        if checkpoint_corpus.checkpoint_head_ref != (
            current_checkpoint_log.head_checkpoint_ref
        ):
            raise ValueError("current checkpoint head differs from 1.22.0")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        witness_checkpoint_time = _parse_timestamp(
            witness_checkpoint_verified_at,
            "witness_checkpoint_verified_at",
        )
        witness_time = _parse_timestamp(
            current_witness_evaluated_at,
            "current_witness_evaluated_at",
        )
        delegated_checkpoint_time = _parse_timestamp(
            current_checkpoint_verified_at,
            "current_checkpoint_verified_at",
        )
        revocation_time = _parse_timestamp(
            current_conflict_adjudicator_revocation_evaluated_at,
            "current_conflict_adjudicator_revocation_evaluated_at",
        )
        revocation_completed = _parse_timestamp(
            revocation_completed_at,
            "revocation_completed_at",
        )
        checkpoint_completed = _parse_timestamp(
            current_checkpoint_completed_at,
            "current_checkpoint_completed_at",
        )
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= witness_checkpoint_time
            <= witness_time
            <= delegated_checkpoint_time
            <= revocation_time
            <= revocation_completed
            <= checkpoint_completed
            <= completed
        ):
            raise ValueError(
                "successor, witness, checkpoint, revocation chronology differs"
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
        final: CurrentRevocationCheckpointWitnessFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: WitnessCorpus,
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
            raise ArtifactIntegrityError("stored 1.23.0 witness corpus differs")
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
        corpus: WitnessCorpus,
        checkpoint_corpus: CheckpointCorpus,
        current_checkpoint_policy: CheckpointPolicy,
        current_checkpoint_log: CheckpointLog,
        current_checkpoints: tuple[CheckpointSnapshot, ...],
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
        current_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        current_conflict_adjudicator_revocation_ledger: Any,
        experiment_run_id: str,
        witness_checkpoint_verified_at: str,
        current_witness_evaluated_at: str,
        current_checkpoint_verified_at: str,
        current_conflict_adjudicator_revocation_evaluated_at: str,
        revocation_completed_at: str,
        current_checkpoint_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> VerifiedCurrentRevocationCheckpointWitnessReceipt:
        """Return witness abstention or the exact delegated PR #44 result."""

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
                witness_checkpoint_verified_at=witness_checkpoint_verified_at,
                current_witness_evaluated_at=current_witness_evaluated_at,
                current_checkpoint_verified_at=current_checkpoint_verified_at,
                current_conflict_adjudicator_revocation_evaluated_at=(
                    current_conflict_adjudicator_revocation_evaluated_at
                ),
                revocation_completed_at=revocation_completed_at,
                current_checkpoint_completed_at=current_checkpoint_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        checkpoint_plan = replace(
            plan,
            corpus_ref=checkpoint_corpus.reference(),
            content_ids=checkpoint_corpus.content_ids,
        )
        try:
            witness_evidence = load_witness_evidence(
                self._store,
                corpus=corpus,
                registry=current_witness_registry,
                policy=current_witness_policy,
            )
            checkpoint_evidence = load_checkpoint_evidence(
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
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = validate_checkpoints(
                plan=checkpoint_plan,
                corpus=checkpoint_corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
                ledger=current_conflict_adjudicator_revocation_ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=witness_checkpoint_verified_at,
                revocation_evaluated_at=current_witness_evaluated_at,
            )
        except (
            cp.AdjudicatorCredentialRevocationCheckpointError,
            ValueError,
        ) as exc:
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.CHECKPOINT_VALIDATION,
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
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_witnesses(
                plan=plan,
                corpus=corpus,
                registry=current_witness_registry,
                policy=current_witness_policy,
                head_checkpoint=checkpoint_evidence.checkpoints[-1],
                attestations=witness_evidence.attestations,
                evaluated_at=current_witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.WITNESS_VALIDATION,
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
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        checkpoint_receipt = None
        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
            try:
                checkpoint_receipt = self._runner.run(
                    plan=checkpoint_plan,
                    corpus=checkpoint_corpus,
                    current_checkpoint_policy=current_checkpoint_policy,
                    current_checkpoint_log=current_checkpoint_log,
                    current_checkpoints=current_checkpoints,
                    current_conflict_adjudicator_revocation_ledger=(
                        current_conflict_adjudicator_revocation_ledger
                    ),
                    experiment_run_id=experiment_run_id,
                    current_checkpoint_verified_at=current_checkpoint_verified_at,
                    current_conflict_adjudicator_revocation_evaluated_at=(
                        current_conflict_adjudicator_revocation_evaluated_at
                    ),
                    revocation_completed_at=revocation_completed_at,
                    completed_at=current_checkpoint_completed_at,
                    **delegated,
                )
            except (
                CurrentCheckpointWitnessConflictAdjudicatorRevocationCheckpointExperimentError
            ) as exc:
                raise CurrentRevocationCheckpointWitnessExperimentError(
                    CurrentRevocationCheckpointWitnessRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if checkpoint_receipt is None:
            current_conflict_adjudicator_revocation_outcome = None
            current_conflict_adjudicator_credential_outcome = None
            conflicting_witness_outcome = None
            current_resolution_status = None
            current_conflict_adjudication_outcome = None
            resolved_current_witness_outcome = None
            current_revocation_outcome = None
            current_credential_outcome = None
            lower_checkpoint_witness_outcome = None
            lower_resolution_status = None
            lower_conflict_adjudication_outcome = None
            lower_predecessor_witness_outcome = None
            inherited_revocation_outcome = None
            inherited_credential_outcome = None
            inherited_checkpoint_witness_outcome = None
            inherited_resolution_status = None
            inherited_adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            checkpoint_final_ref = None
            suffix = "abstention"
        else:
            current_conflict_adjudicator_revocation_outcome = (
                checkpoint_receipt.current_conflict_adjudicator_revocation_outcome
            )
            current_conflict_adjudicator_credential_outcome = (
                checkpoint_receipt.current_conflict_adjudicator_credential_outcome
            )
            conflicting_witness_outcome = checkpoint_receipt.conflicting_witness_outcome
            current_resolution_status = checkpoint_receipt.current_resolution_status
            current_conflict_adjudication_outcome = (
                checkpoint_receipt.current_conflict_adjudication_outcome
            )
            resolved_current_witness_outcome = (
                checkpoint_receipt.resolved_current_witness_outcome
            )
            current_revocation_outcome = checkpoint_receipt.current_revocation_outcome
            current_credential_outcome = checkpoint_receipt.current_credential_outcome
            lower_checkpoint_witness_outcome = (
                checkpoint_receipt.lower_checkpoint_witness_outcome
            )
            lower_resolution_status = checkpoint_receipt.lower_resolution_status
            lower_conflict_adjudication_outcome = (
                checkpoint_receipt.lower_conflict_adjudication_outcome
            )
            lower_predecessor_witness_outcome = (
                checkpoint_receipt.lower_predecessor_witness_outcome
            )
            inherited_revocation_outcome = (
                checkpoint_receipt.inherited_revocation_outcome
            )
            inherited_credential_outcome = (
                checkpoint_receipt.inherited_credential_outcome
            )
            inherited_checkpoint_witness_outcome = (
                checkpoint_receipt.inherited_checkpoint_witness_outcome
            )
            inherited_resolution_status = (
                checkpoint_receipt.inherited_resolution_status
            )
            inherited_adjudication_outcome = (
                checkpoint_receipt.inherited_adjudication_outcome
            )
            terminal_outcome = checkpoint_receipt.terminal_outcome
            checkpoint_final_ref = checkpoint_receipt.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CurrentRevocationCheckpointWitnessFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED,
            current_conflict_adjudicator_revocation_checkpoint_witness_outcome=(
                witness_decision.outcome
            ),
            current_conflict_adjudicator_revocation_outcome=(
                current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=conflicting_witness_outcome,
            current_resolution_status=current_resolution_status,
            current_conflict_adjudication_outcome=(
                current_conflict_adjudication_outcome
            ),
            resolved_current_witness_outcome=resolved_current_witness_outcome,
            current_revocation_outcome=current_revocation_outcome,
            current_credential_outcome=current_credential_outcome,
            lower_checkpoint_witness_outcome=lower_checkpoint_witness_outcome,
            lower_resolution_status=lower_resolution_status,
            lower_conflict_adjudication_outcome=(
                lower_conflict_adjudication_outcome
            ),
            lower_predecessor_witness_outcome=lower_predecessor_witness_outcome,
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
            verified_checks=CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
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
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.FINAL_PERSISTENCE,
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
            raise CurrentRevocationCheckpointWitnessExperimentError(
                CurrentRevocationCheckpointWitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCurrentRevocationCheckpointWitnessReceipt(
            experiment_run_id=experiment_run_id,
            status=CurrentRevocationCheckpointWitnessRunnerStatus.VERIFIED,
            current_conflict_adjudicator_revocation_checkpoint_witness_outcome=(
                witness_decision.outcome
            ),
            current_conflict_adjudicator_revocation_outcome=(
                current_conflict_adjudicator_revocation_outcome
            ),
            current_conflict_adjudicator_credential_outcome=(
                current_conflict_adjudicator_credential_outcome
            ),
            conflicting_witness_outcome=conflicting_witness_outcome,
            current_resolution_status=current_resolution_status,
            current_conflict_adjudication_outcome=(
                current_conflict_adjudication_outcome
            ),
            resolved_current_witness_outcome=resolved_current_witness_outcome,
            current_revocation_outcome=current_revocation_outcome,
            current_credential_outcome=current_credential_outcome,
            lower_checkpoint_witness_outcome=lower_checkpoint_witness_outcome,
            lower_resolution_status=lower_resolution_status,
            lower_conflict_adjudication_outcome=(
                lower_conflict_adjudication_outcome
            ),
            lower_predecessor_witness_outcome=lower_predecessor_witness_outcome,
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
            checkpoint_receipt=checkpoint_receipt,
            final_manifest_ref=final_ref,
            verified_checks=CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CURRENT_REVOCATION_CHECKPOINT_WITNESS_VERIFIED_CHECKS",
    "CurrentRevocationCheckpointWitnessExperimentError",
    "CurrentRevocationCheckpointWitnessFinalManifest",
    "CurrentRevocationCheckpointWitnessRunnerStage",
    "CurrentRevocationCheckpointWitnessRunnerStatus",
    "VerifiedCurrentRevocationCheckpointWitnessReceipt",
    "WitnessGatedCurrentRevocationCheckpointExperimentRunner",
]
