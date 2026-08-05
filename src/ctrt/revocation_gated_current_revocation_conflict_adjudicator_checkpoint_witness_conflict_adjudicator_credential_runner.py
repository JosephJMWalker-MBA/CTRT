"""Gate exact `1.30.0` credential execution on append-only revocation history."""

from __future__ import annotations

from dataclasses import make_dataclass, replace
from datetime import datetime
from enum import StrEnum
from importlib import import_module
from operator import attrgetter
from typing import Any

from ctrt.adjudicator_credential_revocation_ledger import (
    AdjudicatorCredentialRevocationDecisionReport,
    AdjudicatorCredentialRevocationError,
    AdjudicatorCredentialRevocationEventSnapshot,
    AdjudicatorCredentialRevocationLedgerSnapshot,
    AdjudicatorCredentialRevocationPolicySnapshot,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactStoreError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.extraction_review_adjudication import ReviewDecisionOutcome
from ctrt.reviewer_credential_attestation import (
    CredentialDecisionOutcome,
    CredentialIssuerRegistrySnapshot,
)
from ctrt.serialization import CanonicalSerializationError, serialize_artifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationPolicySnapshot,
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistrySnapshot,
)

_contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_ledger"
)
_credential_contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential"
)
_credential_runner = import_module(
    "ctrt.credentialed_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)

RevocationCorpus = vars(_contract)[
    "RevocationBoundCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialCorpusSnapshot"
]
load_revocation_evidence = vars(_contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_evidence"
]
validate_revocation_ledger = vars(_contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_revocation_ledger"
]

CredentialCorpus = vars(_credential_contract)[
    "CredentialBoundCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessCorpusSnapshot"
]
CredentialAttestationSnapshot = vars(_credential_contract)[
    "CredentialAttestationSnapshot"
]
CredentialError = vars(_credential_contract)["CredentialError"]
CredentialPolicySnapshot = vars(_credential_contract)["CredentialPolicySnapshot"]
load_credential_evidence = vars(_credential_contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "credential_evidence"
]

CredentialRunner = vars(_credential_runner)[
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentRunner"
]
CredentialExperimentError = vars(_credential_runner)[
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentError"
]
_CREDENTIAL_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_outcome"
)
PR51_OUTCOME_FIELDS = tuple(
    vars(_credential_runner)["ADJUDICATION_OUTCOME_FIELDS"]
)
PR52_OUTCOME_FIELDS = (_CREDENTIAL_FIELD, *PR51_OUTCOME_FIELDS)

_ARTIFACT_PREFIX = (
    "current-revocation-conflict-adjudicator-checkpoint-witness-"
    "conflict-adjudicator-credential-revocation"
)
_REVOCATION_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_revocation_outcome"
)
_get_revocation_outcome = attrgetter(_REVOCATION_FIELD)

VERIFIED_CHECKS = (
    "exact-1.30.0-current-conflict-adjudicator-credential-predecessor-preserved",
    "exact-current-conflict-adjudicator-credential-revocation-policy-bound",
    "exact-current-conflict-adjudicator-credential-ledger-and-events-bound",
    "issuer-authority-and-linear-supersession-reverified",
    "recording-freeze-publication-and-evaluation-chronology-reverified",
    "revocation-status-evaluated-before-pr52-credential",
    "revocation-decision-persisted-before-pr52",
    "revocation-and-all-pr52-outcomes-finalized-separately",
)


class RevocationRunnerStage(StrEnum):
    """Boundary at which current credential revocation processing failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    REVOCATION_VALIDATION = "revocation-validation"
    DECISION_PERSISTENCE = "decision-persistence"
    CREDENTIAL_EXECUTION = "credential-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class RevocationRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class RevocationExperimentError(RuntimeError):
    """Fail closed while preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: RevocationRunnerStage,
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
    return tuple(getattr(value, name) for name in PR52_OUTCOME_FIELDS)


def _expected_final_id(value: Any) -> str:
    prefix = f"{value.experiment_run_id}:{_ARTIFACT_PREFIX}-"
    if _get_revocation_outcome(value) is CredentialDecisionOutcome.ABSTAIN:
        return prefix + "abstention"
    suffix = (
        "completion"
        if value.terminal_outcome is ReviewDecisionOutcome.EXECUTE
        else "terminal-abstention"
    )
    return prefix + suffix


def _validate_common(value: Any) -> None:
    if value.status is not RevocationRunnerStatus.VERIFIED:
        raise ValueError("revocation-gated credential must be verified")
    if not value.revocation_event_refs:
        raise ValueError("revocation-gated credential requires events")
    if len(value.revocation_event_refs) != len(
        set(value.revocation_event_refs)
    ):
        raise ValueError("revocation event refs must be unique")
    if value.verified_checks != VERIFIED_CHECKS:
        raise ValueError("revocation-gated credential lost verified checks")
    _parse_timestamp(value.completed_at, "completed_at")


def _final_post_init(self: Any) -> None:
    _validate_common(self)
    downstream = _delegated_outcomes(self)
    if _get_revocation_outcome(self) is CredentialDecisionOutcome.ABSTAIN:
        if any(item is not None for item in downstream):
            raise ValueError(
                "revocation abstention may not claim PR #52 outcomes"
            )
        if self.credential_final_ref is not None:
            raise ValueError(
                "revocation abstention may not contain PR #52 final"
            )
        if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
            raise ValueError("revocation abstention must be terminal")
    else:
        if self.credential_final_ref is None:
            raise ValueError("revocation execution requires PR #52 final")
        if downstream[0] is None:
            raise ValueError("revocation execution requires PR #52 outcomes")
    if self.final_id != _expected_final_id(self):
        raise ValueError("final_id must derive from revocation outcome")


def _receipt_post_init(self: Any) -> None:
    _validate_common(self)
    downstream = _delegated_outcomes(self)
    if _get_revocation_outcome(self) is CredentialDecisionOutcome.ABSTAIN:
        if self.credential_receipt is not None:
            raise ValueError(
                "revocation abstention may not contain PR #52 receipt"
            )
        if any(item is not None for item in downstream):
            raise ValueError("revocation abstention may not contain outcomes")
    else:
        delegated = self.credential_receipt
        if delegated is None:
            raise ValueError("revocation execution requires PR #52 receipt")
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #52 receipt belongs to another run")
        if _delegated_outcomes(delegated) != downstream:
            raise ValueError("PR #52 outcomes differ from revocation receipt")
        if delegated.terminal_outcome is not self.terminal_outcome:
            raise ValueError("PR #52 terminal outcome differs")
    if self.final_manifest_ref.artifact_id != _expected_final_id(self):
        raise ValueError("final manifest identifies wrong revocation outcome")


_COMMON_FIELDS: list[tuple[str, Any]] = [
    ("experiment_run_id", str),
    ("status", RevocationRunnerStatus),
    (_REVOCATION_FIELD, CredentialDecisionOutcome),
    *[(name, Any) for name in PR52_OUTCOME_FIELDS],
    ("terminal_outcome", ReviewDecisionOutcome),
    ("experiment_id", str),
    ("experiment_version", str),
    ("content_ids", tuple[str, ...]),
    ("revocation_corpus_ref", StoredArtifactRef),
    ("predecessor_credential_corpus_ref", VersionedArtifactRef),
    ("revocation_policy_ref", StoredArtifactRef),
    ("revocation_ledger_ref", StoredArtifactRef),
    ("revocation_event_refs", tuple[StoredArtifactRef, ...]),
    ("adjudication_ref", StoredArtifactRef),
    ("revocation_decision_ref", StoredArtifactRef),
]

RevocationFinalManifest = make_dataclass(
    "RevocationFinalManifest",
    [
        ("final_id", str),
        *_COMMON_FIELDS,
        ("credential_final_ref", StoredArtifactRef | None),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _final_post_init},
    frozen=True,
    slots=True,
)

VerifiedRevocationReceipt = make_dataclass(
    "VerifiedRevocationReceipt",
    [
        *_COMMON_FIELDS,
        ("credential_receipt", Any),
        ("final_manifest_ref", StoredArtifactRef),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _receipt_post_init},
    frozen=True,
    slots=True,
)


class RevocationGatedExperimentRunner:
    """Require active as-of status before executing exact PR #52."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = CredentialRunner(artifact_store=artifact_store)

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        credential_corpus: Any,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        experiment_run_id: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_reverified_at: str,
        canonical_witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        witness_completed_at: str,
        adjudication_completed_at: str,
        credential_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError("revocation-gated credential requires frozen plan")
        if plan.corpus_ref != corpus.reference():
            raise ValueError("plan must match revocation corpus exactly")
        if plan.content_ids != corpus.content_ids:
            raise ValueError("plan content order differs from revocation corpus")
        if corpus.predecessor_corpus_ref != credential_corpus.reference():
            raise ValueError(
                "revocation corpus must bind exact 1.30.0 predecessor"
            )
        if corpus.corpus.reference() != credential_corpus.reference():
            raise ValueError(
                "revocation corpus carries different 1.30.0 predecessor"
            )
        if corpus.revocation_policy_ref != revocation_policy.reference():
            raise ValueError("revocation policy differs from corpus")
        if corpus.revocation_ledger_ref != revocation_ledger.reference():
            raise ValueError("revocation ledger differs from corpus")
        times = (
            _parse_timestamp(corpus.created_at, "corpus.created_at"),
            _parse_timestamp(
                revocation_evaluated_at,
                "revocation_evaluated_at",
            ),
            _parse_timestamp(
                credential_evaluated_at,
                "credential_evaluated_at",
            ),
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
            _parse_timestamp(
                current_revocation_evaluated_at,
                "current_revocation_evaluated_at",
            ),
            _parse_timestamp(
                revocation_completed_at,
                "revocation_completed_at",
            ),
            _parse_timestamp(
                checkpoint_completed_at,
                "checkpoint_completed_at",
            ),
            _parse_timestamp(
                witness_completed_at,
                "witness_completed_at",
            ),
            _parse_timestamp(
                adjudication_completed_at,
                "adjudication_completed_at",
            ),
            _parse_timestamp(
                credential_completed_at,
                "credential_completed_at",
            ),
            _parse_timestamp(completed_at, "completed_at"),
        )
        if tuple(sorted(times)) != times:
            raise ValueError(
                "revocation, credential, adjudication, and chronology differs"
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
        credential_corpus: Any,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_evidence: Any,
        credential_evidence: Any,
        decision: AdjudicatorCredentialRevocationDecisionReport,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored_final = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored_final.payload != expected.payload:
            raise ArtifactIntegrityError("stored revocation final differs")
        stored_corpus = self._store.get(
            final.revocation_corpus_ref.artifact_id,
            expected_hash=final.revocation_corpus_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.31.0 corpus differs")
        predecessor = self._store.get(
            credential_corpus.reference().artifact_id,
            expected_hash=credential_corpus.reference().artifact_hash,
        )
        if predecessor.payload != credential_corpus.artifact().payload:
            raise ArtifactIntegrityError("stored 1.30.0 credential differs")
        stored_policy = self._store.get(
            final.revocation_policy_ref.artifact_id,
            expected_hash=final.revocation_policy_ref.artifact_hash,
        )
        if stored_policy.payload != revocation_policy.canonical_payload:
            raise ArtifactIntegrityError("stored revocation policy differs")
        stored_ledger = self._store.get(
            final.revocation_ledger_ref.artifact_id,
            expected_hash=final.revocation_ledger_ref.artifact_hash,
        )
        if stored_ledger.payload != revocation_ledger.canonical_payload:
            raise ArtifactIntegrityError("stored revocation ledger differs")
        for reference in (
            *revocation_evidence.event_refs,
            credential_evidence.adjudicator_registry_ref,
            credential_evidence.issuer_registry_ref,
            credential_evidence.credential_policy_ref,
            credential_evidence.adjudication_ref,
            *credential_evidence.attestation_refs,
        ):
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        expected_decision = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            decision,
        )
        stored_decision = self._store.get(
            final.revocation_decision_ref.artifact_id,
            expected_hash=final.revocation_decision_ref.artifact_hash,
        )
        if stored_decision.payload != expected_decision.payload:
            raise ArtifactIntegrityError("stored revocation decision differs")
        if final.credential_final_ref is not None:
            self._store.get(
                final.credential_final_ref.artifact_id,
                expected_hash=final.credential_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: Any,
        credential_corpus: Any,
        adjudication_corpus: Any,
        conflict_adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: Any,
        credentials: tuple[Any, ...],
        conflict_adjudication_policy: WitnessConflictAdjudicationPolicySnapshot,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        revocation_policy: AdjudicatorCredentialRevocationPolicySnapshot,
        revocation_ledger: AdjudicatorCredentialRevocationLedgerSnapshot,
        revocation_events: tuple[
            AdjudicatorCredentialRevocationEventSnapshot, ...
        ],
        experiment_run_id: str,
        revocation_evaluated_at: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_reverified_at: str,
        canonical_witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        current_revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        witness_completed_at: str,
        adjudication_completed_at: str,
        credential_completed_at: str,
        completed_at: str,
        **delegated_inputs: Any,
    ) -> Any:
        """Return revocation abstention or exact delegated PR #52."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                credential_corpus=credential_corpus,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                experiment_run_id=experiment_run_id,
                revocation_evaluated_at=revocation_evaluated_at,
                credential_evaluated_at=credential_evaluated_at,
                conflict_witness_evaluated_at=(
                    conflict_witness_evaluated_at
                ),
                conflict_adjudication_evaluated_at=(
                    conflict_adjudication_evaluated_at
                ),
                checkpoint_reverified_at=checkpoint_reverified_at,
                canonical_witness_evaluated_at=(
                    canonical_witness_evaluated_at
                ),
                delegated_checkpoint_verified_at=(
                    delegated_checkpoint_verified_at
                ),
                current_revocation_evaluated_at=(
                    current_revocation_evaluated_at
                ),
                revocation_completed_at=revocation_completed_at,
                checkpoint_completed_at=checkpoint_completed_at,
                witness_completed_at=witness_completed_at,
                adjudication_completed_at=adjudication_completed_at,
                credential_completed_at=credential_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise RevocationExperimentError(
                RevocationRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            revocation_evidence = load_revocation_evidence(
                self._store,
                corpus=corpus,
                policy=revocation_policy,
                ledger=revocation_ledger,
            )
            credential_evidence = load_credential_evidence(
                self._store,
                corpus=credential_corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                adjudication=conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            AdjudicatorCredentialRevocationError,
            CredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise RevocationExperimentError(
                RevocationRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            decision = validate_revocation_ledger(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                revocation_policy=revocation_policy,
                ledger=revocation_ledger,
                attestations=credential_evidence.attestations,
                adjudication=conflict_adjudication,
                events=revocation_events,
                evaluated_at=revocation_evaluated_at,
            )
        except (AdjudicatorCredentialRevocationError, ValueError) as exc:
            raise RevocationExperimentError(
                RevocationRunnerStage.REVOCATION_VALIDATION,
                str(exc),
            ) from exc

        try:
            decision_ref = self._persist(
                artifact_id=(
                    f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision"
                ),
                value=decision,
                message="stored revocation decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise RevocationExperimentError(
                RevocationRunnerStage.DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        credential_receipt: Any = None
        if decision.outcome is CredentialDecisionOutcome.EXECUTE:
            credential_plan = replace(
                plan,
                corpus_ref=credential_corpus.reference(),
                content_ids=credential_corpus.content_ids,
            )
            try:
                credential_receipt = self._runner.run(
                    plan=credential_plan,
                    corpus=credential_corpus,
                    adjudication_corpus=adjudication_corpus,
                    conflict_adjudicator_registry=(
                        conflict_adjudicator_registry
                    ),
                    credential_issuer_registry=(
                        credential_issuer_registry
                    ),
                    credential_policy=credential_policy,
                    credentials=credential_evidence.attestations,
                    conflict_adjudication_policy=(
                        conflict_adjudication_policy
                    ),
                    conflict_adjudication=conflict_adjudication,
                    experiment_run_id=experiment_run_id,
                    credential_evaluated_at=credential_evaluated_at,
                    conflict_witness_evaluated_at=(
                        conflict_witness_evaluated_at
                    ),
                    conflict_adjudication_evaluated_at=(
                        conflict_adjudication_evaluated_at
                    ),
                    checkpoint_reverified_at=checkpoint_reverified_at,
                    canonical_witness_evaluated_at=(
                        canonical_witness_evaluated_at
                    ),
                    delegated_checkpoint_verified_at=(
                        delegated_checkpoint_verified_at
                    ),
                    current_revocation_evaluated_at=(
                        current_revocation_evaluated_at
                    ),
                    revocation_completed_at=revocation_completed_at,
                    checkpoint_completed_at=checkpoint_completed_at,
                    witness_completed_at=witness_completed_at,
                    adjudication_completed_at=adjudication_completed_at,
                    completed_at=credential_completed_at,
                    **delegated_inputs,
                )
            except CredentialExperimentError as exc:
                raise RevocationExperimentError(
                    RevocationRunnerStage.CREDENTIAL_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if credential_receipt is None:
            values: tuple[Any, ...] = (None,) * len(PR52_OUTCOME_FIELDS)
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            credential_final_ref = None
            suffix = "abstention"
        else:
            values = _delegated_outcomes(credential_receipt)
            terminal_outcome = credential_receipt.terminal_outcome
            credential_final_ref = credential_receipt.final_manifest_ref
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        common = {
            "experiment_run_id": experiment_run_id,
            "status": RevocationRunnerStatus.VERIFIED,
            _REVOCATION_FIELD: decision.outcome,
            **dict(zip(PR52_OUTCOME_FIELDS, values, strict=True)),
            "terminal_outcome": terminal_outcome,
            "experiment_id": plan.experiment_id,
            "experiment_version": plan.experiment_version,
            "content_ids": plan.content_ids,
            "revocation_corpus_ref": revocation_evidence.corpus_ref,
            "predecessor_credential_corpus_ref": (
                credential_corpus.reference()
            ),
            "revocation_policy_ref": revocation_evidence.revocation_policy_ref,
            "revocation_ledger_ref": revocation_evidence.revocation_ledger_ref,
            "revocation_event_refs": revocation_evidence.event_refs,
            "adjudication_ref": credential_evidence.adjudication_ref,
            "revocation_decision_ref": decision_ref,
        }
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = RevocationFinalManifest(
            final_id=final_id,
            **common,
            credential_final_ref=credential_final_ref,
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
            raise RevocationExperimentError(
                RevocationRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                credential_corpus=credential_corpus,
                revocation_policy=revocation_policy,
                revocation_ledger=revocation_ledger,
                revocation_evidence=revocation_evidence,
                credential_evidence=credential_evidence,
                decision=decision,
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
            raise RevocationExperimentError(
                RevocationRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        return VerifiedRevocationReceipt(
            **common,
            credential_receipt=credential_receipt,
            final_manifest_ref=final_ref,
            verified_checks=VERIFIED_CHECKS,
            completed_at=completed_at,
        )


_LONG_CHECKS = (
    "REVOCATION_GATED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_CONFLICT_ADJUDICATOR_CREDENTIAL_VERIFIED_CHECKS"
)
_LONG_ERROR = (
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialExperimentError"
)
_LONG_FINAL = (
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialFinalManifest"
)
_LONG_RUNNER = (
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialExperimentRunner"
)
_LONG_STAGE = (
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialRunnerStage"
)
_LONG_STATUS = (
    "RevocationGatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ConflictAdjudicatorCredentialRunnerStatus"
)
_LONG_RECEIPT = (
    "VerifiedRevocationGatedCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessConflictAdjudicatorCredentialReceipt"
)

globals()[_LONG_CHECKS] = VERIFIED_CHECKS
globals()[_LONG_ERROR] = RevocationExperimentError
globals()[_LONG_FINAL] = RevocationFinalManifest
globals()[_LONG_RUNNER] = RevocationGatedExperimentRunner
globals()[_LONG_STAGE] = RevocationRunnerStage
globals()[_LONG_STATUS] = RevocationRunnerStatus
globals()[_LONG_RECEIPT] = VerifiedRevocationReceipt

__all__ = [
    _LONG_CHECKS,
    _LONG_ERROR,
    _LONG_FINAL,
    _LONG_RUNNER,
    _LONG_STAGE,
    _LONG_STATUS,
    _LONG_RECEIPT,
]
