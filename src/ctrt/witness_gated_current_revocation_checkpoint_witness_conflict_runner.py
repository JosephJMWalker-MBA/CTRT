"""Gate the exact `1.27.0` checkpoint on immutable named observations."""

from __future__ import annotations

from dataclasses import make_dataclass, replace
from datetime import datetime
from enum import StrEnum
from importlib import import_module
from typing import Any

from ctrt.adjudicator_checkpoint_witness_attestation import (
    AdjudicatorCheckpointWitnessDecisionReport,
    AdjudicatorCheckpointWitnessError,
    StoredAdjudicatorCheckpointWitnessEvidence,
)
from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
    AdjudicatorCredentialRevocationCheckpointPolicySnapshot,
    AdjudicatorCredentialRevocationCheckpointVerificationReport,
    AdjudicatorCredentialRevocationLedgerCheckpointSnapshot,
    StoredAdjudicatorCredentialRevocationCheckpointEvidence,
)
from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationLedgerSnapshot,
)
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
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.serialization import CanonicalSerializationError, serialize_artifact

_checkpoint_contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
)
load_checkpoint_evidence = vars(_checkpoint_contract)[
    "load_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_evidence"
]
validate_checkpoints = vars(_checkpoint_contract)[
    "validate_current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoints"
]

_witness_contract = import_module(
    "ctrt.current_revocation_checkpoint_witness_conflict_adjudicator_"
    "credential_revocation_checkpoint_witness"
)
load_witness_evidence = vars(_witness_contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_evidence"
]
validate_witnesses = vars(_witness_contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witnesses"
]

_checkpoint_runner = import_module(
    "ctrt.checkpoint_gated_current_revocation_checkpoint_"
    "witness_conflict_runner"
)
CheckpointExperimentError = vars(_checkpoint_runner)["CheckpointExperimentError"]
CheckpointRunner = vars(_checkpoint_runner)[
    "CheckpointGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner"
]

_ARTIFACT_PREFIX = (
    "current-revocation-checkpoint-witness-conflict-adjudicator-"
    "credential-revocation-checkpoint-witness"
)

OUTCOME_FIELDS = (
    "current_revocation_checkpoint_conflict_adjudicator_revocation_outcome",
    "current_revocation_checkpoint_conflict_adjudicator_credential_outcome",
    "conflicting_current_revocation_checkpoint_witness_outcome",
    "current_revocation_checkpoint_resolution_status",
    "current_revocation_checkpoint_conflict_adjudication_outcome",
    "resolved_current_revocation_checkpoint_witness_outcome",
    "current_conflict_adjudicator_revocation_outcome",
    "current_conflict_adjudicator_credential_outcome",
    "conflicting_witness_outcome",
    "current_resolution_status",
    "current_conflict_adjudication_outcome",
    "resolved_current_witness_outcome",
    "current_revocation_outcome",
    "current_credential_outcome",
    "lower_checkpoint_witness_outcome",
    "lower_resolution_status",
    "lower_conflict_adjudication_outcome",
    "lower_predecessor_witness_outcome",
    "inherited_revocation_outcome",
    "inherited_credential_outcome",
    "inherited_checkpoint_witness_outcome",
    "inherited_resolution_status",
    "inherited_adjudication_outcome",
)

VERIFIED_CHECKS = (
    "exact-1.27.0-current-revocation-conflict-adjudicator-checkpoint-preserved",
    "exact-current-revocation-conflict-adjudicator-witness-registry-bound",
    "exact-current-revocation-conflict-adjudicator-witness-policy-bound",
    "exact-current-revocation-conflict-adjudicator-witness-population-bound",
    "exact-current-revocation-conflict-adjudicator-checkpoint-head-reverified",
    "all-current-revocation-conflict-adjudicator-observations-preserved-separately",
    "current-revocation-conflict-adjudicator-witness-decision-persisted-before-pr49",
    "witness-and-all-pr49-outcomes-finalized-separately",
)


class WitnessRunnerStage(StrEnum):
    """Boundary at which current checkpoint witness execution failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    CHECKPOINT_REPORT_PERSISTENCE = "checkpoint-report-persistence"
    WITNESS_VALIDATION = "witness-validation"
    WITNESS_DECISION_PERSISTENCE = "witness-decision-persistence"
    CHECKPOINT_EXECUTION = "checkpoint-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class WitnessRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class WitnessExperimentError(RuntimeError):
    """Fail-closed error preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: WitnessRunnerStage,
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


def _outcomes(value: Any) -> tuple[Any, ...]:
    return tuple(getattr(value, name) for name in OUTCOME_FIELDS)


def _expected_final_id(value: Any) -> str:
    prefix = f"{value.experiment_run_id}:{_ARTIFACT_PREFIX}-"
    if (
        value.current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    ):
        return prefix + "abstention"
    suffix = (
        "completion"
        if value.terminal_outcome is ReviewDecisionOutcome.EXECUTE
        else "terminal-abstention"
    )
    return prefix + suffix


def _validate_common(value: Any) -> None:
    if value.status is not WitnessRunnerStatus.VERIFIED:
        raise ValueError("current checkpoint witness status must be verified")
    if not value.witness_attestation_refs:
        raise ValueError("current checkpoint witness requires attestations")
    if len(value.witness_attestation_refs) != len(
        set(value.witness_attestation_refs)
    ):
        raise ValueError("current checkpoint witness refs must be unique")
    if value.verified_checks != VERIFIED_CHECKS:
        raise ValueError("current checkpoint witness lost verified checks")
    _parse_timestamp(value.completed_at, "completed_at")


def _final_post_init(self: Any) -> None:
    _validate_common(self)
    downstream = _outcomes(self)
    if (
        self.current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    ):
        if any(item is not None for item in downstream):
            raise ValueError("witness abstention may not claim PR #49 outcomes")
        if self.checkpoint_final_ref is not None:
            raise ValueError("witness abstention may not contain PR #49 final")
        if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
            raise ValueError("witness abstention must be terminal")
    elif self.checkpoint_final_ref is None or downstream[0] is None:
        raise ValueError("witness execution requires PR #49 evidence")
    if self.final_id != _expected_final_id(self):
        raise ValueError("final_id must derive from witness outcome")


def _receipt_post_init(self: Any) -> None:
    _validate_common(self)
    downstream = _outcomes(self)
    if (
        self.current_revocation_conflict_adjudicator_checkpoint_witness_outcome
        is CheckpointWitnessDecisionOutcome.ABSTAIN
    ):
        if self.checkpoint_receipt is not None:
            raise ValueError("witness abstention may not contain PR #49 receipt")
        if any(item is not None for item in downstream):
            raise ValueError("witness abstention may not contain PR #49 outcomes")
    else:
        delegated = self.checkpoint_receipt
        if delegated is None:
            raise ValueError("witness execution requires PR #49 receipt")
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #49 receipt belongs to another run")
        if _outcomes(delegated) != downstream:
            raise ValueError("PR #49 receipt differs from witness receipt")
        if delegated.terminal_outcome is not self.terminal_outcome:
            raise ValueError("PR #49 terminal outcome differs")
    if self.final_manifest_ref.artifact_id != _expected_final_id(self):
        raise ValueError("final manifest identifies wrong witness outcome")


_COMMON_FIELDS: list[tuple[str, Any]] = [
    ("experiment_run_id", str),
    ("status", WitnessRunnerStatus),
    (
        "current_revocation_conflict_adjudicator_checkpoint_witness_outcome",
        CheckpointWitnessDecisionOutcome,
    ),
    *[(name, Any) for name in OUTCOME_FIELDS],
    ("terminal_outcome", ReviewDecisionOutcome),
    ("experiment_id", str),
    ("experiment_version", str),
    ("content_ids", tuple[str, ...]),
    ("witness_corpus_ref", StoredArtifactRef),
    ("witness_registry_ref", StoredArtifactRef),
    ("witness_policy_ref", StoredArtifactRef),
    ("witness_attestation_refs", tuple[StoredArtifactRef, ...]),
    ("checkpoint_verification_ref", StoredArtifactRef),
    ("witness_decision_ref", StoredArtifactRef),
]

WitnessFinalManifest = make_dataclass(
    "WitnessFinalManifest",
    [
        ("final_id", str),
        *_COMMON_FIELDS,
        ("checkpoint_final_ref", StoredArtifactRef | None),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _final_post_init},
    frozen=True,
    slots=True,
)

VerifiedWitnessReceipt = make_dataclass(
    "VerifiedWitnessReceipt",
    [
        *_COMMON_FIELDS,
        ("checkpoint_receipt", Any),
        ("final_manifest_ref", StoredArtifactRef),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _receipt_post_init},
    frozen=True,
    slots=True,
)


class WitnessGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner:
    """Verify named witnesses before executing the exact PR #49 lifecycle."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CheckpointRunner(artifact_store=artifact_store)

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        checkpoint_corpus: Any,
        registry: CheckpointWitnessRegistrySnapshot,
        policy: CheckpointWitnessPolicySnapshot,
        experiment_run_id: str,
        checkpoint_reverified_at: str,
        witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("witness-gated current checkpoint requires frozen plan")
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan must match witness corpus exactly")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order differs from witness corpus")
        if corpus.predecessor_corpus_ref != checkpoint_corpus.reference():
            raise ValueError("witness corpus must bind exact 1.27.0 predecessor")
        if corpus.corpus.reference() != checkpoint_corpus.reference():
            raise ValueError("witness corpus carries different 1.27.0 predecessor")
        if corpus.witness_registry_ref != registry.reference():
            raise ValueError("witness registry differs from corpus")
        if corpus.witness_policy_ref != policy.reference():
            raise ValueError("witness policy differs from corpus")
        times = (
            _parse_timestamp(corpus.created_at, "corpus.created_at"),
            _parse_timestamp(checkpoint_reverified_at, "checkpoint_reverified_at"),
            _parse_timestamp(witness_evaluated_at, "witness_evaluated_at"),
            _parse_timestamp(
                delegated_checkpoint_verified_at,
                "delegated_checkpoint_verified_at",
            ),
            _parse_timestamp(revocation_evaluated_at, "revocation_evaluated_at"),
            _parse_timestamp(revocation_completed_at, "revocation_completed_at"),
            _parse_timestamp(checkpoint_completed_at, "checkpoint_completed_at"),
            _parse_timestamp(completed_at, "completed_at"),
        )
        if tuple(sorted(times)) != times:
            raise ValueError(
                "witness, checkpoint, revocation, and completion chronology differs"
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
        checkpoint_corpus: Any,
        witness_evidence: StoredAdjudicatorCheckpointWitnessEvidence,
        checkpoint_evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        checkpoint_report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
        witness_decision: AdjudicatorCheckpointWitnessDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored_final = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored_final.payload != expected.payload:
            raise ArtifactIntegrityError("stored witness final differs")
        stored_corpus = self._store.get(
            final.witness_corpus_ref.artifact_id,
            expected_hash=final.witness_corpus_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.28.0 witness corpus differs")
        predecessor = self._store.get(
            checkpoint_corpus.reference().artifact_id,
            expected_hash=checkpoint_corpus.reference().artifact_hash,
        )
        if predecessor.payload != checkpoint_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.27.0 checkpoint corpus differs")
        for reference in (
            witness_evidence.witness_registry_ref,
            witness_evidence.witness_policy_ref,
            *witness_evidence.attestation_refs,
            checkpoint_evidence.checkpoint_policy_ref,
            checkpoint_evidence.checkpoint_log_ref,
            *checkpoint_evidence.checkpoint_refs,
        ):
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_checkpoint = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-checkpoint-verification",
            checkpoint_report,
        )
        stored_checkpoint = self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        )
        if stored_checkpoint.payload != expected_checkpoint.payload:
            raise ArtifactIntegrityError("stored witness checkpoint report differs")
        expected_decision = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            witness_decision,
        )
        stored_decision = self._store.get(
            final.witness_decision_ref.artifact_id,
            expected_hash=final.witness_decision_ref.artifact_hash,
        )
        if stored_decision.payload != expected_decision.payload:
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
        corpus: Any,
        checkpoint_corpus: Any,
        current_revocation_corpus: Any,
        witness_registry: CheckpointWitnessRegistrySnapshot,
        witness_policy: CheckpointWitnessPolicySnapshot,
        witness_attestations: tuple[CheckpointWitnessAttestationSnapshot, ...],
        current_checkpoint_policy: (
            AdjudicatorCredentialRevocationCheckpointPolicySnapshot
        ),
        current_checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        current_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        current_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        checkpoint_reverified_at: str,
        witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> Any:
        """Return witness abstention or the exact delegated PR #49 result."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                checkpoint_corpus=checkpoint_corpus,
                registry=witness_registry,
                policy=witness_policy,
                experiment_run_id=experiment_run_id,
                checkpoint_reverified_at=checkpoint_reverified_at,
                witness_evaluated_at=witness_evaluated_at,
                delegated_checkpoint_verified_at=delegated_checkpoint_verified_at,
                revocation_evaluated_at=current_revocation_evaluated_at,
                revocation_completed_at=revocation_completed_at,
                checkpoint_completed_at=checkpoint_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise WitnessExperimentError(
                WitnessRunnerStage.PREFLIGHT,
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
                registry=witness_registry,
                policy=witness_policy,
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
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise WitnessExperimentError(
                WitnessRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            checkpoint_report = validate_checkpoints(
                plan=checkpoint_plan,
                corpus=checkpoint_corpus,
                policy=current_checkpoint_policy,
                log=current_checkpoint_log,
                ledger=current_revocation_ledger,
                checkpoints=current_checkpoints,
                verified_at=checkpoint_reverified_at,
                revocation_evaluated_at=current_revocation_evaluated_at,
            )
        except (
            AdjudicatorCredentialRevocationCheckpointError,
            ValueError,
        ) as exc:
            raise WitnessExperimentError(
                WitnessRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc

        try:
            checkpoint_ref = self._persist(
                artifact_id=(
                    f"{experiment_run_id}:{_ARTIFACT_PREFIX}-checkpoint-verification"
                ),
                value=checkpoint_report,
                message="stored witness checkpoint report differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise WitnessExperimentError(
                WitnessRunnerStage.CHECKPOINT_REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        try:
            witness_decision = validate_witnesses(
                plan=plan,
                corpus=corpus,
                registry=witness_registry,
                policy=witness_policy,
                head_checkpoint=current_checkpoints[-1],
                attestations=witness_attestations,
                evaluated_at=witness_evaluated_at,
            )
        except (AdjudicatorCheckpointWitnessError, ValueError) as exc:
            raise WitnessExperimentError(
                WitnessRunnerStage.WITNESS_VALIDATION,
                str(exc),
            ) from exc

        try:
            decision_ref = self._persist(
                artifact_id=f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
                value=witness_decision,
                message="stored witness decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise WitnessExperimentError(
                WitnessRunnerStage.WITNESS_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        checkpoint_receipt: Any = None
        if witness_decision.outcome is CheckpointWitnessDecisionOutcome.EXECUTE:
            try:
                checkpoint_receipt = self._runner.run(
                    plan=checkpoint_plan,
                    corpus=checkpoint_corpus,
                    current_revocation_corpus=current_revocation_corpus,
                    current_checkpoint_policy=current_checkpoint_policy,
                    current_checkpoint_log=current_checkpoint_log,
                    current_checkpoints=current_checkpoints,
                    current_revocation_ledger=current_revocation_ledger,
                    experiment_run_id=experiment_run_id,
                    current_checkpoint_verified_at=delegated_checkpoint_verified_at,
                    current_revocation_evaluated_at=current_revocation_evaluated_at,
                    revocation_completed_at=revocation_completed_at,
                    completed_at=checkpoint_completed_at,
                    **delegated,
                )
            except CheckpointExperimentError as exc:
                raise WitnessExperimentError(
                    WitnessRunnerStage.CHECKPOINT_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if checkpoint_receipt is None:
            values: tuple[Any, ...] = (None,) * len(OUTCOME_FIELDS)
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            checkpoint_final_ref = None
            suffix = "abstention"
        else:
            values = _outcomes(checkpoint_receipt)
            terminal_outcome = checkpoint_receipt.terminal_outcome
            checkpoint_final_ref = checkpoint_receipt.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        common = {
            "experiment_run_id": experiment_run_id,
            "status": WitnessRunnerStatus.VERIFIED,
            "current_revocation_conflict_adjudicator_checkpoint_witness_outcome": (
                witness_decision.outcome
            ),
            **dict(zip(OUTCOME_FIELDS, values, strict=True)),
            "terminal_outcome": terminal_outcome,
            "experiment_id": plan.experiment_id,
            "experiment_version": plan.experiment_version,
            "content_ids": plan.content_ids,
            "witness_corpus_ref": witness_evidence.corpus_ref,
            "witness_registry_ref": witness_evidence.witness_registry_ref,
            "witness_policy_ref": witness_evidence.witness_policy_ref,
            "witness_attestation_refs": witness_evidence.attestation_refs,
            "checkpoint_verification_ref": checkpoint_ref,
            "witness_decision_ref": decision_ref,
        }
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = WitnessFinalManifest(
            final_id=final_id,
            **common,
            checkpoint_final_ref=checkpoint_final_ref,
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
            raise WitnessExperimentError(
                WitnessRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                checkpoint_corpus=checkpoint_corpus,
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
            completed_ids = (
                plan.content_ids
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise WitnessExperimentError(
                WitnessRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        return VerifiedWitnessReceipt(
            **common,
            checkpoint_receipt=checkpoint_receipt,
            final_manifest_ref=final_ref,
            verified_checks=VERIFIED_CHECKS,
            completed_at=completed_at,
        )


_LONG_CHECKS = (
    "CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_WITNESS_VERIFIED_CHECKS"
)
_LONG_ERROR = (
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessExperimentError"
)
_LONG_FINAL = "CurrentRevocationConflictAdjudicatorCheckpointWitnessFinalManifest"
_LONG_STAGE = "CurrentRevocationConflictAdjudicatorCheckpointWitnessRunnerStage"
_LONG_STATUS = "CurrentRevocationConflictAdjudicatorCheckpointWitnessRunnerStatus"
_LONG_RECEIPT = (
    "VerifiedCurrentRevocationConflictAdjudicatorCheckpointWitnessReceipt"
)

globals()[_LONG_CHECKS] = VERIFIED_CHECKS
globals()[_LONG_ERROR] = WitnessExperimentError
globals()[_LONG_FINAL] = WitnessFinalManifest
globals()[_LONG_STAGE] = WitnessRunnerStage
globals()[_LONG_STATUS] = WitnessRunnerStatus
globals()[_LONG_RECEIPT] = VerifiedWitnessReceipt

__all__ = [
    _LONG_CHECKS,
    "WitnessGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner",
    _LONG_ERROR,
    _LONG_FINAL,
    _LONG_STAGE,
    _LONG_STATUS,
    _LONG_RECEIPT,
]
