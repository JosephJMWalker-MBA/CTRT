"""Gate exact `1.24.0` conflict adjudication on issuer-bound credentials."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from ctrt.adjudicated_current_revocation_checkpoint_witness_runner import (
    AdjudicatedCurrentRevocationCheckpointWitnessExperimentError,
    AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner,
    VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import CheckpointWitnessDecisionOutcome
from ctrt.current_revocation_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot,
)
from ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_credential import (
    CredentialAttestationSnapshot,
    CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
    CredentialDecisionReport,
    CredentialError,
    CredentialPolicySnapshot,
    StoredCredentialEvidence,
    load_current_revocation_checkpoint_witness_conflict_credential_evidence,
    validate_current_revocation_checkpoint_witness_conflict_credentials,
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
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)

_ARTIFACT_PREFIX = (
    "current-revocation-checkpoint-witness-conflict-adjudicator-credential"
)


class CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage(StrEnum):
    """Boundary at which the current conflict-adjudicator credential gate failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    CREDENTIAL_DECISION_PERSISTENCE = "credential-decision-persistence"
    ADJUDICATION_EXECUTION = "adjudication-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
    RuntimeError
):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS = (
    "exact-1.24.0-adjudication-predecessor-preserved",
    "exact-current-revocation-conflict-adjudicator-registry-bound",
    "exact-current-revocation-conflict-credential-issuer-registry-bound",
    "exact-current-revocation-conflict-credential-policy-bound",
    "exact-current-revocation-conflict-adjudicator-identity-revision-bound",
    "exact-witness-conflict-adjudicator-role-bound",
    "credential-validity-window-evaluated",
    "credential-decision-persisted-before-adjudication-execution",
    "credential-and-all-pr46-outcomes-finalized-separately",
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
class CredentialedCurrentRevocationCheckpointWitnessConflictFinalManifest:
    """Final marker preserving credential and every delegated outcome separately."""

    final_id: str
    experiment_run_id: str
    status: CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus
    current_revocation_checkpoint_conflict_adjudicator_credential_outcome: (
        CredentialDecisionOutcome
    )
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_revocation_checkpoint_resolution_status: (
        WitnessConflictResolutionStatus | None
    )
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome | None
    )
    resolved_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
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
        expected_status = (
            CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("credentialed current conflict must be verified")
        if not self.credential_attestation_refs:
            raise ValueError("credentialed current conflict requires credentials")
        if len(self.credential_attestation_refs) != len(
            set(self.credential_attestation_refs)
        ):
            raise ValueError("credential attestation refs must be unique")
        downstream = (
            self.conflicting_current_revocation_checkpoint_witness_outcome,
            self.current_revocation_checkpoint_resolution_status,
            self.current_revocation_checkpoint_conflict_adjudication_outcome,
            self.resolved_current_revocation_checkpoint_witness_outcome,
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
        if (
            self.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
            is CredentialDecisionOutcome.ABSTAIN
        ):
            if any(item is not None for item in downstream):
                raise ValueError(
                    "credential abstention may not claim delegated outcomes"
                )
            if self.adjudication_final_ref is not None:
                raise ValueError("credential abstention may not contain PR #46 final")
            if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
                raise ValueError("credential abstention must be terminal")
            expected_id = prefix + "abstention"
        else:
            if self.adjudication_final_ref is None:
                raise ValueError("credential execution requires PR #46 final")
            if (
                self.conflicting_current_revocation_checkpoint_witness_outcome
                is None
            ):
                raise ValueError("credential execution requires delegated outcomes")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_id != expected_id:
            raise ValueError("final_id must derive from credential outcome")
        if (
            self.verified_checks
            != CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
        ):
            raise ValueError("credentialed current conflict lost verified checks")
        _parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt:
    """Proof of the credential gate plus optional exact PR #46 result."""

    experiment_run_id: str
    status: CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus
    current_revocation_checkpoint_conflict_adjudicator_credential_outcome: (
        CredentialDecisionOutcome
    )
    conflicting_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
    )
    current_revocation_checkpoint_resolution_status: (
        WitnessConflictResolutionStatus | None
    )
    current_revocation_checkpoint_conflict_adjudication_outcome: (
        WitnessConflictAdjudicationOutcome | None
    )
    resolved_current_revocation_checkpoint_witness_outcome: (
        CheckpointWitnessDecisionOutcome | None
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
    credential_corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    credential_attestation_refs: tuple[StoredArtifactRef, ...]
    adjudication_ref: StoredArtifactRef
    credential_decision_ref: StoredArtifactRef
    adjudication_receipt: (
        VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt | None
    )
    final_manifest_ref: StoredArtifactRef
    verified_checks: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        expected_status = (
            CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus.VERIFIED
        )
        if self.status is not expected_status:
            raise ValueError("verified credentialed current conflict required")
        downstream = (
            self.conflicting_current_revocation_checkpoint_witness_outcome,
            self.current_revocation_checkpoint_resolution_status,
            self.current_revocation_checkpoint_conflict_adjudication_outcome,
            self.resolved_current_revocation_checkpoint_witness_outcome,
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
        if (
            self.current_revocation_checkpoint_conflict_adjudicator_credential_outcome
            is CredentialDecisionOutcome.ABSTAIN
        ):
            if self.adjudication_receipt is not None:
                raise ValueError("credential abstention may not contain PR #46 receipt")
            if any(item is not None for item in downstream):
                raise ValueError(
                    "credential abstention may not contain delegated outcomes"
                )
            expected_id = prefix + "abstention"
        else:
            delegated = self.adjudication_receipt
            if delegated is None:
                raise ValueError("credential execution requires PR #46 receipt")
            if delegated.experiment_run_id != self.experiment_run_id:
                raise ValueError("PR #46 receipt belongs to another experiment run")
            delegated_values = (
                delegated.conflicting_current_revocation_checkpoint_witness_outcome,
                delegated.current_revocation_checkpoint_resolution_status,
                delegated.current_revocation_checkpoint_conflict_adjudication_outcome,
                delegated.resolved_current_revocation_checkpoint_witness_outcome,
                delegated.current_conflict_adjudicator_revocation_outcome,
                delegated.current_conflict_adjudicator_credential_outcome,
                delegated.conflicting_witness_outcome,
                delegated.current_resolution_status,
                delegated.current_conflict_adjudication_outcome,
                delegated.resolved_current_witness_outcome,
                delegated.current_revocation_outcome,
                delegated.current_credential_outcome,
                delegated.lower_checkpoint_witness_outcome,
                delegated.lower_resolution_status,
                delegated.lower_conflict_adjudication_outcome,
                delegated.lower_predecessor_witness_outcome,
                delegated.inherited_revocation_outcome,
                delegated.inherited_credential_outcome,
                delegated.inherited_checkpoint_witness_outcome,
                delegated.inherited_resolution_status,
                delegated.inherited_adjudication_outcome,
            )
            if delegated_values != downstream:
                raise ValueError("PR #46 receipt differs from credentialed receipt")
            if delegated.terminal_outcome is not self.terminal_outcome:
                raise ValueError("PR #46 terminal outcome differs")
            suffix = (
                "completion"
                if self.terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )
            expected_id = prefix + suffix
        if self.final_manifest_ref.artifact_id != expected_id:
            raise ValueError("final manifest identifies wrong credential outcome")
        if (
            self.verified_checks
            != CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
        ):
            raise ValueError("verified credentialed conflict lost checks")
        _parse_timestamp(self.completed_at, "completed_at")


class CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner:
    """Validate `1.25.0` credentials before executing exact PR #46."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner(
            artifact_store=artifact_store
        )

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: (
            AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot
        ),
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: CredentialPolicySnapshot,
        credentials: tuple[CredentialAttestationSnapshot, ...],
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("credentialed current conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
            raise ValueError("plan must match credential-bound corpus exactly")
        if corpus.predecessor_corpus_ref != adjudication_corpus.reference():
            raise ValueError("credential corpus must bind exact 1.24.0 predecessor")
        if corpus.corpus.reference() != adjudication_corpus.reference():
            raise ValueError("credential corpus carries different 1.24.0 predecessor")
        if (
            corpus.corpus.adjudicator_registry_ref
            != conflict_adjudicator_registry.reference()
        ):
            raise ValueError("conflict adjudicator registry differs from 1.24.0")
        if corpus.issuer_registry_ref != credential_issuer_registry.reference():
            raise ValueError("credential issuer registry differs from corpus")
        if corpus.credential_policy_ref != credential_policy.reference():
            raise ValueError("credential policy differs from corpus")
        expected_credentials = tuple(
            item.credential_attestation_ref for item in corpus.credential_entries
        )
        if tuple(item.reference() for item in credentials) != expected_credentials:
            raise ValueError("credential population differs from corpus order")
        if corpus.corpus.adjudication_ref != conflict_adjudication.reference():
            raise ValueError("adjudication reference differs from 1.24.0")
        successor = _parse_timestamp(corpus.created_at, "corpus.created_at")
        credential_time = _parse_timestamp(
            credential_evaluated_at,
            "credential_evaluated_at",
        )
        witness_time = _parse_timestamp(
            conflict_witness_evaluated_at,
            "conflict_witness_evaluated_at",
        )
        prior_completed = _parse_timestamp(
            prior_completed_at,
            "prior_completed_at",
        )
        completed = _parse_timestamp(completed_at, "completed_at")
        if not (
            successor
            <= credential_time
            <= witness_time
            <= prior_completed
            <= completed
        ):
            raise ValueError(
                "successor, credential, adjudication, and final chronology differs"
            )

    def _persist_credential_decision(
        self,
        *,
        experiment_run_id: str,
        decision: CredentialDecisionReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision"
        artifact = serialize_artifact(artifact_id, decision)
        reference = self._store.append(artifact)
        if self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        ).payload != artifact.payload:
            raise ArtifactIntegrityError("stored credential decision differs")
        return reference

    def _verify_final(
        self,
        *,
        final: CredentialedCurrentRevocationCheckpointWitnessConflictFinalManifest,
        final_ref: StoredArtifactRef,
        corpus: CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
        evidence: StoredCredentialEvidence,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: CredentialPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        credential_decision: CredentialDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        if self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        ).payload != expected.payload:
            raise ArtifactIntegrityError("stored credentialed final differs")
        if self._store.get(
            final.credential_corpus_ref.artifact_id,
            expected_hash=final.credential_corpus_ref.artifact_hash,
        ).payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.25.0 credential corpus differs")
        if self._store.get(
            final.adjudicator_registry_ref.artifact_id,
            expected_hash=final.adjudicator_registry_ref.artifact_hash,
        ).payload != conflict_adjudicator_registry.canonical_payload:
            raise ArtifactIntegrityError("stored adjudicator registry differs")
        if self._store.get(
            final.issuer_registry_ref.artifact_id,
            expected_hash=final.issuer_registry_ref.artifact_hash,
        ).payload != credential_issuer_registry.canonical_payload:
            raise ArtifactIntegrityError("stored credential issuer registry differs")
        if self._store.get(
            final.credential_policy_ref.artifact_id,
            expected_hash=final.credential_policy_ref.artifact_hash,
        ).payload != credential_policy.canonical_payload:
            raise ArtifactIntegrityError("stored credential policy differs")
        for reference in evidence.attestation_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        if self._store.get(
            final.adjudication_ref.artifact_id,
            expected_hash=final.adjudication_ref.artifact_hash,
        ).payload != conflict_adjudication.canonical_payload:
            raise ArtifactIntegrityError("stored conflict adjudication differs")
        expected_decision = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            credential_decision,
        )
        if self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        ).payload != expected_decision.payload:
            raise ArtifactIntegrityError("stored credential decision differs")
        if final.adjudication_final_ref is not None:
            self._store.get(
                final.adjudication_final_ref.artifact_id,
                expected_hash=final.adjudication_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: CredentialBoundCurrentRevocationCheckpointWitnessConflictCorpusSnapshot,
        adjudication_corpus: (
            AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot
        ),
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: CredentialPolicySnapshot,
        credentials: tuple[CredentialAttestationSnapshot, ...],
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        prior_completed_at: str,
        completed_at: str,
        **delegated_inputs: Any,
    ) -> VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt:
        """Return credential abstention or the exact delegated PR #46 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                adjudication_corpus=adjudication_corpus,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                credential_issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                credentials=credentials,
                conflict_adjudication=conflict_adjudication,
                experiment_run_id=experiment_run_id,
                credential_evaluated_at=credential_evaluated_at,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                prior_completed_at=prior_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            predecessor = self._store.get(
                corpus.predecessor_corpus_ref.artifact_id,
                expected_hash=corpus.predecessor_corpus_ref.artifact_hash,
            )
            if predecessor.payload != adjudication_corpus.artifact().payload:
                raise ArtifactIntegrityError("stored exact 1.24.0 predecessor differs")
            evidence = (
                load_current_revocation_checkpoint_witness_conflict_credential_evidence(
                    self._store,
                    corpus=corpus,
                    adjudicator_registry=conflict_adjudicator_registry,
                    issuer_registry=credential_issuer_registry,
                    credential_policy=credential_policy,
                    adjudication=conflict_adjudication,
                )
            )
        except (
            ArtifactStoreError,
            CredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            credential_decision = (
                validate_current_revocation_checkpoint_witness_conflict_credentials(
                    plan=plan,
                    corpus=corpus,
                    adjudicator_registry=conflict_adjudicator_registry,
                    issuer_registry=credential_issuer_registry,
                    credential_policy=credential_policy,
                    attestations=evidence.attestations,
                    adjudication=conflict_adjudication,
                    evaluated_at=credential_evaluated_at,
                )
            )
        except (CredentialError, ValueError) as exc:
            raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.CREDENTIAL_VALIDATION,
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
            raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.CREDENTIAL_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        delegated: VerifiedAdjudicatedCurrentRevocationCheckpointWitnessReceipt | None
        delegated = None
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
                    conflict_adjudicator_registry=conflict_adjudicator_registry,
                    conflict_adjudication=conflict_adjudication,
                    experiment_run_id=experiment_run_id,
                    conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                    completed_at=prior_completed_at,
                    **delegated_inputs,
                )
            except AdjudicatedCurrentRevocationCheckpointWitnessExperimentError as exc:
                raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                    CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.ADJUDICATION_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if delegated is None:
            delegated_values: tuple[Any, ...] = (None,) * 21
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            adjudication_final_ref = None
            suffix = "abstention"
        else:
            delegated_values = (
                delegated.conflicting_current_revocation_checkpoint_witness_outcome,
                delegated.current_revocation_checkpoint_resolution_status,
                delegated.current_revocation_checkpoint_conflict_adjudication_outcome,
                delegated.resolved_current_revocation_checkpoint_witness_outcome,
                delegated.current_conflict_adjudicator_revocation_outcome,
                delegated.current_conflict_adjudicator_credential_outcome,
                delegated.conflicting_witness_outcome,
                delegated.current_resolution_status,
                delegated.current_conflict_adjudication_outcome,
                delegated.resolved_current_witness_outcome,
                delegated.current_revocation_outcome,
                delegated.current_credential_outcome,
                delegated.lower_checkpoint_witness_outcome,
                delegated.lower_resolution_status,
                delegated.lower_conflict_adjudication_outcome,
                delegated.lower_predecessor_witness_outcome,
                delegated.inherited_revocation_outcome,
                delegated.inherited_credential_outcome,
                delegated.inherited_checkpoint_witness_outcome,
                delegated.inherited_resolution_status,
                delegated.inherited_adjudication_outcome,
            )
            terminal_outcome = delegated.terminal_outcome
            adjudication_final_ref = delegated.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        (
            conflicting_current_revocation_checkpoint_witness_outcome,
            current_revocation_checkpoint_resolution_status,
            current_revocation_checkpoint_conflict_adjudication_outcome,
            resolved_current_revocation_checkpoint_witness_outcome,
            current_conflict_adjudicator_revocation_outcome,
            current_conflict_adjudicator_credential_outcome,
            conflicting_witness_outcome,
            current_resolution_status,
            current_conflict_adjudication_outcome,
            resolved_current_witness_outcome,
            current_revocation_outcome,
            current_credential_outcome,
            lower_checkpoint_witness_outcome,
            lower_resolution_status,
            lower_conflict_adjudication_outcome,
            lower_predecessor_witness_outcome,
            inherited_revocation_outcome,
            inherited_credential_outcome,
            inherited_checkpoint_witness_outcome,
            inherited_resolution_status,
            inherited_adjudication_outcome,
        ) = delegated_values

        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CredentialedCurrentRevocationCheckpointWitnessConflictFinalManifest(
            final_id=final_id,
            experiment_run_id=experiment_run_id,
            status=(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus.VERIFIED
            ),
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome=(
                credential_decision.outcome
            ),
            conflicting_current_revocation_checkpoint_witness_outcome=(
                conflicting_current_revocation_checkpoint_witness_outcome
            ),
            current_revocation_checkpoint_resolution_status=(
                current_revocation_checkpoint_resolution_status
            ),
            current_revocation_checkpoint_conflict_adjudication_outcome=(
                current_revocation_checkpoint_conflict_adjudication_outcome
            ),
            resolved_current_revocation_checkpoint_witness_outcome=(
                resolved_current_revocation_checkpoint_witness_outcome
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
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=credential_decision_ref,
            adjudication_final_ref=adjudication_final_ref,
            verified_checks=(
                CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
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
            raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.FINAL_PERSISTENCE,
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
                credential_issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                conflict_adjudication=conflict_adjudication,
                credential_decision=credential_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=(
                    plan.content_ids
                    if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                    else ()
                ),
            ) from exc

        return VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt(
            experiment_run_id=experiment_run_id,
            status=(
                CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus.VERIFIED
            ),
            current_revocation_checkpoint_conflict_adjudicator_credential_outcome=(
                credential_decision.outcome
            ),
            conflicting_current_revocation_checkpoint_witness_outcome=(
                conflicting_current_revocation_checkpoint_witness_outcome
            ),
            current_revocation_checkpoint_resolution_status=(
                current_revocation_checkpoint_resolution_status
            ),
            current_revocation_checkpoint_conflict_adjudication_outcome=(
                current_revocation_checkpoint_conflict_adjudication_outcome
            ),
            resolved_current_revocation_checkpoint_witness_outcome=(
                resolved_current_revocation_checkpoint_witness_outcome
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
            credential_corpus_ref=evidence.corpus_ref,
            adjudicator_registry_ref=evidence.adjudicator_registry_ref,
            issuer_registry_ref=evidence.issuer_registry_ref,
            credential_policy_ref=evidence.credential_policy_ref,
            credential_attestation_refs=evidence.attestation_refs,
            adjudication_ref=evidence.adjudication_ref,
            credential_decision_ref=credential_decision_ref,
            adjudication_receipt=delegated,
            final_manifest_ref=final_ref,
            verified_checks=(
                CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS
            ),
            completed_at=completed_at,
        )


__all__ = [
    "CREDENTIALED_CURRENT_REVOCATION_CHECKPOINT_WITNESS_CONFLICT_VERIFIED_CHECKS",
    "CredentialedCurrentRevocationCheckpointWitnessConflictExperimentError",
    "CredentialedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
    "CredentialedCurrentRevocationCheckpointWitnessConflictFinalManifest",
    "CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStage",
    "CredentialedCurrentRevocationCheckpointWitnessConflictRunnerStatus",
    "VerifiedCredentialedCurrentRevocationCheckpointWitnessConflictReceipt",
]
