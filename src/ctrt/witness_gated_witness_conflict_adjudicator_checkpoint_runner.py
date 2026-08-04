"""Gate the witness-conflict adjudicator checkpoint on named observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

import ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints as cp
from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CheckpointExecutor,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialPolicySnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_conflict_witness_adjudication import (
    CheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential import (
    CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
)
from ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot,
)
from ctrt.checkpoint_gated_checkpoint_conflict_witness_adjudication_runner import (
    CheckpointConflictWitnessRevocationCheckpointExperimentError,
    CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner,
    VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    StoredAdjudicatorCheckpointWitnessEvidence,
    WitnessBoundCheckpointCorpusSnapshot,
    load_witness_evidence,
    validate_witness_attestations,
)
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)

CheckpointCorpus = (
    cp.CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
)
CheckpointSnapshot = cp.AdjudicatorCredentialRevocationLedgerCheckpointSnapshot
CheckpointPolicy = cp.AdjudicatorCredentialRevocationCheckpointPolicySnapshot
CheckpointLog = cp.AdjudicatorCredentialRevocationCheckpointLogSnapshot
CheckpointReport = cp.AdjudicatorCredentialRevocationCheckpointVerificationReport
CheckpointEvidence = cp.StoredAdjudicatorCredentialRevocationCheckpointEvidence
load_checkpoint_evidence = (
    cp.load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_evidence
)
validate_checkpoints = (
    cp.validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints
)
RevocationCorpus = (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
)


class WitnessConflictAdjudicatorCheckpointRunnerStage(StrEnum):
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


class WitnessConflictAdjudicatorCheckpointRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class WitnessConflictAdjudicatorCheckpointExperimentError(RuntimeError):
    """Fail-closed error preserving the exact failed stage."""

    def __init__(
        self,
        stage: WitnessConflictAdjudicatorCheckpointRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS = (
    "exact-witness-conflict-adjudicator-checkpoint-witness-registry-bound",
    "exact-witness-conflict-adjudicator-checkpoint-witness-policy-bound",
    "exact-witness-conflict-adjudicator-checkpoint-witness-population-bound",
    "exact-witness-conflict-adjudicator-checkpoint-head-reverified",
    "named-witness-conflict-adjudicator-checkpoint-observations-preserved",
    "witness-conflict-adjudicator-checkpoint-witness-decision-persisted",
    "witness-and-checkpoint-outcomes-finalized-separately",
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
class WitnessConflictAdjudicatorCheckpointFinalManifest:
    """Final marker for named witnesses plus optional delegated checkpoint result."""

    final_id: str
    experiment_run_id: str
    status: WitnessConflictAdjudicatorCheckpointRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
    credential_outcome: CredentialDecisionOutcome | None
    prior_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
        if self.status is not WitnessConflictAdjudicatorCheckpointRunnerStatus.VERIFIED:
            raise ValueError("witness-conflict adjudicator checkpoint status must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("witness final requires unique multiple contents")
        if not self.witness_attestation_refs:
            raise ValueError("witness final requires attestations")
        if len(self.witness_attestation_refs) != len(set(self.witness_attestation_refs)):
            raise ValueError("witness final attestation refs must be unique")
        downstream = (
            self.revocation_outcome,
            self.credential_outcome,
            self.prior_checkpoint_witness_outcome,
            self.resolution_status,
            self.adjudication_outcome,
        )
        prefix = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-witness-"
        )
        if self.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("witness abstention must not contain downstream outcomes")
            if self.checkpoint_final_ref is not None:
                raise ValueError("witness abstention must not contain checkpoint final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("witness abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.checkpoint_final_ref is None or self.revocation_outcome is None:
                raise ValueError("witness execution requires delegated checkpoint outcome")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from witness and terminal outcomes")
        if self.verified_checks != WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS:
            raise ValueError("witness final lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedWitnessConflictAdjudicatorCheckpointReceipt:
    """Proof of named observations plus optional exact PR #34 result."""

    experiment_run_id: str
    status: WitnessConflictAdjudicatorCheckpointRunnerStatus
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome
    revocation_outcome: CredentialDecisionOutcome | None
    credential_outcome: CredentialDecisionOutcome | None
    prior_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
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
    checkpoint_receipt: VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not WitnessConflictAdjudicatorCheckpointRunnerStatus.VERIFIED:
            raise ValueError("verified witness checkpoint status required")
        downstream = (
            self.revocation_outcome,
            self.credential_outcome,
            self.prior_checkpoint_witness_outcome,
            self.resolution_status,
            self.adjudication_outcome,
        )
        prefix = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-witness-"
        )
        if self.checkpoint_witness_outcome is CheckpointWitnessDecisionOutcome.ABSTAIN:
            if self.checkpoint_receipt is not None:
                raise ValueError("witness abstention must not contain checkpoint receipt")
            if any(item is not None for item in downstream):
                raise ValueError("witness abstention must not contain downstream outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.checkpoint_receipt
            if delegated is None:
                raise ValueError("witness execution requires checkpoint receipt")
            if (
                delegated.revocation_outcome is not self.revocation_outcome
                or delegated.credential_outcome is not self.credential_outcome
                or delegated.checkpoint_witness_outcome
                is not self.prior_checkpoint_witness_outcome
                or delegated.resolution_status is not self.resolution_status
                or delegated.adjudication_outcome is not self.adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("checkpoint receipt differs from witness receipt")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong witness outcome")
        if self.verified_checks != WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS:
            raise ValueError("verified witness receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner:
    """Verify current named witnesses before executing exact PR #34."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: WitnessBoundCheckpointCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
        current_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        checkpoint_policy: CheckpointPolicy,
        checkpoint_log: CheckpointLog,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        current_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("checkpoint-witness execution requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match witness-bound corpus exactly")
        if corpus.predecessor_corpus_ref != checkpoint_corpus.reference():
            raise ValueError("witness corpus must bind exact 1.12.0 predecessor")
        if corpus.witness_registry_ref != current_witness_registry.reference():
            raise ValueError("current witness registry reference differs from corpus")
        if corpus.witness_policy_ref != current_witness_policy.reference():
            raise ValueError("current witness policy reference differs from corpus")
        if corpus.witness_attestation_refs != tuple(
            item.reference() for item in current_witness_attestations
        ):
            raise ValueError("current witness population differs from corpus order")
        if checkpoint_corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("checkpoint policy differs from 1.12.0 predecessor")
        if checkpoint_corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("checkpoint log differs from 1.12.0 predecessor")
        if checkpoint_corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("checkpoint head differs from 1.12.0 predecessor")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        checkpoint_time = _parse_timestamp(
            checkpoint_verified_at,
            "checkpoint_verified_at",
        )
        witness_time = _parse_timestamp(
            current_witness_evaluated_at,
            "current_witness_evaluated_at",
        )
        revocation_time = _parse_timestamp(
            revocation_evaluated_at,
            "revocation_evaluated_at",
        )
        completed_time = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= checkpoint_time
            <= witness_time
            <= revocation_time
            <= completed_time
        ):
            raise ValueError("successor, checkpoint, witness, revocation chronology differs")

    def _persist_checkpoint_report(
        self,
        *,
        experiment_run_id: str,
        report: CheckpointReport,
    ) -> StoredArtifactRef:
        artifact_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-witness-checkpoint-verification"
        )
        artifact = serialize_artifact(artifact_id, report)
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
        artifact_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-witness-decision"
        )
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored witness decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: WitnessConflictAdjudicatorCheckpointFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: WitnessBoundCheckpointCorpusSnapshot,
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
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
            raise ArtifactIntegrityError("stored witness final differs")
        if self._store.get(
            final.witness_corpus_ref.artifact_id,
            expected_hash=final.witness_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored witness corpus differs")
        if self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        ).payload != current_witness_registry.canonical_payload:
            raise ArtifactIntegrityError("stored witness registry differs")
        if self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        ).payload != current_witness_policy.canonical_payload:
            raise ArtifactIntegrityError("stored witness policy differs")
        for reference in witness_evidence.attestation_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        for reference in checkpoint_evidence.checkpoint_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        checkpoint_id = (
            f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-witness-checkpoint-verification"
        )
        expected_checkpoint = serialize_artifact(checkpoint_id, checkpoint_report)
        if self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        ).payload != expected_checkpoint.payload:
            raise ArtifactIntegrityError("stored checkpoint report differs")
        witness_id = (
            f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            "checkpoint-witness-decision"
        )
        expected_witness = serialize_artifact(witness_id, witness_decision)
        if self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        ).payload != expected_witness.payload:
            raise ArtifactIntegrityError("stored witness decision differs")
        if final.checkpoint_final_ref is not None:
            self._store.get(
                final.checkpoint_final_ref.artifact_id,
                expected_hash=final.checkpoint_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: WitnessBoundCheckpointCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        revocation_corpus: RevocationCorpus,
        credential_corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        checkpoint_policy: CheckpointPolicy,
        checkpoint_log: CheckpointLog,
        checkpoints: tuple[CheckpointSnapshot, ...],
        current_witness_registry: CheckpointWitnessRegistrySnapshot,
        current_witness_policy: CheckpointWitnessPolicySnapshot,
        current_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        prior_witness_registry: CheckpointWitnessRegistrySnapshot,
        prior_witness_policy: CheckpointWitnessPolicySnapshot,
        prior_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        prior_head_checkpoint: CheckpointSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        prior_witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        current_witness_evaluated_at: str,
        prior_witness_evaluated_at: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        adjudication_evaluated_at: str,
        adjudication_completed_at: str,
        credential_completed_at: str,
        checkpoint_completed_at: str,
        completed_at: str,
    ) -> VerifiedWitnessConflictAdjudicatorCheckpointReceipt:
        """Return witness abstention or the exact delegated PR #34 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                checkpoint_corpus=checkpoint_corpus,
                current_witness_registry=current_witness_registry,
                current_witness_policy=current_witness_policy,
                current_witness_attestations=current_witness_attestations,
                checkpoint_policy=checkpoint_policy,
                checkpoint_log=checkpoint_log,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=checkpoint_verified_at,
                current_witness_evaluated_at=current_witness_evaluated_at,
                revocation_evaluated_at=revocation_evaluated_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.PREFLIGHT,
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
                policy=checkpoint_policy,
                log=checkpoint_log,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCheckpointWitnessError,
            cp.AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = validate_checkpoints(
                plan=checkpoint_plan,
                corpus=checkpoint_corpus,
                policy=checkpoint_policy,
                log=checkpoint_log,
                ledger=revocation_ledger,
                checkpoints=checkpoint_evidence.checkpoints,
                verified_at=checkpoint_verified_at,
                revocation_evaluated_at=revocation_evaluated_at,
            )
        except (cp.AdjudicatorCredentialRevocationCheckpointError, ValueError) as exc:
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.CHECKPOINT_VALIDATION,
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
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_witness_attestations(
                plan=plan,
                corpus=corpus,
                registry=current_witness_registry,
                policy=current_witness_policy,
                head_checkpoint=checkpoint_evidence.checkpoints[-1],
                attestations=witness_evidence.attestations,
                evaluated_at=current_witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.WITNESS_VALIDATION,
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
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCheckpointConflictWitnessRevocationCheckpointReceipt | None = None
        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
            try:
                delegated = self._runner.run(
                    plan=checkpoint_plan,
                    corpus=checkpoint_corpus,
                    revocation_corpus=revocation_corpus,
                    credential_corpus=credential_corpus,
                    adjudication_corpus=adjudication_corpus,
                    checkpoint_policy=checkpoint_policy,
                    checkpoint_log=checkpoint_log,
                    checkpoints=checkpoints,
                    witness_registry=prior_witness_registry,
                    witness_policy=prior_witness_policy,
                    witness_attestations=prior_witness_attestations,
                    head_checkpoint=prior_head_checkpoint,
                    adjudicator_registry=adjudicator_registry,
                    adjudication_policy=adjudication_policy,
                    adjudication=adjudication,
                    issuer_registry=issuer_registry,
                    credential_policy=credential_policy,
                    revocation_policy=revocation_policy,
                    revocation_ledger=revocation_ledger,
                    revocation_events=revocation_events,
                    witness_receipt=prior_witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    checkpoint_verified_at=checkpoint_verified_at,
                    witness_evaluated_at=prior_witness_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=credential_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    adjudication_completed_at=adjudication_completed_at,
                    credential_completed_at=credential_completed_at,
                    revocation_completed_at=checkpoint_completed_at,
                    completed_at=completed_at,
                )
            except CheckpointConflictWitnessRevocationCheckpointExperimentError as exc:
                raise WitnessConflictAdjudicatorCheckpointExperimentError(
                    WitnessConflictAdjudicatorCheckpointRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated is None:
            revocation_outcome = None
            credential_outcome = None
            prior_checkpoint_witness_outcome = None
            resolution_status = None
            adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            checkpoint_final_ref = None
            suffix = "abstention"
        else:
            revocation_outcome = delegated.revocation_outcome
            credential_outcome = delegated.credential_outcome
            prior_checkpoint_witness_outcome = delegated.checkpoint_witness_outcome
            resolution_status = delegated.resolution_status
            adjudication_outcome = delegated.adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            checkpoint_final_ref = delegated.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-"
            f"checkpoint-witness-{suffix}"
        )
        final = WitnessConflictAdjudicatorCheckpointFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=WitnessConflictAdjudicatorCheckpointRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
            prior_checkpoint_witness_outcome=prior_checkpoint_witness_outcome,
            resolution_status=resolution_status,
            adjudication_outcome=adjudication_outcome,
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
            verified_checks=WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS,
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
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.FINAL_PERSISTENCE,
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
                current_witness_registry=current_witness_registry,
                current_witness_policy=current_witness_policy,
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
            raise WitnessConflictAdjudicatorCheckpointExperimentError(
                WitnessConflictAdjudicatorCheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedWitnessConflictAdjudicatorCheckpointReceipt(
            experiment_run_id=experiment_run_id,
            status=WitnessConflictAdjudicatorCheckpointRunnerStatus.VERIFIED,
            checkpoint_witness_outcome=witness_decision.outcome,
            revocation_outcome=revocation_outcome,
            credential_outcome=credential_outcome,
            prior_checkpoint_witness_outcome=prior_checkpoint_witness_outcome,
            resolution_status=resolution_status,
            adjudication_outcome=adjudication_outcome,
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
            verified_checks=WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "WITNESS_CONFLICT_ADJUDICATOR_CHECKPOINT_VERIFIED_CHECKS",
    "VerifiedWitnessConflictAdjudicatorCheckpointReceipt",
    "WitnessConflictAdjudicatorCheckpointExperimentError",
    "WitnessConflictAdjudicatorCheckpointFinalManifest",
    "WitnessConflictAdjudicatorCheckpointRunnerStage",
    "WitnessConflictAdjudicatorCheckpointRunnerStatus",
    "WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner",
]
