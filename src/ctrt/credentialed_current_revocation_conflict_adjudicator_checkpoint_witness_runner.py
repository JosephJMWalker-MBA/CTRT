"""Gate exact `1.29.0` adjudication on issuer-bound credentials."""

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
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus
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

_credential_contract = import_module(
    "ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential"
)
_adjudication_runner = import_module(
    "ctrt.adjudicated_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_runner"
)

CredentialCorpus = vars(_credential_contract)[
    "CredentialBoundCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessCorpusSnapshot"
]
CredentialAttestationSnapshot = vars(_credential_contract)[
    "CredentialAttestationSnapshot"
]
CredentialDecisionReport = vars(_credential_contract)[
    "CredentialDecisionReport"
]
CredentialError = vars(_credential_contract)["CredentialError"]
CredentialPolicySnapshot = vars(_credential_contract)[
    "CredentialPolicySnapshot"
]
StoredCredentialEvidence = vars(_credential_contract)[
    "StoredCredentialEvidence"
]
load_credential_evidence = vars(_credential_contract)[
    "load_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "credential_evidence"
]
validate_credentials = vars(_credential_contract)[
    "validate_current_revocation_conflict_adjudicator_checkpoint_witness_"
    "credentials"
]

AdjudicationRunner = vars(_adjudication_runner)[
    "AdjudicatedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentRunner"
]
AdjudicationExperimentError = vars(_adjudication_runner)[
    "AdjudicationExperimentError"
]
DELEGATED_OUTCOME_FIELDS = tuple(
    vars(_adjudication_runner)["DELEGATED_OUTCOME_FIELDS"]
)

_ARTIFACT_PREFIX = (
    "current-revocation-conflict-adjudicator-checkpoint-witness-"
    "conflict-adjudicator-credential"
)
_CREDENTIAL_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_witness_"
    "conflict_adjudicator_credential_outcome"
)
_CONFLICTING_FIELD = (
    "conflicting_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_outcome"
)
_RESOLUTION_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_resolution_status"
)
_ADJUDICATION_FIELD = (
    "current_revocation_conflict_adjudicator_checkpoint_"
    "conflict_adjudication_outcome"
)
_RESOLVED_FIELD = (
    "resolved_current_revocation_conflict_adjudicator_checkpoint_"
    "witness_outcome"
)
ADJUDICATION_OUTCOME_FIELDS = (
    _CONFLICTING_FIELD,
    _RESOLUTION_FIELD,
    _ADJUDICATION_FIELD,
    _RESOLVED_FIELD,
    *DELEGATED_OUTCOME_FIELDS,
)
_get_credential_outcome = attrgetter(_CREDENTIAL_FIELD)

VERIFIED_CHECKS = (
    "exact-1.29.0-current-revocation-conflict-adjudicator-"
    "adjudication-predecessor-preserved",
    "exact-current-revocation-conflict-adjudicator-registry-bound",
    "exact-current-revocation-conflict-adjudicator-credential-"
    "issuer-registry-bound",
    "exact-current-revocation-conflict-adjudicator-credential-"
    "policy-bound",
    "exact-current-revocation-conflict-adjudicator-identity-"
    "revision-bound",
    "exact-witness-conflict-adjudicator-role-bound",
    "credential-validity-window-evaluated",
    "credential-decision-persisted-before-pr51",
    "credential-and-all-pr51-outcomes-finalized-separately",
)


class CredentialRunnerStage(StrEnum):
    """Boundary at which the current adjudicator credential gate failed."""

    PREFLIGHT = "preflight"
    EVIDENCE_LOADING = "evidence-loading"
    CREDENTIAL_VALIDATION = "credential-validation"
    CREDENTIAL_DECISION_PERSISTENCE = "credential-decision-persistence"
    ADJUDICATION_EXECUTION = "adjudication-execution"
    FINAL_PERSISTENCE = "final-persistence"
    VERIFICATION = "verification"


class CredentialRunnerStatus(StrEnum):
    """A receipt exists only after complete storage reverification."""

    VERIFIED = "verified"


class CredentialExperimentError(RuntimeError):
    """Fail closed while preserving stage and completed content IDs."""

    def __init__(
        self,
        stage: CredentialRunnerStage,
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


def _adjudication_outcomes(value: Any) -> tuple[Any, ...]:
    return tuple(
        getattr(value, name) for name in ADJUDICATION_OUTCOME_FIELDS
    )


def _expected_final_id(value: Any) -> str:
    prefix = f"{value.experiment_run_id}:{_ARTIFACT_PREFIX}-"
    if _get_credential_outcome(value) is CredentialDecisionOutcome.ABSTAIN:
        return prefix + "abstention"
    suffix = (
        "completion"
        if value.terminal_outcome is ReviewDecisionOutcome.EXECUTE
        else "terminal-abstention"
    )
    return prefix + suffix


def _validate_common(value: Any) -> None:
    if value.status is not CredentialRunnerStatus.VERIFIED:
        raise ValueError("credentialed adjudication must be verified")
    if not value.credential_attestation_refs:
        raise ValueError("credentialed adjudication requires credentials")
    if len(value.credential_attestation_refs) != len(
        set(value.credential_attestation_refs)
    ):
        raise ValueError("credential attestation refs must be unique")
    if value.verified_checks != VERIFIED_CHECKS:
        raise ValueError("credentialed adjudication lost verified checks")
    _parse_timestamp(value.completed_at, "completed_at")


def _final_post_init(self: Any) -> None:
    _validate_common(self)
    downstream = _adjudication_outcomes(self)
    if _get_credential_outcome(self) is CredentialDecisionOutcome.ABSTAIN:
        if any(item is not None for item in downstream):
            raise ValueError(
                "credential abstention may not claim PR #51 outcomes"
            )
        if self.adjudication_final_ref is not None:
            raise ValueError(
                "credential abstention may not contain PR #51 final"
            )
        if self.terminal_outcome is not ReviewDecisionOutcome.ABSTAIN:
            raise ValueError("credential abstention must be terminal")
    else:
        if self.adjudication_final_ref is None:
            raise ValueError(
                "credential execution requires PR #51 final"
            )
        if downstream[0] is None:
            raise ValueError(
                "credential execution requires delegated outcomes"
            )
    if self.final_id != _expected_final_id(self):
        raise ValueError("final_id must derive from credential outcome")


def _receipt_post_init(self: Any) -> None:
    _validate_common(self)
    downstream = _adjudication_outcomes(self)
    if _get_credential_outcome(self) is CredentialDecisionOutcome.ABSTAIN:
        if self.adjudication_receipt is not None:
            raise ValueError(
                "credential abstention may not contain PR #51 receipt"
            )
        if any(item is not None for item in downstream):
            raise ValueError(
                "credential abstention may not contain outcomes"
            )
    else:
        delegated = self.adjudication_receipt
        if delegated is None:
            raise ValueError(
                "credential execution requires PR #51 receipt"
            )
        if delegated.experiment_run_id != self.experiment_run_id:
            raise ValueError("PR #51 receipt belongs to another run")
        if _adjudication_outcomes(delegated) != downstream:
            raise ValueError(
                "PR #51 outcomes differ from credentialed receipt"
            )
        if delegated.terminal_outcome is not self.terminal_outcome:
            raise ValueError("PR #51 terminal outcome differs")
    if self.final_manifest_ref.artifact_id != _expected_final_id(self):
        raise ValueError(
            "final manifest identifies wrong credential outcome"
        )


_COMMON_FIELDS: list[tuple[str, Any]] = [
    ("experiment_run_id", str),
    ("status", CredentialRunnerStatus),
    (_CREDENTIAL_FIELD, CredentialDecisionOutcome),
    *[(name, Any) for name in ADJUDICATION_OUTCOME_FIELDS],
    ("terminal_outcome", ReviewDecisionOutcome),
    ("experiment_id", str),
    ("experiment_version", str),
    ("content_ids", tuple[str, ...]),
    ("credential_corpus_ref", StoredArtifactRef),
    ("adjudicator_registry_ref", StoredArtifactRef),
    ("issuer_registry_ref", StoredArtifactRef),
    ("credential_policy_ref", StoredArtifactRef),
    ("credential_attestation_refs", tuple[StoredArtifactRef, ...]),
    ("adjudication_ref", StoredArtifactRef),
    ("credential_decision_ref", StoredArtifactRef),
]

CredentialFinalManifest = make_dataclass(
    "CredentialFinalManifest",
    [
        ("final_id", str),
        *_COMMON_FIELDS,
        ("adjudication_final_ref", StoredArtifactRef | None),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _final_post_init},
    frozen=True,
    slots=True,
)

VerifiedCredentialReceipt = make_dataclass(
    "VerifiedCredentialReceipt",
    [
        *_COMMON_FIELDS,
        ("adjudication_receipt", Any),
        ("final_manifest_ref", StoredArtifactRef),
        ("verified_checks", tuple[str, ...]),
        ("completed_at", str),
    ],
    namespace={"__post_init__": _receipt_post_init},
    frozen=True,
    slots=True,
)


class CredentialedExperimentRunner:
    """Validate `1.30.0` credentials before exact PR #51."""

    def __init__(self, *, artifact_store: FileSystemArtifactStore) -> None:
        self._store = artifact_store
        self._runner = AdjudicationRunner(artifact_store=artifact_store)

    @staticmethod
    def _preflight(
        *,
        plan: ExperimentPlan,
        corpus: Any,
        adjudication_corpus: Any,
        conflict_adjudicator_registry: (
            WitnessConflictAdjudicatorRegistrySnapshot
        ),
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: Any,
        credentials: tuple[Any, ...],
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
        credential_evaluated_at: str,
        conflict_witness_evaluated_at: str,
        conflict_adjudication_evaluated_at: str,
        checkpoint_reverified_at: str,
        canonical_witness_evaluated_at: str,
        delegated_checkpoint_verified_at: str,
        revocation_evaluated_at: str,
        revocation_completed_at: str,
        checkpoint_completed_at: str,
        witness_completed_at: str,
        adjudication_completed_at: str,
        completed_at: str,
    ) -> None:
        if not experiment_run_id.strip():
            raise ValueError("experiment_run_id must not be empty")
        if plan.status is not ExperimentPlanStatus.FROZEN:
            raise ValueError(
                "credentialed current adjudication requires frozen plan"
            )
        if plan.corpus_ref != corpus.reference():
            raise ValueError(
                "plan must match credential-bound corpus exactly"
            )
        if plan.content_ids != corpus.content_ids:
            raise ValueError(
                "plan content order differs from credential corpus"
            )
        if corpus.predecessor_corpus_ref != adjudication_corpus.reference():
            raise ValueError(
                "credential corpus must bind exact 1.29.0 predecessor"
            )
        if corpus.corpus.reference() != adjudication_corpus.reference():
            raise ValueError(
                "credential corpus carries different 1.29.0 predecessor"
            )
        if (
            corpus.corpus.adjudicator_registry_ref
            != conflict_adjudicator_registry.reference()
        ):
            raise ValueError(
                "conflict adjudicator registry differs from 1.29.0"
            )
        if (
            corpus.issuer_registry_ref
            != credential_issuer_registry.reference()
        ):
            raise ValueError(
                "credential issuer registry differs from corpus"
            )
        if corpus.credential_policy_ref != credential_policy.reference():
            raise ValueError("credential policy differs from corpus")
        expected_credentials = tuple(
            item.credential_attestation_ref
            for item in corpus.credential_entries
        )
        if (
            tuple(item.reference() for item in credentials)
            != expected_credentials
        ):
            raise ValueError(
                "credential population differs from corpus order"
            )
        if (
            corpus.corpus.adjudication_ref
            != conflict_adjudication.reference()
        ):
            raise ValueError(
                "adjudication reference differs from exact 1.29.0"
            )
        times = (
            _parse_timestamp(corpus.created_at, "corpus.created_at"),
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
                revocation_evaluated_at,
                "revocation_evaluated_at",
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
            _parse_timestamp(completed_at, "completed_at"),
        )
        if tuple(sorted(times)) != times:
            raise ValueError(
                "credential, adjudication, and PR #51 chronology differs"
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
        adjudication_corpus: Any,
        evidence: Any,
        conflict_adjudicator_registry: (
            WitnessConflictAdjudicatorRegistrySnapshot
        ),
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: Any,
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        credential_decision: Any,
    ) -> None:
        expected = serialize_artifact(final.final_id, final)
        stored_final = self._store.get(
            final_ref.artifact_id,
            expected_hash=final_ref.artifact_hash,
        )
        if stored_final.payload != expected.payload:
            raise ArtifactIntegrityError(
                "stored credentialed final differs"
            )
        stored_corpus = self._store.get(
            final.credential_corpus_ref.artifact_id,
            expected_hash=final.credential_corpus_ref.artifact_hash,
        )
        if stored_corpus.payload != corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "stored 1.30.0 credential corpus differs"
            )
        predecessor = self._store.get(
            adjudication_corpus.reference().artifact_id,
            expected_hash=adjudication_corpus.reference().artifact_hash,
        )
        if predecessor.payload != adjudication_corpus.artifact().payload:
            raise ArtifactIntegrityError(
                "stored exact 1.29.0 predecessor differs"
            )
        stored_registry = self._store.get(
            final.adjudicator_registry_ref.artifact_id,
            expected_hash=final.adjudicator_registry_ref.artifact_hash,
        )
        if (
            stored_registry.payload
            != conflict_adjudicator_registry.canonical_payload
        ):
            raise ArtifactIntegrityError(
                "stored adjudicator registry differs"
            )
        stored_issuer = self._store.get(
            final.issuer_registry_ref.artifact_id,
            expected_hash=final.issuer_registry_ref.artifact_hash,
        )
        if (
            stored_issuer.payload
            != credential_issuer_registry.canonical_payload
        ):
            raise ArtifactIntegrityError(
                "stored credential issuer registry differs"
            )
        stored_policy = self._store.get(
            final.credential_policy_ref.artifact_id,
            expected_hash=final.credential_policy_ref.artifact_hash,
        )
        if stored_policy.payload != credential_policy.canonical_payload:
            raise ArtifactIntegrityError(
                "stored credential policy differs"
            )
        for reference in evidence.attestation_refs:
            self._store.get(
                reference.artifact_id,
                expected_hash=reference.artifact_hash,
            )
        stored_adjudication = self._store.get(
            final.adjudication_ref.artifact_id,
            expected_hash=final.adjudication_ref.artifact_hash,
        )
        if (
            stored_adjudication.payload
            != conflict_adjudication.canonical_payload
        ):
            raise ArtifactIntegrityError(
                "stored conflict adjudication differs"
            )
        expected_decision = serialize_artifact(
            f"{final.experiment_run_id}:{_ARTIFACT_PREFIX}-decision",
            credential_decision,
        )
        stored_decision = self._store.get(
            final.credential_decision_ref.artifact_id,
            expected_hash=final.credential_decision_ref.artifact_hash,
        )
        if stored_decision.payload != expected_decision.payload:
            raise ArtifactIntegrityError(
                "stored credential decision differs"
            )
        if final.adjudication_final_ref is not None:
            self._store.get(
                final.adjudication_final_ref.artifact_id,
                expected_hash=final.adjudication_final_ref.artifact_hash,
            )

    def run(
        self,
        *,
        plan: ExperimentPlan,
        corpus: Any,
        adjudication_corpus: Any,
        conflict_adjudicator_registry: (
            WitnessConflictAdjudicatorRegistrySnapshot
        ),
        credential_issuer_registry: CredentialIssuerRegistrySnapshot,
        credential_policy: Any,
        credentials: tuple[Any, ...],
        conflict_adjudication_policy: (
            WitnessConflictAdjudicationPolicySnapshot
        ),
        conflict_adjudication: WitnessConflictAdjudicationSnapshot,
        experiment_run_id: str,
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
        completed_at: str,
        **delegated_inputs: Any,
    ) -> Any:
        """Return credential abstention or exact delegated PR #51."""

        try:
            self._preflight(
                plan=plan,
                corpus=corpus,
                adjudication_corpus=adjudication_corpus,
                conflict_adjudicator_registry=(
                    conflict_adjudicator_registry
                ),
                credential_issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                credentials=credentials,
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
                revocation_evaluated_at=(
                    current_revocation_evaluated_at
                ),
                revocation_completed_at=revocation_completed_at,
                checkpoint_completed_at=checkpoint_completed_at,
                witness_completed_at=witness_completed_at,
                adjudication_completed_at=adjudication_completed_at,
                completed_at=completed_at,
            )
        except ValueError as exc:
            raise CredentialExperimentError(
                CredentialRunnerStage.PREFLIGHT,
                str(exc),
            ) from exc

        try:
            predecessor = self._store.get(
                corpus.predecessor_corpus_ref.artifact_id,
                expected_hash=corpus.predecessor_corpus_ref.artifact_hash,
            )
            if predecessor.payload != adjudication_corpus.artifact().payload:
                raise ArtifactIntegrityError(
                    "stored exact 1.29.0 predecessor differs"
                )
            evidence = load_credential_evidence(
                self._store,
                corpus=corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                adjudication=conflict_adjudication,
            )
        except (
            ArtifactStoreError,
            CredentialError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialExperimentError(
                CredentialRunnerStage.EVIDENCE_LOADING,
                str(exc),
            ) from exc

        try:
            credential_decision = validate_credentials(
                plan=plan,
                corpus=corpus,
                adjudicator_registry=conflict_adjudicator_registry,
                issuer_registry=credential_issuer_registry,
                credential_policy=credential_policy,
                attestations=evidence.attestations,
                adjudication=conflict_adjudication,
                evaluated_at=credential_evaluated_at,
            )
        except (CredentialError, ValueError) as exc:
            raise CredentialExperimentError(
                CredentialRunnerStage.CREDENTIAL_VALIDATION,
                str(exc),
            ) from exc

        try:
            decision_ref = self._persist(
                artifact_id=(
                    f"{experiment_run_id}:{_ARTIFACT_PREFIX}-decision"
                ),
                value=credential_decision,
                message="stored credential decision differs",
            )
        except (
            ArtifactStoreError,
            CanonicalSerializationError,
            OSError,
            ValueError,
        ) as exc:
            raise CredentialExperimentError(
                CredentialRunnerStage.CREDENTIAL_DECISION_PERSISTENCE,
                str(exc),
            ) from exc

        adjudication_receipt: Any = None
        if credential_decision.outcome is CredentialDecisionOutcome.EXECUTE:
            predecessor_plan = replace(
                plan,
                corpus_ref=adjudication_corpus.reference(),
                content_ids=adjudication_corpus.content_ids,
            )
            try:
                adjudication_receipt = self._runner.run(
                    plan=predecessor_plan,
                    corpus=adjudication_corpus,
                    conflict_adjudicator_registry=(
                        conflict_adjudicator_registry
                    ),
                    conflict_adjudication_policy=(
                        conflict_adjudication_policy
                    ),
                    conflict_adjudication=conflict_adjudication,
                    experiment_run_id=experiment_run_id,
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
                    completed_at=adjudication_completed_at,
                    **delegated_inputs,
                )
            except AdjudicationExperimentError as exc:
                raise CredentialExperimentError(
                    CredentialRunnerStage.ADJUDICATION_EXECUTION,
                    str(exc),
                    completed_content_ids=exc.completed_content_ids,
                ) from exc

        if adjudication_receipt is None:
            values: tuple[Any, ...] = (
                None,
            ) * len(ADJUDICATION_OUTCOME_FIELDS)
            terminal_outcome = ReviewDecisionOutcome.ABSTAIN
            adjudication_final_ref = None
            suffix = "abstention"
        else:
            values = _adjudication_outcomes(adjudication_receipt)
            terminal_outcome = adjudication_receipt.terminal_outcome
            adjudication_final_ref = (
                adjudication_receipt.final_manifest_ref
            )
            suffix = (
                "completion"
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else "terminal-abstention"
            )

        common = {
            "experiment_run_id": experiment_run_id,
            "status": CredentialRunnerStatus.VERIFIED,
            _CREDENTIAL_FIELD: credential_decision.outcome,
            **dict(
                zip(
                    ADJUDICATION_OUTCOME_FIELDS,
                    values,
                    strict=True,
                )
            ),
            "terminal_outcome": terminal_outcome,
            "experiment_id": plan.experiment_id,
            "experiment_version": plan.experiment_version,
            "content_ids": plan.content_ids,
            "credential_corpus_ref": evidence.corpus_ref,
            "adjudicator_registry_ref": (
                evidence.adjudicator_registry_ref
            ),
            "issuer_registry_ref": evidence.issuer_registry_ref,
            "credential_policy_ref": evidence.credential_policy_ref,
            "credential_attestation_refs": evidence.attestation_refs,
            "adjudication_ref": evidence.adjudication_ref,
            "credential_decision_ref": decision_ref,
        }
        final_id = f"{experiment_run_id}:{_ARTIFACT_PREFIX}-{suffix}"
        final = CredentialFinalManifest(
            final_id=final_id,
            **common,
            adjudication_final_ref=adjudication_final_ref,
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
            raise CredentialExperimentError(
                CredentialRunnerStage.FINAL_PERSISTENCE,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        try:
            self._verify_final(
                final=final,
                final_ref=final_ref,
                corpus=corpus,
                adjudication_corpus=adjudication_corpus,
                evidence=evidence,
                conflict_adjudicator_registry=(
                    conflict_adjudicator_registry
                ),
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
            completed_ids = (
                plan.content_ids
                if terminal_outcome is ReviewDecisionOutcome.EXECUTE
                else ()
            )
            raise CredentialExperimentError(
                CredentialRunnerStage.VERIFICATION,
                str(exc),
                completed_content_ids=completed_ids,
            ) from exc

        return VerifiedCredentialReceipt(
            **common,
            adjudication_receipt=adjudication_receipt,
            final_manifest_ref=final_ref,
            verified_checks=VERIFIED_CHECKS,
            completed_at=completed_at,
        )


_LONG_CHECKS = (
    "CREDENTIALED_CURRENT_REVOCATION_CONFLICT_ADJUDICATOR_CHECKPOINT_"
    "WITNESS_VERIFIED_CHECKS"
)
_LONG_ERROR = (
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentError"
)
_LONG_FINAL = (
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "FinalManifest"
)
_LONG_RUNNER = (
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "ExperimentRunner"
)
_LONG_STAGE = (
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStage"
)
_LONG_STATUS = (
    "CredentialedCurrentRevocationConflictAdjudicatorCheckpointWitness"
    "RunnerStatus"
)
_LONG_RECEIPT = (
    "VerifiedCredentialedCurrentRevocationConflictAdjudicatorCheckpoint"
    "WitnessReceipt"
)

globals()[_LONG_CHECKS] = VERIFIED_CHECKS
globals()[_LONG_ERROR] = CredentialExperimentError
globals()[_LONG_FINAL] = CredentialFinalManifest
globals()[_LONG_RUNNER] = CredentialedExperimentRunner
globals()[_LONG_STAGE] = CredentialRunnerStage
globals()[_LONG_STATUS] = CredentialRunnerStatus
globals()[_LONG_RECEIPT] = VerifiedCredentialReceipt

__all__ = [
    _LONG_CHECKS,
    _LONG_ERROR,
    _LONG_FINAL,
    _LONG_RUNNER,
    _LONG_STAGE,
    _LONG_STATUS,
    _LONG_RECEIPT,
]
