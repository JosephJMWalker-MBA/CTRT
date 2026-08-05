"""Close exact `1.31.0` execution behind one immutable checkpoint."""

from __future__ import annotations

from dataclasses import make_dataclass, replace
from datetime import datetime
from enum import StrEnum
from importlib import import_module
from typing import Any

from ctrt.adjudicator_credential_revocation_checkpoints import (
    AdjudicatorCredentialRevocationCheckpointError,
    AdjudicatorCredentialRevocationCheckpointLogSnapshot,
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
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.serialization import CanonicalSerializationError, serialize_artifact

_contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_closure_checkpoints"
)
_policy_name = (
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointPolicySnapshot"
)
_corpus_name = (
    "ClosureCheckpointBoundCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot"
)
ClosurePolicy = vars(_contract)[_policy_name]
ClosureCorpus = vars(_contract)[_corpus_name]
load_checkpoint_evidence = vars(_contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_conflict_"
    "adjudicator_credential_revocation_closure_checkpoint_evidence"
]
validate_checkpoints = vars(_contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_closure_checkpoints"
]

_revocation_runner = import_module(
    "ctrt.revocation_gated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_conflict_adjudicator_credential_runner"
)
RevocationRunner = vars(_revocation_runner)[
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialExperimentRunner"
]
RevocationExperimentError = vars(_revocation_runner)[
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialExperimentError"
]
_REVOCATION_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_revocation_outcome"
)
PR52_OUTCOME_FIELDS = tuple(vars(_revocation_runner)["PR52_OUTCOME_FIELDS"])
PR53_OUTCOME_FIELDS = (_REVOCATION_FIELD, *PR52_OUTCOME_FIELDS)

_ARTIFACT_PREFIX = (
    "current-revocation-conflict-adjudicator-checkpoint-witness-conflict-"
    "adjudicator-credential-revocation-closure-checkpoint"
)

VERIFIED_CHECKS = (
    "exact-1.31.0-current-conflict-adjudicator-credential-revocation-head-preserved",
    "exact-closure-checkpoint-policy-and-protected-predecessor-bound",
    "exact-current-conflict-adjudicator-credential-revocation-ledger-bound",
    "contiguous-closure-checkpoint-chain-and-ordered-event-prefix-verified",
    "closure-checkpoint-head-matches-exact-1.31.0-ledger",
    "closure-verification-report-persisted-before-pr53",
    "automatic-successor-governance-layers-forbidden",
    "reopen-requires-concrete-documented-unrepresented-failure",
    "closure-checkpoint-and-all-pr53-outcomes-finalized-separately",
)


class ClosureCheckpointRunnerStage(StrEnum):
    """Boundary at which closure-checkpoint execution failed."""

    PREFLIGHT = "preflight"
    CHECKPOINT_LOADING = "checkpoint-loading"
    CHECKPOINT_VALIDATION = "checkpoint-validation"
    REPORT_PERSISTENCE = "report-persistence"
    REVOCATION_EXECUTION = "revocation-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class ClosureCheckpointRunnerStatus(StrEnum):
    """A receipt exists only after full closure storage reverification."""

    VERIFIED = "verified"


class ClosureCheckpointExperimentError(RuntimeError):
    """Fail closed while preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: ClosureCheckpointRunnerStage,
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
        raise ValueError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _delegated_outcomes(value: Any) -> tuple[Any, ...]:
    return tuple(getattr(value, name) for name in PR53_OUTCOME_FIELDS)


def _expected_final_id(value: Any) -> str:
    suffix = (
        "completion"
        if value.terminal_outcome is ReviewDecisionOutcome.EXECUTE
        else "terminal-abstention"
    )
    return f"{value.experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"


def _validate_common(value: Any) -> None:
    if value.status is not ClosureCheckpointRunnerStatus.VERIFIED:
        raise ValueError("closure checkpoint must be verified")
    if value.closure_state != "closed":
        raise ValueError("closure checkpoint must close the branch")
    if value.automatic_successor_layers_allowed:
        raise ValueError("closure checkpoint forbids automatic successors")
    if not value.reopen_requires_documented_failure:
        raise ValueError("closure checkpoint requires documented failure")
    if value.permitted_reopen_trigger != "concrete-unrepresented-failure":
        raise ValueError("closure checkpoint has wrong reopen trigger")
    if not value.checkpoint_refs:
        raise ValueError("closure checkpoint requires checkpoint evidence")
    if value.checkpoint_head_ref != value.checkpoint_refs[-1]:
        raise ValueError("closure checkpoint head must be final")
    if value.verified_checks != VERIFIED_CHECKS:
        raise ValueError("closure checkpoint lost verified checks")
    _parse_timestamp(value.completed_at, "completed_at")


def _final_post_init(self: Any) -> None:
    _validate_common(self)
    if self.final_id != _expected_final_id(self):
        raise ValueError("final_id must derive from closure terminal outcome")


def _receipt_post_init(self: Any) -> None:
    _validate_common(self)
    delegated = self.revocation_receipt
    if delegated.experiment_run_id != self.experiment_run_id:
        raise ValueError("PR #53 receipt belongs to another run")
    if _delegated_outcomes(delegated) != _delegated_outcomes(self):
        raise ValueError("PR #53 outcomes differ from closure receipt")
    if delegated.terminal_outcome is not self.terminal_outcome:
        raise ValueError("PR #53 terminal outcome differs")
    if self.final_manifest_ref.artifact_id != _expected_final_id(self):
        raise ValueError("final manifest identifies wrong closure outcome")


_COMMON_FIELDS: list[tuple[str, Any]] = [
    ("experiment_run_id", str),
    ("status", ClosureCheckpointRunnerStatus),
    *[(name, Any) for name in PR53_OUTCOME_FIELDS],
    ("terminal_outcome", ReviewDecisionOutcome),
    ("experiment_id", str),
    ("experiment_version", str),
    ("content_ids", tuple[str, ...]),
    ("closure_state", str),
    ("automatic_successor_layers_allowed", bool),
    ("reopen_requires_documented_failure", bool),
    ("permitted_reopen_trigger", str),
    ("checkpoint_corpus_ref", StoredArtifactRef),
    ("predecessor_revocation_corpus_ref", VersionedArtifactRef),
    ("checkpoint_policy_ref", StoredArtifactRef),
    ("checkpoint_log_ref", StoredArtifactRef),
    ("checkpoint_refs", tuple[StoredArtifactRef, ...]),
    ("checkpoint_head_ref", StoredArtifactRef),
    ("checkpoint_verification_ref", StoredArtifactRef),
]

ClosureCheckpointFinalManifest = make_dataclass(
    "ClosureCheckpointFinalManifest",
    [
        ("final_id", str),
        *_COMMON_FIELDS,
        ("revocation_final_ref", StoredArtifactRef),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _final_post_init},
    frozen=True,
    slots=True,
)

VerifiedClosureCheckpointReceipt = make_dataclass(
    "VerifiedClosureCheckpointReceipt",
    [
        *_COMMON_FIELDS,
        ("revocation_receipt", Any),
        ("final_manifest_ref", StoredArtifactRef),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _receipt_post_init},
    frozen=True,
    slots=True,
)


class ClosureCheckpointExperimentRunner:
    """Verify the exact `1.31.0` closure head before unchanged PR #53."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = RevocationRunner(artifact_store=artifact_store)

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        revocation_corpus: Any,
        checkpoint_policy: Any,
        checkpoint_log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        experiment_run_id: str,
        checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        revocation_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("closure checkpoint requires frozen plan")
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan must match closure checkpoint corpus")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order differs from closure corpus")
        if corpus.predecessor_corpus_ref != revocation_corpus.reference():
            raise ValueError("closure corpus must bind exact 1.31.0")
        if corpus.corpus.reference() != revocation_corpus.reference():
            raise ValueError("closure corpus carries different 1.31.0")
        if checkpoint_policy.protected_predecessor_ref != (
            revocation_corpus.reference()
        ):
            raise ValueError("closure policy protects a different predecessor")
        if corpus.checkpoint_policy_ref != checkpoint_policy.reference():
            raise ValueError("closure checkpoint policy differs from corpus")
        if corpus.checkpoint_log_ref != checkpoint_log.reference():
            raise ValueError("closure checkpoint log differs from corpus")
        if corpus.checkpoint_head_ref != checkpoint_log.head_checkpoint_ref:
            raise ValueError("closure checkpoint head differs from log")
        times = (
            _parse_timestamp(corpus.created_at, "corpus.created_at"),
            _parse_timestamp(
                checkpoint_verified_at,
                "checkpoint_verified_at",
            ),
            _parse_timestamp(
                revocation_evaluated_at,
                "revocation_evaluated_at",
            ),
            _parse_timestamp(
                revocation_completed_at,
                "revocation_completed_at",
            ),
            _parse_timestamp(completed_at, "completed_at"),
        )
        if tuple(sorted(times)) != times:
            raise ValueError(
                "closure, revocation, and completion chronology differs"
            )

    def _persist_report(
        self,
        *,
        experiment_run_id: str,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> StoredArtifactRef:
        artifact_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-verification"
        artifact = serialize_artifact(artifact_id, report)
        reference = self._store.append(artifact)
        stored = self._store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError("stored closure report differs")
        return reference

    def _verify_final(
        self,
        *,
        final: Any,
        final_ref: StoredArtifactRef,
        corpus: Any,
        revocation_corpus: Any,
        policy: Any,
        log: AdjudicatorCredentialRevocationCheckpointLogSnapshot,
        evidence: StoredAdjudicatorCredentialRevocationCheckpointEvidence,
        report: AdjudicatorCredentialRevocationCheckpointVerificationReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored_final = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored_final.payload != expected.payload:
            raise ArtifactIntegrityError("stored closure final differs")
        stored_corpus = self._store.get(
            final.checkpoint_corpus_ref.artifact_id,
            expected_hash=final.checkpoint_corpus_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.32.0 closure corpus differs")
        predecessor = self._store.get(
            revocation_corpus.reference().artifact_id,
            expected_hash=revocation_corpus.reference().artifact_hash,
        )
        if predecessor.payload != revocation_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.31.0 revocation corpus differs")
        stored_policy = self._store.get(
            final.checkpoint_policy_ref.artifact_id,
            expected_hash=final.checkpoint_policy_ref.artifact_hash,
        )
        if stored_policy.payload != policy.canonical_payload:
            raise ArtifactIntegrityError("stored closure policy differs")
        stored_log = self._store.get(
            final.checkpoint_log_ref.artifact_id,
            expected_hash=final.checkpoint_log_ref.artifact_hash,
        )
        if stored_log.payload != log.canonical_payload:
            raise ArtifactIntegrityError("stored closure log differs")
        for reference in evidence.checkpoint_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_report = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-verification",
            report,
        )
        stored_report = self._store.get(
            final.checkpoint_verification_ref.artifact_id,
            expected_hash=final.checkpoint_verification_ref.artifact_hash,
        )
        if stored_report.payload != expected_report.payload:
            raise ArtifactIntegrityError("stored closure report differs")
        self._store.get(
            final.revocation_final_ref.artifact_id,
            expected_hash=final.revocation_final_ref.artifact_hash,
        )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: Any,
        current_revocation_corpus: Any,
        closure_checkpoint_policy: Any,
        closure_checkpoint_log: (
            AdjudicatorCredentialRevocationCheckpointLogSnapshot
        ),
        closure_checkpoints: tuple[
            AdjudicatorCredentialRevocationLedgerCheckpointSnapshot, ...
        ],
        current_revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        closure_checkpoint_verified_at: str,
        current_credential_revocation_evaluated_at: str,
        current_credential_revocation_completed_at: str,
        completed_at: str,
        **delegated: Any,
    ) -> Any:
        """Return the closure checkpoint plus exact delegated PR #53."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                revocation_corpus=current_revocation_corpus,
                checkpoint_policy=closure_checkpoint_policy,
                checkpoint_log=closure_checkpoint_log,
                experiment_run_id=experiment_run_id,
                checkpoint_verified_at=closure_checkpoint_verified_at,
                revocation_evaluated_at=(
                    current_credential_revocation_evaluated_at
                ),
                revocation_completed_at=(
                    current_credential_revocation_completed_at
                ),
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            evidence = load_checkpoint_evidence(
                self._store,
                corpus=corpus,
                policy=closure_checkpoint_policy,
                log=closure_checkpoint_log,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationCheckpointError,
            OSError,
            ValueError,
        ) as exc:
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.CHECKPOINT_LOADING,
                str(exc),
            ) from exc

        try:
            report = validate_checkpoints(
                plan=plan,
                corpus=corpus,
                policy=closure_checkpoint_policy,
                log=closure_checkpoint_log,
                ledger=current_revocation_ledger,
                checkpoints=closure_checkpoints,
                verified_at=closure_checkpoint_verified_at,
                revocation_evaluated_at=(
                    current_credential_revocation_evaluated_at
                ),
            )
        except (
            AdjudicatorCredentialRevocationCheckpointError,
            ValueError,
        ) as exc:
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.CHECKPOINT_VALIDATION,
                str(exc),
            ) from exc

        try:
            report_ref = self._persist_report(
                experiment_run_id=experiment_run_id,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.REPORT_PERSISTENCE,
                str(exc),
            ) from exc

        revocation_plan = replace(
            plan,
            corpus_ref=current_revocation_corpus.reference(),
            content_ids=current_revocation_corpus.content_ids,
        )
        try:
            delegated_receipt = self._runner.run(
                plan=revocation_plan,
                corpus=current_revocation_corpus,
                revocation_ledger=current_revocation_ledger,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=(
                    current_credential_revocation_evaluated_at
                ),
                completed_at=current_credential_revocation_completed_at,
                **delegated,
            )
        except RevocationExperimentError as exc:
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.REVOCATION_EXECUTION,
                str(exc),
                completed_content_ids=exc.completed_content_ids,
            ) from exc

        values = _delegated_outcomes(delegated_receipt)
        common = {
            "experiment_run_id": experiment_run_id,
            "status": ClosureCheckpointRunnerStatus.VERIFIED,
            **dict(zip(PR53_OUTCOME_FIELDS, values, strict=True)),
            "terminal_outcome": delegated_receipt.terminal_outcome,
            "experiment_id": plan.experiment_id,
            "experiment_version": plan.experiment_version,
            "content_ids": plan.content_ids,
            "closure_state": closure_checkpoint_policy.branch_state,
            "automatic_successor_layers_allowed": (
                closure_checkpoint_policy.automatic_successor_layers_allowed
            ),
            "reopen_requires_documented_failure": (
                closure_checkpoint_policy.reopen_requires_documented_failure
            ),
            "permitted_reopen_trigger": (
                closure_checkpoint_policy.permitted_reopen_trigger
            ),
            "checkpoint_corpus_ref": evidence.corpus_ref,
            "predecessor_revocation_corpus_ref": (
                corpus.predecessor_corpus_ref
            ),
            "checkpoint_policy_ref": evidence.checkpoint_policy_ref,
            "checkpoint_log_ref": evidence.checkpoint_log_ref,
            "checkpoint_refs": evidence.checkpoint_refs,
            "checkpoint_head_ref": evidence.checkpoint_refs[-1],
            "checkpoint_verification_ref": report_ref,
        }
        suffix = (
            "completion"
            if delegated_receipt.terminal_outcome
            is ReviewDecisionOutcome.EXECUTE
            else "terminal-abstention"
        )
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = ClosureCheckpointFinalManifest(
            final_id=final_id,
            **common,
            revocation_final_ref=delegated_receipt.final_manifest_ref,
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
                if delegated_receipt.terminal_outcome
                is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                revocation_corpus=current_revocation_corpus,
                policy=closure_checkpoint_policy,
                log=closure_checkpoint_log,
                evidence=evidence,
                report=report,
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            completed_ids = (
                plan.content_ids
                if delegated_receipt.terminal_outcome
                is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise ClosureCheckpointExperimentError(
                ClosureCheckpointRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        return VerifiedClosureCheckpointReceipt(
            **common,
            revocation_receipt=delegated_receipt,
            final_manifest_ref=final_ref,
            verified_checks=VERIFIED_CHECKS,
            completed_at=completed_at,
        )


_LONG_CHECKS = (
    "CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_WITNESS_CONFLICT_"
    "ADJUDICATOR_CREDENTIAL_REVOCATION_CLOSURE_CHECKPOINT_VERIFIED_CHECKS"
)
_LONG_ERROR = (
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointExperimentError"
)
_LONG_FINAL = (
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointFinalManifest"
)
_LONG_RUNNER = (
    "ClosureCheckpointGatedCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessConflictAdjudicatorCredentialRevocationExperimentRunner"
)
_LONG_STAGE = (
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointRunnerStage"
)
_LONG_STATUS = (
    "CurrentRevocationConflictAdjudicatorCheckpointWitnessConflictAdjudicator"
    "CredentialRevocationClosureCheckpointRunnerStatus"
)
_LONG_RECEIPT = (
    "VerifiedCurrentRevocationConflictAdjudicatorCheckpointWitnessConflict"
    "AdjudicatorCredentialRevocationClosureCheckpointReceipt"
)

globals()[_LONG_CHECKS] = VERIFIED_CHECKS
globals()[_LONG_ERROR] = ClosureCheckpointExperimentError
globals()[_LONG_FINAL] = ClosureCheckpointFinalManifest
globals()[_LONG_RUNNER] = ClosureCheckpointExperimentRunner
globals()[_LONG_STAGE] = ClosureCheckpointRunnerStage
globals()[_LONG_STATUS] = ClosureCheckpointRunnerStatus
globals()[_LONG_RECEIPT] = VerifiedClosureCheckpointReceipt

__all__ = [
    _LONG_CHECKS,
    _LONG_ERROR,
    _LONG_FINAL,
    _LONG_RUNNER,
    _LONG_STAGE,
    _LONG_STATUS,
    _LONG_RECEIPT,
]
