"""Credential the adjudicator authorized to resolve adjudicator-checkpoint witness conflicts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from ctrt.adjudicator_checkpoint_witness_conflict_adjudication import (
    AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
)
from ctrt.adjudicator_credential_attestation import (
    AdjudicatorCredentialAttestationSnapshot,
    AdjudicatorCredentialDecisionReport,
    AdjudicatorCredentialEvidenceEntry,
    AdjudicatorCredentialPolicySnapshot,
    AdjudicatorCredentialSummary,
)
from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.confidence import SystemAbstention
from ctrt.experiments import ExperimentPlan, ExperimentPlanStatus, VersionedArtifactRef
from ctrt.reviewer_credential_attestation import (
    CredentialAttestationStatus,
    CredentialDecisionOutcome,
    CredentialIssuerRegistryLifecycle,
    CredentialIssuerRegistrySnapshot,
    CredentialPolicyLifecycle,
)
from ctrt.serialization import CanonicalArtifact
from ctrt.witness_conflict_adjudication import (
    WitnessConflictAdjudicationSnapshot,
    WitnessConflictAdjudicatorRegistryLifecycle,
    WitnessConflictAdjudicatorRegistrySnapshot,
    WitnessConflictAdjudicatorRole,
)


class AdjudicatorCheckpointConflictCredentialError(ValueError):
    """Raised when checkpoint-conflict adjudicator credentials are invalid."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AdjudicatorCheckpointConflictCredentialError(
            f"{field_name} must be an object"
        )
    if any(not isinstance(key, str) for key in value):
        raise AdjudicatorCheckpointConflictCredentialError(
            f"{field_name} keys must be strings"
        )
    return value


def _versioned_ref(value: object, field_name: str) -> VersionedArtifactRef:
    document = _mapping(value, field_name)
    for key in ("artifact_id", "artifact_version", "artifact_hash"):
        item = document.get(key)
        if not isinstance(item, str) or not item.strip():
            raise AdjudicatorCheckpointConflictCredentialError(
                f"{field_name}.{key} must be a non-empty string"
            )
    return VersionedArtifactRef(
        artifact_id=str(document["artifact_id"]),
        artifact_version=str(document["artifact_version"]),
        artifact_hash=str(document["artifact_hash"]),
    )


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not value.strip():
        raise AdjudicatorCheckpointConflictCredentialError(
            f"{field_name} must not be empty"
        )
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AdjudicatorCheckpointConflictCredentialError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise AdjudicatorCheckpointConflictCredentialError(
            f"{field_name} must include a timezone"
        )
    return parsed


@dataclass(frozen=True, slots=True)
class CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot:
    """Adjudication-bound corpus plus exact conflict-adjudicator credentials."""

    corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot
    predecessor_corpus_ref: VersionedArtifactRef
    issuer_registry_ref: VersionedArtifactRef
    credential_policy_ref: VersionedArtifactRef
    credential_entries: tuple[AdjudicatorCredentialEvidenceEntry, ...]

    def __post_init__(self) -> None:
        ids = tuple(item.adjudicator_id for item in self.credential_entries)
        if not ids:
            raise AdjudicatorCheckpointConflictCredentialError(
                "credential-bound checkpoint conflict corpus requires credentials"
            )
        if len(ids) != len(set(ids)):
            raise AdjudicatorCheckpointConflictCredentialError(
                "checkpoint conflict credential entries must use unique IDs"
            )

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, object],
    ) -> CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot:
        values = document.get(
            "adjudicator_checkpoint_conflict_adjudicator_credentials"
        )
        if not isinstance(values, list):
            raise AdjudicatorCheckpointConflictCredentialError(
                "adjudicator_checkpoint_conflict_adjudicator_credentials "
                "must be an array"
            )
        entries: list[AdjudicatorCredentialEvidenceEntry] = []
        for value in values:
            if not isinstance(value, Mapping):
                raise AdjudicatorCheckpointConflictCredentialError(
                    "checkpoint conflict credential entries must be objects"
                )
            entries.append(
                AdjudicatorCredentialEvidenceEntry.from_document(value)
            )
        return cls(
            corpus=(
                AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot
                .from_document(document)
            ),
            predecessor_corpus_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_credential_predecessor_corpus_ref"
                ),
                "adjudicator_checkpoint_conflict_credential_predecessor_corpus_ref",
            ),
            issuer_registry_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_issuer_registry_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_issuer_registry_ref",
            ),
            credential_policy_ref=_versioned_ref(
                document.get(
                    "adjudicator_checkpoint_conflict_adjudicator_credential_policy_ref"
                ),
                "adjudicator_checkpoint_conflict_adjudicator_credential_policy_ref",
            ),
            credential_entries=tuple(entries),
        )

    @property
    def content_ids(self) -> tuple[str, ...]:
        return self.corpus.content_ids

    def reference(self) -> VersionedArtifactRef:
        return self.corpus.reference()

    def artifact(self) -> CanonicalArtifact:
        return self.corpus.artifact()


@dataclass(frozen=True, slots=True)
class StoredAdjudicatorCheckpointConflictCredentialEvidence:
    """Stored credential graph and preserved checkpoint-conflict adjudication."""

    corpus_ref: StoredArtifactRef
    adjudicator_registry_ref: StoredArtifactRef
    issuer_registry_ref: StoredArtifactRef
    credential_policy_ref: StoredArtifactRef
    adjudication_ref: StoredArtifactRef
    attestation_refs: tuple[StoredArtifactRef, ...]
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...]


def _load_attestation(
    store: FileSystemArtifactStore,
    reference: StoredArtifactRef,
) -> AdjudicatorCredentialAttestationSnapshot:
    artifact = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    attestation = AdjudicatorCredentialAttestationSnapshot.from_artifact(artifact)
    if attestation.reference() != reference:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential reference differs from corpus"
        )
    return attestation


def load_adjudicator_checkpoint_conflict_credential_evidence(
    store: FileSystemArtifactStore,
    *,
    corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    adjudication: WitnessConflictAdjudicationSnapshot,
) -> StoredAdjudicatorCheckpointConflictCredentialEvidence:
    """Load and reverify the credential-bound checkpoint-conflict graph."""

    corpus_artifact = store.get(
        corpus.reference().artifact_id,
        expected_hash=corpus.reference().artifact_hash,
    )
    if corpus_artifact.payload != corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential corpus differs from expected"
        )
    registry_artifact = store.get(
        adjudicator_registry.registry_id,
        expected_hash=adjudicator_registry.artifact_hash,
    )
    if registry_artifact.payload != adjudicator_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict adjudicator registry differs"
        )
    issuer_artifact = store.get(
        issuer_registry.registry_id,
        expected_hash=issuer_registry.artifact_hash,
    )
    if issuer_artifact.payload != issuer_registry.canonical_payload:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential issuer registry differs"
        )
    policy_artifact = store.get(
        credential_policy.policy_id,
        expected_hash=credential_policy.artifact_hash,
    )
    if policy_artifact.payload != credential_policy.canonical_payload:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential policy differs"
        )
    adjudication_artifact = store.get(
        adjudication.artifact_id,
        expected_hash=adjudication.artifact_hash,
    )
    if adjudication_artifact.payload != adjudication.canonical_payload:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict adjudication differs"
        )
    attestations = tuple(
        _load_attestation(store, item.credential_attestation_ref)
        for item in corpus.credential_entries
    )
    return StoredAdjudicatorCheckpointConflictCredentialEvidence(
        corpus_ref=store.reference(corpus.reference().artifact_id),
        adjudicator_registry_ref=store.reference(adjudicator_registry.registry_id),
        issuer_registry_ref=store.reference(issuer_registry.registry_id),
        credential_policy_ref=store.reference(credential_policy.policy_id),
        adjudication_ref=store.reference(adjudication.artifact_id),
        attestation_refs=tuple(item.reference() for item in attestations),
        attestations=attestations,
    )


def validate_adjudicator_checkpoint_conflict_credentials(
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> AdjudicatorCredentialDecisionReport:
    """Evaluate conflict-adjudicator credentials without rewriting adjudication."""

    evaluated = _parse_timestamp(evaluated_at, "evaluated_at")
    if plan.status is not ExperimentPlanStatus.FROZEN:
        raise AdjudicatorCheckpointConflictCredentialError(
            "only a frozen experiment plan may pass checkpoint conflict credentials"
        )
    if plan.corpus_ref != corpus.reference() or plan.content_ids != corpus.content_ids:
        raise AdjudicatorCheckpointConflictCredentialError(
            "experiment plan differs from credential-bound checkpoint conflict corpus"
        )
    if corpus.corpus.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict adjudicator registry differs from predecessor corpus"
        )
    if corpus.issuer_registry_ref != issuer_registry.reference():
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential issuer registry differs"
        )
    if corpus.credential_policy_ref != credential_policy.reference():
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential policy differs"
        )
    if corpus.corpus.adjudication_ref != adjudication.reference():
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict adjudication reference differs"
        )
    if (
        adjudicator_registry.status
        is not WitnessConflictAdjudicatorRegistryLifecycle.ACCEPTED
    ):
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict adjudicator registry must be accepted"
        )
    if issuer_registry.status is not CredentialIssuerRegistryLifecycle.ACCEPTED:
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential issuer registry must be accepted"
        )
    if credential_policy.status is not CredentialPolicyLifecycle.ACCEPTED:
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential policy must be accepted"
        )
    if credential_policy.issuer_registry_ref != issuer_registry.reference():
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential policy issuer registry differs"
        )
    if credential_policy.adjudicator_registry_ref != adjudicator_registry.reference():
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential policy adjudicator registry differs"
        )
    if len(corpus.credential_entries) != len(adjudicator_registry.adjudicators):
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential population must match registry"
        )
    if len(attestations) != len(corpus.credential_entries):
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential population differs from corpus"
        )

    failures: list[str] = []
    summaries: list[AdjudicatorCredentialSummary] = []
    by_id: dict[str, AdjudicatorCredentialAttestationSnapshot] = {}
    for adjudicator, entry, attestation in zip(
        adjudicator_registry.adjudicators,
        corpus.credential_entries,
        attestations,
        strict=True,
    ):
        if (entry.adjudicator_id, entry.identity_revision) != (
            adjudicator.adjudicator_id,
            adjudicator.identity_revision,
        ):
            failures.append(
                f"{adjudicator.adjudicator_id}: credential entry identity differs"
            )
            continue
        if attestation.reference() != entry.credential_attestation_ref:
            failures.append(
                f"{adjudicator.adjudicator_id}: credential reference differs"
            )
            continue
        if (attestation.adjudicator_id, attestation.identity_revision) != (
            adjudicator.adjudicator_id,
            adjudicator.identity_revision,
        ):
            failures.append(
                f"{adjudicator.adjudicator_id}: attested identity revision differs"
            )
            continue
        expected_roles = (adjudicator.role,)
        if (
            credential_policy.require_exact_role_match
            and attestation.authorized_roles != expected_roles
        ):
            failures.append(
                f"{adjudicator.adjudicator_id}: attested role differs from registry"
            )
            continue
        if attestation.credential_type != credential_policy.credential_type:
            failures.append(
                f"{adjudicator.adjudicator_id}: credential type differs from policy"
            )
            continue
        issuer = issuer_registry.issuer(attestation.issuer_id)
        if issuer is None:
            failures.append(
                f"{adjudicator.adjudicator_id}: attestation issuer is absent"
            )
            continue
        if issuer.issuer_revision != attestation.issuer_revision:
            failures.append(
                f"{adjudicator.adjudicator_id}: issuer revision differs"
            )
            continue
        if attestation.credential_type not in issuer.credential_types:
            failures.append(
                f"{adjudicator.adjudicator_id}: issuer may not issue credential type"
            )
            continue

        reasons: list[str] = []
        if not issuer.active:
            reasons.append("credential-issuer-inactive")
        if attestation.status is CredentialAttestationStatus.SUSPENDED:
            reasons.append("credential-status:suspended")
        elif attestation.status is CredentialAttestationStatus.REVOKED:
            reasons.append("credential-status:revoked")
        valid_from = _parse_timestamp(attestation.valid_from, "valid_from")
        valid_until = _parse_timestamp(attestation.valid_until, "valid_until")
        if evaluated < valid_from:
            reasons.append("credential-not-yet-valid")
        if evaluated >= valid_until:
            reasons.append("credential-expired")
        summaries.append(
            AdjudicatorCredentialSummary(
                adjudicator_id=adjudicator.adjudicator_id,
                identity_revision=adjudicator.identity_revision,
                issuer_id=attestation.issuer_id,
                issuer_revision=attestation.issuer_revision,
                authorized_roles=attestation.authorized_roles,
                attestation_status=attestation.status,
                valid_from=attestation.valid_from,
                valid_until=attestation.valid_until,
                abstention=SystemAbstention(
                    triggered=bool(reasons),
                    reasons=tuple(reasons),
                ),
            )
        )
        by_id[adjudicator.adjudicator_id] = attestation

    if adjudication.adjudicator_id is not None:
        selected_attestation = by_id.get(adjudication.adjudicator_id)
        if selected_attestation is None:
            failures.append("checkpoint conflict adjudication credential is absent")
        elif (
            adjudication.adjudicator_identity_revision
            != selected_attestation.identity_revision
        ):
            failures.append(
                "checkpoint conflict adjudication identity differs from credential"
            )
        elif WitnessConflictAdjudicatorRole.WITNESS_CONFLICT_ADJUDICATOR not in (
            selected_attestation.authorized_roles
        ):
            failures.append(
                "checkpoint conflict adjudication role is not attested"
            )

    if failures:
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential evidence failed: "
            + " | ".join(failures)
        )
    outcome = (
        CredentialDecisionOutcome.ABSTAIN
        if any(item.abstention.triggered for item in summaries)
        else CredentialDecisionOutcome.EXECUTE
    )
    return AdjudicatorCredentialDecisionReport(
        experiment_id=plan.experiment_id,
        experiment_version=plan.experiment_version,
        credential_corpus_ref=corpus.reference(),
        adjudicator_registry_ref=adjudicator_registry.reference(),
        issuer_registry_ref=issuer_registry.reference(),
        credential_policy_ref=credential_policy.reference(),
        adjudication_ref=adjudication.reference(),
        outcome=outcome,
        credentials=tuple(summaries),
        evaluated_at=evaluated_at,
    )


def persist_credential_bound_adjudicator_checkpoint_conflict_corpus(
    store: FileSystemArtifactStore,
    *,
    plan: ExperimentPlan,
    corpus: CredentialBoundAdjudicatorCheckpointConflictCorpusSnapshot,
    predecessor_corpus: AdjudicationBoundAdjudicatorCheckpointWitnessCorpusSnapshot,
    adjudicator_registry: WitnessConflictAdjudicatorRegistrySnapshot,
    issuer_registry: CredentialIssuerRegistrySnapshot,
    credential_policy: AdjudicatorCredentialPolicySnapshot,
    attestations: tuple[AdjudicatorCredentialAttestationSnapshot, ...],
    adjudication: WitnessConflictAdjudicationSnapshot,
    evaluated_at: str,
) -> StoredAdjudicatorCheckpointConflictCredentialEvidence:
    """Persist credential graph members before publishing the manifest last."""

    if predecessor_corpus.reference() != corpus.predecessor_corpus_ref:
        raise AdjudicatorCheckpointConflictCredentialError(
            "predecessor corpus differs from checkpoint conflict credential corpus"
        )
    if predecessor_corpus.content_ids != corpus.content_ids:
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential corpus content differs from predecessor"
        )
    predecessor = store.get(
        predecessor_corpus.reference().artifact_id,
        expected_hash=predecessor_corpus.reference().artifact_hash,
    )
    if predecessor.payload != predecessor_corpus.artifact().payload:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict predecessor corpus differs"
        )
    decision = validate_adjudicator_checkpoint_conflict_credentials(
        plan=plan,
        corpus=corpus,
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        attestations=attestations,
        adjudication=adjudication,
        evaluated_at=evaluated_at,
    )
    if decision.outcome is CredentialDecisionOutcome.ABSTAIN:
        raise AdjudicatorCheckpointConflictCredentialError(
            "checkpoint conflict credential corpus publication requires "
            "eligible attestations"
        )
    if store.append(issuer_registry.artifact()).artifact_hash != (
        issuer_registry.artifact_hash
    ):
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential issuer registry differs"
        )
    if store.append(credential_policy.artifact()).artifact_hash != (
        credential_policy.artifact_hash
    ):
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential policy differs"
        )
    for attestation in attestations:
        if store.append(attestation.artifact()) != attestation.reference():
            raise ArtifactIntegrityError(
                "stored checkpoint conflict credential attestation differs"
            )
    manifest_ref = store.append(corpus.artifact())
    if manifest_ref.artifact_hash != corpus.reference().artifact_hash:
        raise ArtifactIntegrityError(
            "stored checkpoint conflict credential corpus reference differs"
        )
    return load_adjudicator_checkpoint_conflict_credential_evidence(
        store,
        corpus=corpus,
        adjudicator_registry=adjudicator_registry,
        issuer_registry=issuer_registry,
        credential_policy=credential_policy,
        adjudication=adjudication,
    )
