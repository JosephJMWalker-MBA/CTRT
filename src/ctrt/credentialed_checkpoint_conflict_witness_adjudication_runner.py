"""Gate checkpoint-conflict witness adjudication on exact issuer credentials."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner,
    CheckpointConflictWitnessAdjudicationExperimentError,
    CheckpointExecutor,
    VerifiedCheckpointConflictWitnessAdjudicationReceipt,
)
from ctrt.adjudicator_checkpoint_conflict_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialDecisionReport,
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
    CheckpointConflictWitnessAdjudicatorCredentialError,
    CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
    StoredCredentialEvidence,
    load_checkpoint_conflict_witness_adjudicator_credential_evidence,
    validate_checkpoint_conflict_witness_adjudicator_credentials,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
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
from ctrt.witness_gated_adjudicator_checkpoint_conflict_runner import (
    VerifiedCheckpointConflictRevocationWitnessReceipt,
)


class CheckpointConflictWitnessCredentialRunnerStage(StrEnum):
    """Boundary at which credential-gated adjudication failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    CREDENTIAL_DECISION_PERSISTENCE = "credential-decision-persistence"
    ADJUDICATION_EXECUTION = "adjudication-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CheckpointConflictWitnessCredentialRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CheckpointConflictWitnessCredentialExperimentError(RuntimeError):
    """Fail-closed error preserving the exact failed stage."""

    def __init__(
        self,
        stage: CheckpointConflictWitnessCredentialRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS = (
    "exact-witness-conflict-adjudicator-identity-revision-bound",
    "exact-witness-conflict-adjudicator-role-attested",
    "issuer-and-credential-policy-reverified",
    "credential-validity-evaluated-before-adjudication",
    "credential-abstention-precedes-adjudication-execution",
    "witness-fork-dissent-and-selected-head-left-immutable",
    "credential-and-adjudication-outcomes-finalized-separately",
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
class CheckpointConflictWitnessCredentialFinalManifest:
    """Final marker for credential abstention or delegated adjudication."""

    final_id: str
    experiment_run_id: str
    status: CheckpointConflictWitnessCredentialRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    predecessor_adjudication_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudication_final_ref: StoredArtifactRef | None
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictWitnessCredentialRunnerStatus.VERIFIED:
            raise ValueError("checkpoint-conflict witness credential status must be verified")
        if not self.credential_attestation_refs:
            raise ValueError("credential final requires at least one attestation")
        downstream = (
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.adjudication_outcome,
            self.adjudication_final_ref,
        )
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("credential abstention may not claim adjudication outcomes")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("credential abstention must be terminal")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-abstention"
            )
        else:
            if any(item is None for item in downstream):
                raise ValueError("credential execution requires delegated adjudication")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudicator-credential-terminal-abstention"
                )
            )
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from credential terminal outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS
        ):
            raise ValueError("checkpoint-conflict witness credential final lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCheckpointConflictWitnessCredentialReceipt:
    """Proof of credential eligibility and optional PR #31 adjudication."""

    experiment_run_id: str
    status: CheckpointConflictWitnessCredentialRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    predecessor_adjudication_corpus_ref: VersionedArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudication_receipt: VerifiedCheckpointConflictWitnessAdjudicationReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.status is not CheckpointConflictWitnessCredentialRunnerStatus.VERIFIED:
            raise ValueError("verified checkpoint-conflict witness credential required")
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.adjudication_receipt is not None:
                raise ValueError("credential abstention may not contain adjudication receipt")
            if any(
                item is not None
                for item in (
                    self.checkpoint_witness_outcome,
                    self.resolution_status,
                    self.adjudication_outcome,
                )
            ):
                raise ValueError("credential abstention may not contain outcomes")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-abstention"
            )
        else:
            delegated = self.adjudication_receipt
            if delegated is None:
                raise ValueError("credential execution requires adjudication receipt")
            if (
                delegated.checkpoint_witness_outcome
                is not self.checkpoint_witness_outcome
                or delegated.resolution_status is not self.resolution_status
                or delegated.adjudication_outcome is not self.adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("adjudication receipt differs from credential receipt")
            expected_id = (
                f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudicator-credential-terminal-abstention"
                )
            )
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong credential outcome")
        if (
            self.verified_checks
            != CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS
        ):
            raise ValueError("verified credential receipt lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner:
    """Require eligible credentials before executing the exact PR #31 runner."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        witness_evaluated_at: str,
        credential_evaluated_at: str,
        adjudication_evaluated_at: str,
        adjudication_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("credential-gated adjudication requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match credential-bound corpus exactly")
        if corpus.predecessor_corpus_ref != adjudication_corpus.reference():
            raise ValueError("credential corpus must bind exact 1.9.0 predecessor")
        if corpus.corpus.adjudicator_registry_ref != adjudicator_registry.reference():
            raise ValueError("adjudicator registry reference differs from corpus")
        if corpus.issuer_registry_ref != issuer_registry.reference():
            raise ValueError("issuer registry reference differs from corpus")
        if corpus.credential_policy_ref != credential_policy.reference():
            raise ValueError("credential policy reference differs from corpus")
        if corpus.corpus.adjudication_ref != adjudication.reference():
            raise ValueError("adjudication record reference differs from corpus")
        witness_time = _parse_timestamp(witness_evaluated_at, "witness_evaluated_at")
        credential_time = _parse_timestamp(
            credential_evaluated_at,
            "credential_evaluated_at",
        )
        adjudication_time = _parse_timestamp(
            adjudication_evaluated_at,
            "adjudication_evaluated_at",
        )
        adjudication_completed = _parse_timestamp(
            adjudication_completed_at,
            "adjudication_completed_at",
        )
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            witness_time <= credential_time <= adjudication_time
            <= adjudication_completed <= completed
        ):
            raise ValueError("witness, credential, adjudication, and completion chronology differs")

    def _persist_decision(
        self,
        *,
        experiment_run_id: str,
        decision: AdjudicatorCredentialDecisionReport,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(
            (
                f"{experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-decision"
            ),
            decision,
        )
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored witness-conflict credential decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CheckpointConflictWitnessCredentialFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        evidence: StoredCredentialEvidence,
        decision: AdjudicatorCredentialDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored witness-conflict credential final differs")
        if self._store.get(
            evidence.corpus_ref.artifact_id,
            expected_hash=evidence.corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("credential-bound corpus differs")
        for reference in (
            evidence.adjudicator_registry_ref,
            evidence.issuer_registry_ref,
            evidence.credential_policy_ref,
            evidence.adjudication_ref,
            *evidence.attestation_refs,
        ):
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        self._store.get(
            final.predecessor_adjudication_corpus_ref.artifact_id,
            expected_hash=final.predecessor_adjudication_corpus_ref.artifact_hash,
        )
        expected_decision = serialize_artifact(
            (
                f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-decision"
            ),
            decision,
        )
        if self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError("credential decision differs during verification")
        if final.adjudication_final_ref is not None:
            self._store.get(
                final.adjudication_final_ref.artifact_id,
                expected_hash=final.adjudication_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot,
        adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        head_checkpoint: AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
        adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        adjudication: WitnessConflictAdjudicationSnapshot,
        issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: AdjudicatorCredentialPolicySnapshot,
        credentials: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
        witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
        witness_evaluated_at: str,
        credential_evaluated_at: str,
        adjudication_evaluated_at: str,
        adjudication_completed_at: str,
        completed_at: str,
    ) -> VerifiedCheckpointConflictWitnessCredentialReceipt:
        """Return credential abstention or the independently verified PR #31 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                adjudication_corpus=adjudication_corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                adjudication=adjudication,
                experiment_run_id=experiment_run_id,
                witness_evaluated_at=witness_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                adjudication_evaluated_at=adjudication_evaluated_at,
                adjudication_completed_at=adjudication_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CheckpointConflictWitnessCredentialExperimentError(
                CheckpointConflictWitnessCredentialRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_checkpoint_conflict_witness_adjudicator_credential_evidence(
                self._store,
                corpus=corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                adjudication=adjudication,
            )
        except (ArtifactStoreError, OSError, ValueError) as exc:
            raise CheckpointConflictWitnessCredentialExperimentError(
                CheckpointConflictWitnessCredentialRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_checkpoint_conflict_witness_adjudicator_credentials(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=adjudicator_registry,
                issuer_registry=issuer_registry,
                credential_policy=credential_policy,
                attestations=credentials,
                adjudication=adjudication,
                evaluated_at=credential_evaluated_at,
            )
        except (CheckpointConflictWitnessAdjudicatorCredentialError, ValueError) as exc:
            raise CheckpointConflictWitnessCredentialExperimentError(
                CheckpointConflictWitnessCredentialRunnerStage.CREDENTIAL_VALIDATION,
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
            raise CheckpointConflictWitnessCredentialExperimentError(
                CheckpointConflictWitnessCredentialRunnerStage.CREDENTIAL_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedCheckpointConflictWitnessAdjudicationReceipt | None = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            adjudication_plan = replace(
                plan,
                corpus_ref=adjudication_corpus.reference(),
                content_ids=adjudication_corpus.content_ids,
            )
            try:
                delegated = self._runner.run(
                    plan=adjudication_plan,
                    corpus=adjudication_corpus,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    witness_attestations=witness_attestations,
                    head_checkpoint=head_checkpoint,
                    adjudicator_registry=adjudicator_registry,
                    adjudication_policy=adjudication_policy,
                    adjudication=adjudication,
                    witness_receipt=witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    witness_evaluated_at=witness_evaluated_at,
                    adjudication_evaluated_at=adjudication_evaluated_at,
                    completed_at=adjudication_completed_at,
                )
            except CheckpointConflictWitnessAdjudicationExperimentError as exc:
                raise CheckpointConflictWitnessCredentialExperimentError(
                    CheckpointConflictWitnessCredentialRunnerStage.ADJUDICATION_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None = None
        resolution_status: WitnessConflictResolutionStatus | None = None
        adjudication_outcome: WitnessConflictAdjudicationOutcome | None = None
        terminal_outcome = ReviewDecisionOutcome.ABSTAIN
        adjudication_final_ref: StoredArtifactRef | None = None
        if delegated is not None:
            checkpoint_witness_outcome = delegated.checkpoint_witness_outcome
            resolution_status = delegated.resolution_status
            adjudication_outcome = delegated.adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            adjudication_final_ref = delegated.final_manifest_ref

        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-abstention"
            if decision.outcome is CredentialDecisionOutcome.ABSTAIN
            else (
                f"{experiment_run_id}:checkpoint-conflict-revocation-"
                "witness-conflict-adjudicator-credential-completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else (
                    f"{experiment_run_id}:checkpoint-conflict-revocation-"
                    "witness-conflict-adjudicator-credential-terminal-abstention"
                )
            )
        )
        final = CheckpointConflictWitnessCredentialFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessCredentialRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            adjudication_outcome=adjudication_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=evidence.corpus_ref,
            predecessor_adjudication_corpus_ref=corpus.predecessor_corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=decision_ref,
            adjudication_final_ref=adjudication_final_ref,
            verified_checks=CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS,
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
            raise CheckpointConflictWitnessCredentialExperimentError(
                CheckpointConflictWitnessCredentialRunnerStage.FINAL_PERSISTENCE,
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
            raise CheckpointConflictWitnessCredentialExperimentError(
                CheckpointConflictWitnessCredentialRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCheckpointConflictWitnessCredentialReceipt(
            experiment_run_id=experiment_run_id,
            status=CheckpointConflictWitnessCredentialRunnerStatus.VERIFIED,
            credential_outcome=decision.outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            adjudication_outcome=adjudication_outcome,
            terminal_outcome=terminal_outcome,
            experiment_id=plan.experiment_id,
            experiment_version=plan.experiment_version,
            content_ids=plan.content_ids,
            credential_corpus_ref=evidence.corpus_ref,
            predecessor_adjudication_corpus_ref=corpus.predecessor_corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=decision_ref,
            adjudication_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CHECKPOINT_CONFLICT_WITNESS_CREDENTIAL_VERIFIED_CHECKS",
    "CheckpointConflictWitnessCredentialExperimentError",
    "CheckpointConflictWitnessCredentialFinalManifest",
    "CheckpointConflictWitnessCredentialRunnerStage",
    "CheckpointConflictWitnessCredentialRunnerStatus",
    "CredentialedCheckpointConflictWitnessAdjudicationExperimentRunner",
    "VerifiedCheckpointConflictWitnessCredentialReceipt",
]
