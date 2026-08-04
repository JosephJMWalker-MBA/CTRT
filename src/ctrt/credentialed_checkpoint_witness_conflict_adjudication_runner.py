"""Gate the exact `1.14.0` conflict adjudication on issuer credentials."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

import ctrt.checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints as cp
from ctrt.adjudicated_checkpoint_conflict_revocation_witness_runner import (
    CheckpointExecutor,
)
from ctrt.adjudicated_witness_conflict_adjudicator_checkpoint_runner import (
    AdjudicatedCheckpointWitnessConflictExperimentError,
    AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner,
    VerifiedAdjudicatedCheckpointWitnessConflictReceipt,
)
from ctrt.adjudicator_credential_attestation import AdjudicatorCredentialPolicySnapshot
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
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.checkpoint_witness_conflict_adjudicator_credential import (
    CredentialAttestationSnapshot,
    CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
    CredentialDecisionReport,
    CredentialError,
    CredentialPolicySnapshot,
    StoredCredentialEvidence,
    load_checkpoint_witness_conflict_credential_evidence,
    validate_checkpoint_witness_conflict_credentials,
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
    WitnessBoundCheckpointCorpusSnapshot,
)
from ctrt.witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCheckpointWitnessCorpusSnapshot,
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
RevocationCorpus = (
    RevocationBoundCheckpointConflictWitnessAdjudicatorCredentialCorpusSnapshot
)


class CredentialedCheckpointWitnessConflictRunnerStage(StrEnum):
    """Boundary at which the current credential gate failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    CREDENTIAL_DECISION_PERSISTENCE = "credential-decision-persistence"
    ADJUDICATION_EXECUTION = "adjudication-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CredentialedCheckpointWitnessConflictRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CredentialedCheckpointWitnessConflictExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CredentialedCheckpointWitnessConflictRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS = (
    "exact-1.14.0-adjudication-predecessor-preserved",
    "exact-conflict-adjudicator-registry-bound",
    "exact-conflict-adjudicator-credential-issuer-registry-bound",
    "exact-conflict-adjudicator-credential-policy-bound",
    "exact-conflict-adjudicator-identity-revision-bound",
    "exact-witness-conflict-adjudicator-role-bound",
    "credential-validity-window-evaluated",
    "credential-decision-persisted-before-adjudication-execution",
    "credential-and-downstream-outcomes-finalized-separately",
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
class CredentialedCheckpointWitnessConflictFinalManifest:
    """Final marker preserving credential and all delegated outcomes separately."""

    final_id: str
    experiment_run_id: str
    status: CredentialedCheckpointWitnessConflictRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
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
        expected_status = CredentialedCheckpointWitnessConflictRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("credentialed checkpoint-witness conflict must be verified")
        if len(self.content_ids) < 2 or len(self.content_ids) != len(set(self.content_ids)):
            raise ValueError("credentialed conflict requires unique multiple contents")
        if not self.credential_attestation_refs:
            raise ValueError("credentialed conflict requires credential attestations")
        if len(self.credential_attestation_refs) != len(
            set(self.credential_attestation_refs)
        ):
            raise ValueError("credential attestation refs must be unique")
        downstream = (
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.conflict_adjudication_outcome,
            self.predecessor_witness_outcome,
            self.revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudicator-credential-"
        )
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if any(item is not None for item in downstream):
                raise ValueError("credential abstention must not contain downstream outcomes")
            if self.adjudication_final_ref is not None:
                raise ValueError("credential abstention must not contain adjudication final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("credential abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.adjudication_final_ref is None:
                raise ValueError("credential execution requires PR #36 final")
            if self.checkpoint_witness_outcome is None:
                raise ValueError("credential execution requires delegated outcomes")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from credential and terminal outcomes")
        if self.verified_checks != CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS:
            raise ValueError("credentialed conflict final lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCredentialedCheckpointWitnessConflictReceipt:
    """Proof of the current credential gate plus optional exact PR #36 result."""

    experiment_run_id: str
    status: CredentialedCheckpointWitnessConflictRunnerStatus
    credential_outcome: CredentialDecisionOutcome
    checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    resolution_status: WitnessConflictResolutionStatus | None
    conflict_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    predecessor_witness_outcome: CheckpointWitnessDecisionOutcome | None
    revocation_outcome: CredentialDecisionOutcome | None
    inherited_credential_outcome: CredentialDecisionOutcome | None
    inherited_checkpoint_witness_outcome: CheckpointWitnessDecisionOutcome | None
    inherited_resolution_status: WitnessConflictResolutionStatus | None
    inherited_adjudication_outcome: WitnessConflictAdjudicationOutcome | None
    terminal_outcome: ReviewDecisionOutcome
    experiment_id: str
    experiment_version: str
    content_ids: tuple[str, ...]
    credential_corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudication_receipt: VerifiedAdjudicatedCheckpointWitnessConflictReceipt | None
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = CredentialedCheckpointWitnessConflictRunnerStatus.VERIFIED
        if self.status is not expected_status:
            raise ValueError("verified credentialed checkpoint conflict status required")
        downstream = (
            self.checkpoint_witness_outcome,
            self.resolution_status,
            self.conflict_adjudication_outcome,
            self.predecessor_witness_outcome,
            self.revocation_outcome,
            self.inherited_credential_outcome,
            self.inherited_checkpoint_witness_outcome,
            self.inherited_resolution_status,
            self.inherited_adjudication_outcome,
        )
        prefix = (
            f"{self.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudicator-credential-"
        )
        if self.credential_outcome is CredentialDecisionOutcome.ABSTAIN:
            if self.adjudication_receipt is not None:
                raise ValueError("credential abstention must not contain PR #36 receipt")
            if any(item is not None for item in downstream):
                raise ValueError("credential abstention must not contain downstream outcomes")
            expected_id = prefix + "abstention"
        else:
            delegated = self.adjudication_receipt
            if delegated is None:
                raise ValueError("credential execution requires PR #36 receipt")
            if (
                delegated.checkpoint_witness_outcome
                is not self.checkpoint_witness_outcome
                or delegated.resolution_status is not self.resolution_status
                or delegated.conflict_adjudication_outcome
                is not self.conflict_adjudication_outcome
                or delegated.predecessor_witness_outcome
                is not self.predecessor_witness_outcome
                or delegated.revocation_outcome is not self.revocation_outcome
                or delegated.credential_outcome
                is not self.inherited_credential_outcome
                or delegated.inherited_checkpoint_witness_outcome
                is not self.inherited_checkpoint_witness_outcome
                or delegated.inherited_resolution_status
                is not self.inherited_resolution_status
                or delegated.inherited_adjudication_outcome
                is not self.inherited_adjudication_outcome
                or delegated.terminal_outcome is not self.terminal_outcome
            ):
                raise ValueError("PR #36 receipt differs from credentialed receipt")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong credential outcome")
        if self.verified_checks != CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS:
            raise ValueError("verified credentialed conflict lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CredentialedCheckpointWitnessConflictExperimentRunner:
    """Validate `1.15.0` credentials before executing exact PR #36."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        current_issuer_registry: CredentialIssuerRegistrySnapshot,
        current_credential_policy: CredentialPolicySnapshot,
        current_credentials: tuple[CredentialAttestationSnapshot, ...],
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        current_credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("credentialed checkpoint conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match credential-bound corpus exactly")
        if corpus.predecessor_corpus_ref != adjudication_corpus.reference():
            raise ValueError("credential corpus must bind exact 1.14.0 predecessor")
        if corpus.corpus.reference() != adjudication_corpus.reference():
            raise ValueError("credential corpus carries different 1.14.0 predecessor")
        if (
            corpus.corpus.adjudicator_registry_ref
            != conflict_adjudicator_registry.reference()
        ):
            raise ValueError("conflict adjudicator registry differs from 1.14.0")
        if corpus.issuer_registry_ref != current_issuer_registry.reference():
            raise ValueError("current credential issuer registry differs from corpus")
        if corpus.credential_policy_ref != current_credential_policy.reference():
            raise ValueError("current credential policy differs from corpus")
        if corpus.credential_entries != tuple(
            base_entry
            for base_entry in corpus.credential_entries
        ):
            raise ValueError("credential entry population is unstable")
        if tuple(item.reference() for item in current_credentials) != tuple(
            item.credential_attestation_ref for item in corpus.credential_entries
        ):
            raise ValueError("current credential population differs from corpus order")
        if corpus.corpus.adjudication_ref != conflict_adjudication.reference():
            raise ValueError("current adjudication differs from credential predecessor")
        successor_time = _parse_timestamp(corpus.created_at, "corpus.created_at")
        credential_time = _parse_timestamp(
            current_credential_evaluated_at,
            "current_credential_evaluated_at",
        )
        witness_time = _parse_timestamp(
            conflict_witness_evaluated_at,
            "conflict_witness_evaluated_at",
        )
        prior_completed = _parse_timestamp(prior_completed_at, "prior_completed_at")
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor_time
            <= credential_time
            <= witness_time
            <= prior_completed
            <= completed
        ):
            raise ValueError("credential and PR #36 chronology differs")

    def _persist_credential_decision(
        self,
        *,
        experiment_run_id: str,
        decision: CredentialDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudicator-credential-decision"
        )
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored current credential decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CredentialedCheckpointWitnessConflictFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        evidence: StoredCredentialEvidence,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        current_issuer_registry: CredentialIssuerRegistrySnapshot,
        current_credential_policy: CredentialPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        credential_decision: CredentialDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored credentialed conflict final differs")
        if self._store.get(
            final.credential_corpus_ref.artifact_id,
            expected_hash=final.credential_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored credential corpus differs")
        if self._store.get(
            corpus.predecessor_corpus_ref.artifact_id,
            expected_hash=corpus.predecessor_corpus_ref.artifact_hash,
        ).payload != corpus.corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.14.0 predecessor differs")
        if self._store.get(
            final.adjudicator_registry_ref.artifact_id,
            expected_hash=final.adjudicator_registry_ref.artifact_hash,
        ).payload != conflict_adjudicator_registry.canonical_payload:
            raise ArtifactIntegrityError("stored conflict adjudicator registry differs")
        if self._store.get(
            final.issuer_registry_ref.artifact_id,
            expected_hash=final.issuer_registry_ref.artifact_hash,
        ).payload != current_issuer_registry.canonical_payload:
            raise ArtifactIntegrityError("stored current credential issuer differs")
        if self._store.get(
            final.credential_policy_ref.artifact_id,
            expected_hash=final.credential_policy_ref.artifact_hash,
        ).payload != current_credential_policy.canonical_payload:
            raise ArtifactIntegrityError("stored current credential policy differs")
        for reference in evidence.attestation_refs:
            self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        if self._store.get(
            final.adjudication_ref.artifact_id,
            expected_hash=final.adjudication_ref.artifact_hash,
        ).payload != conflict_adjudication.canonical_payload:
            raise ArtifactIntegrityError("stored current adjudication differs")
        decision_id = (
            f"{final.experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            "witness-conflict-adjudicator-credential-decision"
        )
        expected_decision = serialize_artifact(decision_id, credential_decision)
        if self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError("stored current credential decision differs")
        if final.adjudication_final_ref is not None:
            self._store.get(
                final.adjudication_final_ref.artifact_id,
                expected_hash=final.adjudication_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: AdjudicationBoundCheckpointWitnessCorpusSnapshot,
        witness_predecessor: WitnessBoundCheckpointCorpusSnapshot,
        checkpoint_corpus: CheckpointCorpus,
        revocation_corpus: RevocationCorpus,
        inherited_credential_corpus: (
            CredentialBoundCheckpointConflictWitnessAdjudicationCorpusSnapshot
        ),
        inherited_adjudication_corpus: CheckpointConflictWitnessAdjudicationCorpusSnapshot,
        checkpoint_policy: CheckpointPolicy,
        checkpoint_log: CheckpointLog,
        checkpoints: tuple[CheckpointSnapshot, ...],
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        predecessor_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        current_issuer_registry: CredentialIssuerRegistrySnapshot,
        current_credential_policy: CredentialPolicySnapshot,
        current_credentials: tuple[CredentialAttestationSnapshot, ...],
        inherited_witness_registry: CheckpointWitnessRegistrySnapshot,
        inherited_witness_policy: CheckpointWitnessPolicySnapshot,
        inherited_witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        inherited_head_checkpoint: CheckpointSnapshot,
        inherited_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        inherited_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        inherited_adjudication: WitnessConflictAdjudicationSnapshot,
        inherited_issuer_registry: CredentialIssuerRegistrySnapshot,
        inherited_credential_policy: AdjudicatorCredentialPolicySnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[AdjudicatorCredentialRevocationEventSnapshot, ...],
        inherited_witness_receipt: VerifiedCheckpointConflictRevocationWitnessReceipt,
        checkpoint_executor: CheckpointExecutor | None,
        experiment_run_id: str,
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
        completed_at: str,
    ) -> VerifiedCredentialedCheckpointWitnessConflictReceipt:
        """Return credential abstention or the exact delegated PR #36 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                adjudication_corpus=adjudication_corpus,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                current_issuer_registry=current_issuer_registry,
                current_credential_policy=current_credential_policy,
                current_credentials=current_credentials,
                conflict_adjudication=conflict_adjudication,
                experiment_run_id=experiment_run_id,
                current_credential_evaluated_at=current_credential_evaluated_at,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                prior_completed_at=prior_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CredentialedCheckpointWitnessConflictExperimentError(
                CredentialedCheckpointWitnessConflictRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            predecessor = self._store.get(
                corpus.predecessor_corpus_ref.artifact_id,
                expected_hash=corpus.predecessor_corpus_ref.artifact_hash,
            )
            if predecessor.payload != adjudication_corpus.artifact().payload:
                raise ArtifactIntegrityError("stored exact 1.14.0 predecessor differs")
            evidence = load_checkpoint_witness_conflict_credential_evidence(
                self._store,
                corpus=corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=current_issuer_registry,
                credential_policy=current_credential_policy,
                adjudication=conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            CredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedCheckpointWitnessConflictExperimentError(
                CredentialedCheckpointWitnessConflictRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            credential_decision = validate_checkpoint_witness_conflict_credentials(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=current_issuer_registry,
                credential_policy=current_credential_policy,
                attestations=evidence.attestations,
                adjudication=conflict_adjudication,
                evaluated_at=current_credential_evaluated_at,
            )
        except (CredentialError, ValueError) as exc:
            raise CredentialedCheckpointWitnessConflictExperimentError(
                CredentialedCheckpointWitnessConflictRunnerStage.CREDENTIAL_VALIDATION,
                str(exc),
            ) from exc

        try:
            credential_decision_ref = self._persist_credential_decision(
                experiment_run_id=experiment_run_id,
                decision=credential_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedCheckpointWitnessConflictExperimentError(
                CredentialedCheckpointWitnessConflictRunnerStage.CREDENTIAL_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedAdjudicatedCheckpointWitnessConflictReceipt | None = None
        if credential_decision.outcome is CredentialDecisionOutcome.EXECUTE:
            predecessor_plan = replace(
                plan,
                corpus_ref=adjudication_corpus.reference(),
                content_ids=adjudication_corpus.content_ids,
            )
            try:
                delegated = self._runner.run(
                    plan=predecessor_plan,
                    corpus=adjudication_corpus,
                    witness_predecessor=witness_predecessor,
                    checkpoint_corpus=checkpoint_corpus,
                    revocation_corpus=revocation_corpus,
                    credential_corpus=inherited_credential_corpus,
                    adjudication_corpus=inherited_adjudication_corpus,
                    checkpoint_policy=checkpoint_policy,
                    checkpoint_log=checkpoint_log,
                    checkpoints=checkpoints,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    conflict_witness_attestations=conflict_witness_attestations,
                    predecessor_witness_attestations=(
                        predecessor_witness_attestations
                    ),
                    conflict_adjudicator_registry=conflict_adjudicator_registry,
                    conflict_adjudication_policy=conflict_adjudication_policy,
                    conflict_adjudication=conflict_adjudication,
                    inherited_witness_registry=inherited_witness_registry,
                    inherited_witness_policy=inherited_witness_policy,
                    inherited_witness_attestations=inherited_witness_attestations,
                    inherited_head_checkpoint=inherited_head_checkpoint,
                    inherited_adjudicator_registry=inherited_adjudicator_registry,
                    inherited_adjudication_policy=inherited_adjudication_policy,
                    inherited_adjudication=inherited_adjudication,
                    issuer_registry=inherited_issuer_registry,
                    credential_policy=inherited_credential_policy,
                    revocation_policy=revocation_policy,
                    revocation_ledger=revocation_ledger,
                    revocation_events=revocation_events,
                    inherited_witness_receipt=inherited_witness_receipt,
                    checkpoint_executor=checkpoint_executor,
                    experiment_run_id=experiment_run_id,
                    conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                    conflict_adjudication_evaluated_at=(
                        conflict_adjudication_evaluated_at
                    ),
                    checkpoint_verified_at=checkpoint_verified_at,
                    predecessor_witness_evaluated_at=(
                        predecessor_witness_evaluated_at
                    ),
                    inherited_witness_evaluated_at=inherited_witness_evaluated_at,
                    revocation_evaluated_at=revocation_evaluated_at,
                    credential_evaluated_at=inherited_credential_evaluated_at,
                    inherited_adjudication_evaluated_at=(
                        inherited_adjudication_evaluated_at
                    ),
                    inherited_adjudication_completed_at=(
                        inherited_adjudication_completed_at
                    ),
                    credential_completed_at=inherited_credential_completed_at,
                    revocation_completed_at=revocation_completed_at,
                    checkpoint_completed_at=checkpoint_completed_at,
                    prior_completed_at=prior_completed_at,
                    completed_at=prior_completed_at,
                )
            except AdjudicatedCheckpointWitnessConflictExperimentError as exc:
                raise CredentialedCheckpointWitnessConflictExperimentError(
                    CredentialedCheckpointWitnessConflictRunnerStage.ADJUDICATION_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated is None:
            checkpoint_witness_outcome = None
            resolution_status = None
            conflict_adjudication_outcome = None
            predecessor_witness_outcome = None
            revocation_outcome = None
            inherited_credential_outcome = None
            inherited_checkpoint_witness_outcome = None
            inherited_resolution_status = None
            inherited_adjudication_outcome = None
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            adjudication_final_ref = None
            suffix = "abstention"
        else:
            checkpoint_witness_outcome = delegated.checkpoint_witness_outcome
            resolution_status = delegated.resolution_status
            conflict_adjudication_outcome = delegated.conflict_adjudication_outcome
            predecessor_witness_outcome = delegated.predecessor_witness_outcome
            revocation_outcome = delegated.revocation_outcome
            inherited_credential_outcome = delegated.credential_outcome
            inherited_checkpoint_witness_outcome = (
                delegated.inherited_checkpoint_witness_outcome
            )
            inherited_resolution_status = delegated.inherited_resolution_status
            inherited_adjudication_outcome = delegated.inherited_adjudication_outcome
            terminal_outcome = delegated.terminal_outcome
            adjudication_final_ref = delegated.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        final_id = (
            f"{experiment_run_id}:checkpoint-conflict-revocation-"
            "witness-conflict-adjudicator-credential-revocation-checkpoint-"
            f"witness-conflict-adjudicator-credential-{suffix}"
        )
        final = CredentialedCheckpointWitnessConflictFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=CredentialedCheckpointWitnessConflictRunnerStatus.VERIFIED,
            credential_outcome=credential_decision.outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
            revocation_outcome=revocation_outcome,
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
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=credential_decision_ref,
            adjudication_final_ref=adjudication_final_ref,
            verified_checks=CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
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
            raise CredentialedCheckpointWitnessConflictExperimentError(
                CredentialedCheckpointWitnessConflictRunnerStage.FINAL_PERSISTENCE,
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
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                current_issuer_registry=current_issuer_registry,
                current_credential_policy=current_credential_policy,
                conflict_adjudication=conflict_adjudication,
                credential_decision=credential_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedCheckpointWitnessConflictExperimentError(
                CredentialedCheckpointWitnessConflictRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCredentialedCheckpointWitnessConflictReceipt(
            experiment_run_id=experiment_run_id,
            status=CredentialedCheckpointWitnessConflictRunnerStatus.VERIFIED,
            credential_outcome=credential_decision.outcome,
            checkpoint_witness_outcome=checkpoint_witness_outcome,
            resolution_status=resolution_status,
            conflict_adjudication_outcome=conflict_adjudication_outcome,
            predecessor_witness_outcome=predecessor_witness_outcome,
            revocation_outcome=revocation_outcome,
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
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=credential_decision_ref,
            adjudication_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS,
            completed_at=completed_at,
        )


__all__ = [
    "CREDENTIALED_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
    "CredentialedCheckpointWitnessConflictExperimentError",
    "CredentialedCheckpointWitnessConflictExperimentRunner",
    "CredentialedCheckpointWitnessConflictFinalManifest",
    "CredentialedCheckpointWitnessConflictRunnerStage",
    "CredentialedCheckpointWitnessConflictRunnerStatus",
    "VerifiedCredentialedCheckpointWitnessConflictReceipt",
]
