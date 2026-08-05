"""Adjudicate the exact `1.29.0` witness conflict before PR #50."""

from __future__ import annotations

from dataclasses import make_dataclass, replace
from datetime import datetime
from enum import StrEnum
from importlib import import_module
from operator import attrgetter
from typing import Any

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.checkpoint_witness_attestation import (
    CheckpointWitnessAttestationSnapshot,
    CheckpointWitnessDecisionOutcome,
    CheckpointWitnessPolicySnapshot,
    CheckpointWitnessRegistrySnapshot,
)
from ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_conflict_adjudication import (
    ConflictAdjudicationDecisionReport,
    ConflictAdjudicationError,
    StoredConflictAdjudicationEvidence,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationOutcome,
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictResolutionStatus,
)

_contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_"
    "witness_conflict_adjudication"
)
_witness_contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_witness"
)
_witness_runner = import_module(
    "ctrt.witness_gated_current_revocation_checkpoint_witness_conflict_runner"
)

AdjudicationCorpus = vars(_contract)[
    "AdjudicationBoundCurrentRevocationConflictAdjudicator"
    "CheckpointWitnessCorpusSnapshot"
]
load_adjudication_evidence = vars(_contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_"
    "adjudication_evidence"
]
validate_adjudication = vars(_contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_adjudication"
]
AdjudicatorCheckpointWitnessError = vars(_witness_contract)[
    "AdjudicatorCheckpointWitnessError"
]
validate_witnesses = vars(_witness_contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witnesses"
]
WitnessRunner = vars(_witness_runner)[
    "WitnessGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner"
]
WitnessExperimentError = vars(_witness_runner)["WitnessExperimentError"]
DELEGATED_OUTCOME_FIELDS = tuple(vars(_witness_runner)["OUTCOME_FIELDS"])

_ARTIFACT_PREFIX = (
    "current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-witness-conflict-adjudication"
)
_CONFLICTING_FIELD = (
    "conflicting_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_outcome"
)
_RESOLUTION_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_resolution_status"
)
_ADJUDICATION_OUTCOME_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_"
    "conflict_adjudication_outcome"
)
_RESOLVED_FIELD = (
    "resolved_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_outcome"
)
_DELEGATED_WITNESS_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_outcome"
)
_get_conflicting = attrgetter(_CONFLICTING_FIELD)
_get_adjudication_outcome = attrgetter(_ADJUDICATION_OUTCOME_FIELD)
_get_resolved = attrgetter(_RESOLVED_FIELD)
_get_delegated_witness = attrgetter(_DELEGATED_WITNESS_FIELD)

VERIFIED_CHECKS = (
    "exact-1.28.0-current-revocation-conflict-adjudicator-witness-"
    "predecessor-preserved",
    "exact-conflicting-current-revocation-conflict-adjudicator-witness-"
    "population-bound",
    "original-current-revocation-conflict-adjudicator-witness-abstention-"
    "preserved",
    "exact-current-revocation-conflict-adjudicator-conflict-adjudicator-"
    "registry-bound",
    "exact-current-revocation-conflict-adjudicator-conflict-adjudication-"
    "policy-bound",
    "current-revocation-conflict-adjudicator-fork-evidence-reverified",
    "current-revocation-conflict-adjudicator-dissent-preserved",
    "resolved-head-restricted-to-exact-1.27.0-checkpoint-head",
    "adjudication-and-all-pr50-outcomes-finalized-separately",
)


class AdjudicationRunnerStage(StrEnum):
    """Boundary at which current witness-conflict adjudication failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    ADJUDICATION_VALIDATION = "adjudication-validation"
    ADJUDICATION_DECISION_PERSISTENCE = "adjudication-decision-persistence"
    WITNESS_EXECUTION = "witness-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class AdjudicationRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class AdjudicationExperimentError(RuntimeError):
    """Fail closed while preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: AdjudicationRunnerStage,
        message: str,
        *,
        completed_content_ids: tuple[str, ...] = (),
    ) -> None:
        self.stage = stage
        self.completed_content_ids = completed_content_ids
        super().__init__(f"{stage.value} failed: {message}")


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


def _delegated_outcomes(value: Any) -> tuple[Any, ...]:
    return tuple(getattr(value, name) for name in DELEGATED_OUTCOME_FIELDS)


def _expected_final_id(value: Any) -> str:
    prefix = f"{value.experiment_run_id}:{_ARTIFACT_PREFIX}-"
    if _get_adjudication_outcome(value) is WitnessConflictAdjudicationOutcome.ABSTAIN:
        return prefix + "abstention"
    suffix = (
        "completion"
        if value.terminal_outcome is ReviewDecisionOutcome.EXECUTE
        else "terminal-abstention"
    )
    return prefix + suffix


def _validate_common(value: Any) -> None:
    if value.status is not AdjudicationRunnerStatus.VERIFIED:
        raise ValueError("adjudicated current witness conflict must be verified")
    if _get_conflicting(value) is not CheckpointWitnessDecisionOutcome.ABSTAIN:
        raise ValueError("preserved conflicting witness outcome must be abstain")
    if not value.witness_attestation_refs:
        raise ValueError("adjudicated current conflict requires attestations")
    if len(value.witness_attestation_refs) != len(
        set(value.witness_attestation_refs)
    ):
        raise ValueError("adjudicated current conflict refs must be unique")
    if value.verified_checks != VERIFIED_CHECKS:
        raise ValueError("adjudicated current conflict lost verified checks")
    _parse_timestamp(value.completed_at, "completed_at")


def _final_post_init(self: Any) -> None:
    _validate_common(self)
    resolved = _get_resolved(self)
    downstream = (resolved, *_delegated_outcomes(self))
    if _get_adjudication_outcome(self) is WitnessConflictAdjudicationOutcome.ABSTAIN:
        if any(item is not None for item in downstream):
            raise ValueError("adjudication abstention may not claim PR #50 outcomes")
        if self.predecessor_witness_final_ref is not None:
            raise ValueError("adjudication abstention may not contain PR #50 final")
        if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
            raise ValueError("adjudication abstention must be terminal")
    else:
        if self.predecessor_witness_final_ref is None:
            raise ValueError("adjudication execution requires PR #50 final")
        if resolved is None:
            raise ValueError("adjudication execution requires witness outcome")
    if self.final_id != _expected_final_id(self):
        raise ValueError("final_id must derive from adjudication outcome")


def _receipt_post_init(self: Any) -> None:
    _validate_common(self)
    resolved = _get_resolved(self)
    downstream = (resolved, *_delegated_outcomes(self))
    if _get_adjudication_outcome(self) is WitnessConflictAdjudicationOutcome.ABSTAIN:
        if self.predecessor_witness_receipt is not None:
            raise ValueError("adjudication abstention may not contain PR #50 receipt")
        if any(item is not None for item in downstream):
            raise ValueError("adjudication abstention may not contain outcomes")
    else:
        delegated = self.predecessor_witness_receipt
        if delegated is None:
            raise ValueError("adjudication execution requires PR #50 receipt")
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #50 receipt belongs to another run")
        if _get_delegated_witness(delegated) is not resolved:
            raise ValueError("resolved witness outcome differs from PR #50")
        if _delegated_outcomes(delegated) != _delegated_outcomes(self):
            raise ValueError("PR #50 outcomes differ from adjudicated receipt")
        if delegated.terminal_outcome is not self.terminal_outcome:
            raise ValueError("PR #50 terminal outcome differs")
    if self.final_manifest_ref.artifact_id != _expected_final_id(self):
        raise ValueError("final manifest identifies wrong adjudication outcome")


_COMMON_FIELDS: list[tuple[str, Any]] = [
    ("experiment_run_id", str),
    ("status", AdjudicationRunnerStatus),
    (_CONFLICTING_FIELD, CheckpointWitnessDecisionOutcome),
    (_RESOLUTION_FIELD, WitnessConflictResolutionStatus),
    (_ADJUDICATION_OUTCOME_FIELD, WitnessConflictAdjudicationOutcome),
    (_RESOLVED_FIELD, CheckpointWitnessDecisionOutcome | None),
    *[(name, Any) for name in DELEGATED_OUTCOME_FIELDS],
    ("terminal_outcome", ReviewDecisionOutcome),
    ("experiment_id", str),
    ("experiment_version", str),
    ("content_ids", tuple[str, ...]),
    ("adjudication_corpus_ref", StoredArtifactRef),
    ("witness_registry_ref", StoredArtifactRef),
    ("witness_policy_ref", StoredArtifactRef),
    ("witness_attestation_refs", tuple[StoredArtifactRef, ...]),
    ("conflict_adjudicator_registry_ref", StoredArtifactRef),
    ("conflict_adjudication_policy_ref", StoredArtifactRef),
    ("conflict_adjudication_ref", StoredArtifactRef),
    ("witness_decision_ref", StoredArtifactRef),
    ("adjudication_decision_ref", StoredArtifactRef),
]

AdjudicationFinalManifest = make_dataclass(
    "AdjudicationFinalManifest",
    [
        ("final_id", str),
        *_COMMON_FIELDS,
        ("predecessor_witness_final_ref", StoredArtifactRef | None),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _final_post_init},
    frozen=True,
    slots=True,
)

VerifiedAdjudicationReceipt = make_dataclass(
    "VerifiedAdjudicationReceipt",
    [
        *_COMMON_FIELDS,
        ("predecessor_witness_receipt", Any),
        ("final_manifest_ref", StoredArtifactRef),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _receipt_post_init},
    frozen=True,
    slots=True,
)


class AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitnessExperimentRunner:
    """Resolve the exact `1.29.0` conflict before executing PR #50."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = WitnessRunner(artifact_store=artifact_store)

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        witness_predecessor: Any,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_reverified_at: str,
        canonical_witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        witness_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("adjudicated current conflict requires frozen plan")
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan must match adjudication corpus exactly")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order differs from adjudication corpus")
        if corpus.predecessor_corpus_ref != witness_predecessor.reference():
            raise ValueError("adjudication corpus must bind exact 1.28.0 predecessor")
        if corpus.corpus.witness_registry_ref != witness_registry.reference():
            raise ValueError("witness registry differs from adjudication corpus")
        if corpus.corpus.witness_policy_ref != witness_policy.reference():
            raise ValueError("witness policy differs from adjudication corpus")
        expected_attestations = tuple(
            item.reference() for item in conflict_witness_attestations
        )
        if corpus.corpus.witness_attestation_refs != expected_attestations:
            raise ValueError("conflicting witness population differs from corpus")
        if (
            corpus.adjudicator_registry_ref
            != conflict_adjudicator_registry.reference()
        ):
            raise ValueError("conflict adjudicator registry differs from corpus")
        if (
            corpus.adjudication_policy_ref
            != conflict_adjudication_policy.reference()
        ):
            raise ValueError("conflict adjudication policy differs from corpus")
        if corpus.adjudication_ref != conflict_adjudication.reference():
            raise ValueError("conflict adjudication record differs from corpus")
        times = (
            _parse_timestamp(corpus.corpus.created_at, "corpus.created_at"),
            _parse_timestamp(
                conflict_witness_evaluated_at,
                "conflict_witness_evaluated_at",
            ),
            _parse_timestamp(
                conflict_adjudication_evaluated_at,
                "conflict_adjudication_evaluated_at",
            ),
            _parse_timestamp(
                checkpoint_reverified_at,
                "checkpoint_reverified_at",
            ),
            _parse_timestamp(
                canonical_witness_evaluated_at,
                "canonical_witness_evaluated_at",
            ),
            _parse_timestamp(
                delegated_checkpoint_verified_at,
                "delegated_checkpoint_verified_at",
            ),
            _parse_timestamp(revocation_evaluated_at, "revocation_evaluated_at"),
            _parse_timestamp(revocation_completed_at, "revocation_completed_at"),
            _parse_timestamp(checkpoint_completed_at, "checkpoint_completed_at"),
            _parse_timestamp(witness_completed_at, "witness_completed_at"),
            _parse_timestamp(completed_at, "completed_at"),
        )
        if tuple(sorted(times)) != times:
            raise ValueError(
                "successor, adjudication, and PR #50 chronology differs"
            )

    def _persist(
        self,
        *,
        artifact_id: str,
        value: object,
        message: str,
    ) -> StoredArtifactRef:
        artifact = serialize_artifact(artifact_id, value)
        reference = self._store.append(artifact)
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError(message)
        return reference

    def _verify_final(
        self,
        *,
        final: Any,
        final_ref: StoredArtifactRef,
        corpus: Any,
        witness_predecessor: Any,
        evidence: StoredConflictAdjudicationEvidence,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        witness_decision: Any,
        adjudication_decision: ConflictAdjudicationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored_final = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored_final.payload != expected.payload:
            raise ArtifactIntegrityError("stored adjudication final differs")
        stored_corpus = self._store.get(
            final.adjudication_corpus_ref.artifact_id,
            expected_hash=final.adjudication_corpus_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.29.0 adjudication corpus differs")
        predecessor = self._store.get(
            witness_predecessor.reference().artifact_id,
            expected_hash=witness_predecessor.reference().artifact_hash,
        )
        if predecessor.payload != witness_predecessor.artifact().payload:
            raise ArtifactIntegrityError("stored 1.28.0 witness predecessor differs")
        stored_registry = self._store.get(
            final.witness_registry_ref.artifact_id,
            expected_hash=final.witness_registry_ref.artifact_hash,
        )
        if stored_registry.payload != witness_registry.canonical_payload:
            raise ArtifactIntegrityError("stored witness registry differs")
        stored_policy = self._store.get(
            final.witness_policy_ref.artifact_id,
            expected_hash=final.witness_policy_ref.artifact_hash,
        )
        if stored_policy.payload != witness_policy.canonical_payload:
            raise ArtifactIntegrityError("stored witness policy differs")
        for reference in evidence.witness_evidence.attestation_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        stored_adjudicator_registry = self._store.get(
            final.conflict_adjudicator_registry_ref.artifact_id,
            expected_hash=final.conflict_adjudicator_registry_ref.artifact_hash,
        )
        if (
            stored_adjudicator_registry.payload
            != conflict_adjudicator_registry.canonical_payload
        ):
            raise ArtifactIntegrityError("stored adjudicator registry differs")
        stored_adjudication_policy = self._store.get(
            final.conflict_adjudication_policy_ref.artifact_id,
            expected_hash=final.conflict_adjudication_policy_ref.artifact_hash,
        )
        if (
            stored_adjudication_policy.payload
            != conflict_adjudication_policy.canonical_payload
        ):
            raise ArtifactIntegrityError("stored adjudication policy differs")
        stored_adjudication = self._store.get(
            final.conflict_adjudication_ref.artifact_id,
            expected_hash=final.conflict_adjudication_ref.artifact_hash,
        )
        if stored_adjudication.payload != conflict_adjudication.canonical_payload:
            raise ArtifactIntegrityError("stored adjudication record differs")
        expected_witness = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-witness-decision",
            witness_decision,
        )
        stored_witness = self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        )
        if stored_witness.payload != expected_witness.payload:
            raise ArtifactIntegrityError("stored conflicting witness decision differs")
        expected_adjudication = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            adjudication_decision,
        )
        stored_decision = self._store.get(
            final.adjudication_decision_ref.artifact_id,
            expected_hash=final.adjudication_decision_ref.artifact_hash,
        )
        if stored_decision.payload != expected_adjudication.payload:
            raise ArtifactIntegrityError("stored adjudication decision differs")
        if final.predecessor_witness_final_ref is not None:
            self._store.get(
                final.predecessor_witness_final_ref.artifact_id,
                expected_hash=final.predecessor_witness_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: Any,
        witness_predecessor: Any,
        checkpoint_predecessor: Any,
        current_revocation_corpus: Any,
        current_checkpoint_policy: Any,
        current_checkpoint_log: Any,
        current_checkpoints: tuple[Any, ...],
        current_revocation_ledger: Any,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        conflict_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        canonical_witness_attestations: tuple[
            CheckpointWitnessAttestationSnapshot, ...
        ],
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_reverified_at: str,
        canonical_witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        witness_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> Any:
        """Return adjudication abstention or exact delegated PR #50 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                witness_predecessor=witness_predecessor,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                conflict_witness_attestations=conflict_witness_attestations,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                conflict_adjudication_policy=conflict_adjudication_policy,
                conflict_adjudication=conflict_adjudication,
                experiment_run_id=experiment_run_id,
                conflict_witness_evaluated_at=conflict_witness_evaluated_at,
                conflict_adjudication_evaluated_at=(
                    conflict_adjudication_evaluated_at
                ),
                checkpoint_reverified_at=checkpoint_reverified_at,
                canonical_witness_evaluated_at=canonical_witness_evaluated_at,
                delegated_checkpoint_verified_at=(
                    delegated_checkpoint_verified_at
                ),
                revocation_evaluated_at=current_revocation_evaluated_at,
                revocation_completed_at=revocation_completed_at,
                checkpoint_completed_at=checkpoint_completed_at,
                witness_completed_at=witness_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_adjudication_evidence(
                self._store,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=conflict_adjudicator_registry,
                adjudication_policy=conflict_adjudication_policy,
                adjudication=conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            ConflictAdjudicationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_witnesses(
                plan=plan,
                corpus=corpus.corpus,
                registry=witness_registry,
                policy=witness_policy,
                head_checkpoint=current_checkpoints[-1],
                attestations=conflict_witness_attestations,
                evaluated_at=conflict_witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.WITNESS_VALIDATION,
                str(exc),
            ) from exc

        try:
            witness_ref = self._persist(
                artifact_id=(
                    f"{experiment_run_id}:{_ARTIFACT_PREFIX}-witness-decision"
                ),
                value=witness_decision,
                message="stored conflicting witness decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            adjudication_decision = validate_adjudication(
                plan=plan,
                corpus=corpus,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                adjudicator_registry=conflict_adjudicator_registry,
                adjudication_policy=conflict_adjudication_policy,
                witness_decision=witness_decision,
                adjudication=conflict_adjudication,
                evaluated_at=conflict_adjudication_evaluated_at,
            )
        except (ConflictAdjudicationError, ValueError) as exc:
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.ADJUDICATION_VALIDATION,
                str(exc),
            ) from exc

        try:
            adjudication_ref = self._persist(
                artifact_id=f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
                value=adjudication_decision,
                message="stored conflict adjudication decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.ADJUDICATION_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        predecessor_receipt: Any = None
        if (
            adjudication_decision.outcome
            is WitnessConflictAdjudicationOutcome.EXECUTE
        ):
            witness_plan = replace(
                plan,
                corpus_ref=witness_predecessor.reference(),
                content_ids=witness_predecessor.content_ids,
            )
            try:
                predecessor_receipt = self._runner.run(
                    plan=witness_plan,
                    corpus=witness_predecessor,
                    checkpoint_corpus=checkpoint_predecessor,
                    current_revocation_corpus=current_revocation_corpus,
                    witness_registry=witness_registry,
                    witness_policy=witness_policy,
                    witness_attestations=canonical_witness_attestations,
                    current_checkpoint_policy=current_checkpoint_policy,
                    current_checkpoint_log=current_checkpoint_log,
                    current_checkpoints=current_checkpoints,
                    current_revocation_ledger=current_revocation_ledger,
                    experiment_run_id=experiment_run_id,
                    checkpoint_reverified_at=checkpoint_reverified_at,
                    witness_evaluated_at=canonical_witness_evaluated_at,
                    delegated_checkpoint_verified_at=(
                        delegated_checkpoint_verified_at
                    ),
                    current_revocation_evaluated_at=(
                        current_revocation_evaluated_at
                    ),
                    revocation_completed_at=revocation_completed_at,
                    checkpoint_completed_at=checkpoint_completed_at,
                    completed_at=witness_completed_at,
                    **delegated,
                )
            except WitnessExperimentError as exc:
                raise AdjudicationExperimentError(
                    AdjudicationRunnerStage.WITNESS_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if predecessor_receipt is None:
            resolved_witness_outcome = None
            values: tuple[Any, ...] = (None,) * len(DELEGATED_OUTCOME_FIELDS)
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            predecessor_final_ref = None
            suffix = "abstention"
        else:
            resolved_witness_outcome = _get_delegated_witness(
                predecessor_receipt
            )
            values = _delegated_outcomes(predecessor_receipt)
            terminal_outcome = predecessor_receipt.terminal_outcome
            predecessor_final_ref = predecessor_receipt.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        common = {
            "experiment_run_id": experiment_run_id,
            "status": AdjudicationRunnerStatus.VERIFIED,
            _CONFLICTING_FIELD: witness_decision.outcome,
            _RESOLUTION_FIELD: adjudication_decision.resolution_status,
            _ADJUDICATION_OUTCOME_FIELD: adjudication_decision.outcome,
            _RESOLVED_FIELD: resolved_witness_outcome,
            **dict(zip(DELEGATED_OUTCOME_FIELDS, values, strict=True)),
            "terminal_outcome": terminal_outcome,
            "experiment_id": plan.experiment_id,
            "experiment_version": plan.experiment_version,
            "content_ids": plan.content_ids,
            "adjudication_corpus_ref": evidence.corpus_ref,
            "witness_registry_ref": evidence.witness_evidence.witness_registry_ref,
            "witness_policy_ref": evidence.witness_evidence.witness_policy_ref,
            "witness_attestation_refs": evidence.witness_evidence.attestation_refs,
            "conflict_adjudicator_registry_ref": evidence.adjudicator_registry_ref,
            "conflict_adjudication_policy_ref": evidence.adjudication_policy_ref,
            "conflict_adjudication_ref": evidence.adjudication_ref,
            "witness_decision_ref": witness_ref,
            "adjudication_decision_ref": adjudication_ref,
        }
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = AdjudicationFinalManifest(
            final_id=final_id,
            **common,
            predecessor_witness_final_ref=predecessor_final_ref,
            verified_checks=VERIFIED_CHECKS,
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
            completed_ids = (
                plan.content_ids
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                witness_predecessor=witness_predecessor,
                evidence=evidence,
                witness_registry=witness_registry,
                witness_policy=witness_policy,
                conflict_adjudicator_registry=conflict_adjudicator_registry,
                conflict_adjudication_policy=conflict_adjudication_policy,
                conflict_adjudication=conflict_adjudication,
                witness_decision=witness_decision,
                adjudication_decision=adjudication_decision,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            completed_ids = (
                plan.content_ids
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise AdjudicationExperimentError(
                AdjudicationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        return VerifiedAdjudicationReceipt(
            **common,
            predecessor_witness_receipt=predecessor_receipt,
            final_manifest_ref=final_ref,
            verified_checks=VERIFIED_CHECKS,
            completed_at=completed_at,
        )


_LONG_CHECKS = (
    "ADJUDICATED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_VERIFIED_CHECKS"
)
_LONG_ERROR = (
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentError"
)
_LONG_FINAL = (
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "FinalManifest"
)
_LONG_STAGE = (
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStage"
)
_LONG_STATUS = (
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStatus"
)
_LONG_RECEIPT = (
    "VerifiedAdjudicatedCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessReceipt"
)

globals()[_LONG_CHECKS] = VERIFIED_CHECKS
globals()[_LONG_ERROR] = AdjudicationExperimentError
globals()[_LONG_FINAL] = AdjudicationFinalManifest
globals()[_LONG_STAGE] = AdjudicationRunnerStage
globals()[_LONG_STATUS] = AdjudicationRunnerStatus
globals()[_LONG_RECEIPT] = VerifiedAdjudicationReceipt

__all__ = [
    _LONG_CHECKS,
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitnessExperimentRunner",
    _LONG_ERROR,
    _LONG_FINAL,
    _LONG_STAGE,
    _LONG_STATUS,
    _LONG_RECEIPT,
]
