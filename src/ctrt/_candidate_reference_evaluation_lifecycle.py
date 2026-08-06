"""Execute a preregistered descriptive candidate-to-human-reference evaluation.

The frozen protocol is loaded before candidate execution. Human-reference judgments
remain independent observations rather than ground truth, and correspondence remains
a denominator-preserving description rather than accuracy.

Production execution refuses collections marked as synthetic fixtures. Tests may use
the explicit fixture entry point, whose artifacts and report remain visibly marked as
not human research evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.candidate_eligibility import (
    CandidateRegistrySnapshot,
    RegistryLifecycle,
    candidate_authorization_reasons,
)
from ctrt.candidate_reference_evaluation_protocol import (
    CANDIDATE_BUCKETS,
    DEFAULT_ANNOTATION_PROTOCOL,
    DEFAULT_CORPUS,
    DEFAULT_EVALUATION_PROTOCOL,
    DEFAULT_REAL_CANDIDATE_REGISTRY,
    DEFAULT_SYNTHESIS_PROTOCOL,
    REQUIRED_CANDIDATE_STATUS,
    CandidateReferenceEvaluationProtocol,
    DirectionBucket,
    DirectionalCorrespondence,
    HumanDirectionalDistribution,
    RepositoryEvaluationBindings,
    load_default_evaluation_protocol,
    validate_repository_bindings,
)
from ctrt.contracts import ContentItem, ModelResult, ResultStatus, SourceType
from ctrt.experiments import VersionedArtifactRef
from ctrt.human_reference_protocol import EvaluationCorpus, ValenceLabel
from ctrt.human_reference_synthesis import (
    INSUFFICIENT_COVERAGE,
    SUFFICIENT_COVERAGE,
    ItemSynthesis,
    VerifiedSynthesisReceipt,
    find_collection_store,
    is_test_fixture_collection,
    run_human_reference_synthesis,
)
from ctrt.real_candidate_registry import RealCandidateBinding, real_candidate_binding
from ctrt.serialization import canonical_sha256, serialize_artifact
from ctrt.vader_adapter import (
    PRESERVED_OUTPUT_KEYS,
    VADER_ADAPTER_REVISION,
    VADER_ANALYZER_ID,
    VADER_CANDIDATE_ID,
    VADER_PINNED_VERSION,
    VaderSentimentAdapter,
    load_vader_sentiment_adapter,
)

EVALUATION_VERSION = "ctrt-candidate-reference-evaluation@0.1.0"
EVALUATION_RECORD_TYPE = "candidate_reference_descriptive_evaluation"
_RUN_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")

EVALUATION_NON_CLAIMS = (
    "Human-reference judgments are not ground truth, and candidate correspondence "
    "with them is not correctness.",
    "A same-direction count is descriptive correspondence, not accuracy.",
    "A different-direction count is descriptive divergence, not proof that either "
    "the candidate or a human response is wrong.",
    "Human abstention, candidate abstention, candidate failure, and insufficient "
    "reference coverage remain separate outcomes.",
    "The participating annotators and repository-authored pilot corpus do not "
    "represent any population.",
    "The VADER compound value is not confidence, probability, calibration, or an "
    "overall CTRT score.",
    "This protocol does not rank or select a candidate and does not advance the "
    "candidate lifecycle.",
    "This protocol does not authorize creator-facing, reader-facing, moderation, "
    "restriction, or enforcement use.",
)

FIXTURE_NON_CLAIM = (
    "This evaluation used synthetic test-fixture annotations. It is not human "
    "research evidence and must never be reported as an empirical human result."
)


class CandidateReferenceEvaluationError(ValueError):
    """Raised when the preregistered evaluation cannot proceed exactly."""


class ItemEvaluationStatus(StrEnum):
    """Whether an item yielded a bounded candidate-to-reference description."""

    DESCRIBED = "described"
    INSUFFICIENT_REFERENCE_COVERAGE = "insufficient_reference_coverage"
    CANDIDATE_ABSTAINED = "candidate_abstained"
    CANDIDATE_FAILED = "candidate_failed"


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CandidateReferenceEvaluationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CandidateReferenceEvaluationError(f"{field_name} keys must be strings")
    return value


def _load_document(path: Path, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateReferenceEvaluationError(
            f"unable to read {field_name} from {path}"
        ) from exc
    return _mapping(value, field_name)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise CandidateReferenceEvaluationError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _ref_document(reference: StoredArtifactRef) -> dict[str, str]:
    return {
        "artifact_id": reference.artifact_id,
        "artifact_hash": reference.artifact_hash,
        "canonicalization_version": reference.canonicalization_version,
        "media_type": reference.media_type,
    }


@dataclass(frozen=True, slots=True)
class CandidateEvaluationEligibility:
    """Exact candidate and registry facts reverified immediately before execution."""

    candidate_registry_ref: VersionedArtifactRef
    candidate_id: str
    analyzer_id: str
    dimension_id: str
    dimension_version: str
    adapter_revision: str
    package_distribution: str
    package_version: str
    configuration_hash: str
    lifecycle_status: str
    license_review_status: str
    user_facing_execution_permitted: bool

    def __post_init__(self) -> None:
        if self.candidate_id != VADER_CANDIDATE_ID:
            raise CandidateReferenceEvaluationError("unexpected candidate identity")
        if self.analyzer_id != VADER_ANALYZER_ID:
            raise CandidateReferenceEvaluationError("unexpected analyzer identity")
        if self.adapter_revision != VADER_ADAPTER_REVISION:
            raise CandidateReferenceEvaluationError("unexpected adapter revision")
        if self.package_version != VADER_PINNED_VERSION:
            raise CandidateReferenceEvaluationError("unexpected package version")
        if self.lifecycle_status != REQUIRED_CANDIDATE_STATUS:
            raise CandidateReferenceEvaluationError(
                "evaluation requires the candidate to remain eligible_for_evaluation"
            )
        if self.user_facing_execution_permitted:
            raise CandidateReferenceEvaluationError(
                "candidate evaluation may not permit user-facing execution"
            )


@dataclass(frozen=True, slots=True)
class CandidateReferenceEvaluationPlan:
    """Frozen run plan binding the preregistered protocol before execution."""

    evaluation_id: str
    evaluation_version: str
    record_type: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    candidate_registry_ref: VersionedArtifactRef
    candidate_id: str
    analyzer_id: str
    adapter_revision: str
    configuration_hash: str
    annotation_protocol_id: str
    annotation_protocol_version: str
    synthesis_protocol_id: str
    synthesis_protocol_version: str
    synthesis_completion_ref: StoredArtifactRef
    corpus_id: str
    corpus_version: str
    corpus_hash: str
    dimension_id: str
    dimension_version: str
    item_ids: tuple[str, ...]
    synthetic_test_fixture: bool
    non_claims: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        if self.evaluation_version != EVALUATION_VERSION:
            raise CandidateReferenceEvaluationError("unsupported evaluation version")
        if self.record_type != EVALUATION_RECORD_TYPE:
            raise CandidateReferenceEvaluationError("unsupported evaluation record type")
        if not self.item_ids:
            raise CandidateReferenceEvaluationError("evaluation requires at least one item")
        if len(self.item_ids) != len(set(self.item_ids)):
            raise CandidateReferenceEvaluationError("evaluation item IDs must be unique")
        expected_non_claims = (
            (*EVALUATION_NON_CLAIMS, FIXTURE_NON_CLAIM)
            if self.synthetic_test_fixture
            else EVALUATION_NON_CLAIMS
        )
        if self.non_claims != expected_non_claims:
            raise CandidateReferenceEvaluationError(
                "evaluation plan must preserve the exact declared non-claims"
            )


@dataclass(frozen=True, slots=True)
class PreservedCandidateOutput:
    """One exact VADER output retained with its declared numeric bounds."""

    key: str
    value: float
    lower_bound: float
    upper_bound: float

    def __post_init__(self) -> None:
        if self.key not in PRESERVED_OUTPUT_KEYS:
            raise CandidateReferenceEvaluationError("unexpected candidate output key")
        if self.lower_bound >= self.upper_bound:
            raise CandidateReferenceEvaluationError("candidate output bounds are invalid")
        if not self.lower_bound <= self.value <= self.upper_bound:
            raise CandidateReferenceEvaluationError(
                "candidate output falls outside its declared bounds"
            )


@dataclass(frozen=True, slots=True)
class CandidateReferenceItemEvaluation:
    """One item-level descriptive pairing with all original evidence retained."""

    position: int
    item_id: str
    content_hash: str
    text: str
    human_coverage_status: str
    original_human_distribution: Mapping[str, int]
    human_directional_distribution: HumanDirectionalDistribution
    candidate_result_status: str
    candidate_raw_output: Mapping[str, object]
    candidate_outputs: tuple[PreservedCandidateOutput, ...]
    candidate_bucket: DirectionBucket | None
    correspondence: DirectionalCorrespondence | None
    evaluation_status: ItemEvaluationStatus
    exclusion_reasons: tuple[str, ...]
    candidate_result_ref: StoredArtifactRef
    human_synthesis_ref: StoredArtifactRef

    def __post_init__(self) -> None:
        if self.position < 0:
            raise CandidateReferenceEvaluationError("item position must be non-negative")
        expected_labels = {label.value for label in ValenceLabel}
        if set(self.original_human_distribution) != expected_labels:
            raise CandidateReferenceEvaluationError(
                "item evaluation must preserve every original human response option"
            )
        if sum(self.original_human_distribution.values()) != (
            self.human_directional_distribution.total_responses
        ):
            raise CandidateReferenceEvaluationError(
                "original and directional human distributions must preserve totals"
            )
        if self.human_coverage_status not in {
            SUFFICIENT_COVERAGE,
            INSUFFICIENT_COVERAGE,
        }:
            raise CandidateReferenceEvaluationError(
                "human coverage status must remain explicit"
            )
        if self.evaluation_status is ItemEvaluationStatus.DESCRIBED:
            if self.human_coverage_status != SUFFICIENT_COVERAGE:
                raise CandidateReferenceEvaluationError(
                    "described correspondence requires sufficient human coverage"
                )
            if self.candidate_result_status != ResultStatus.SUCCESS.value:
                raise CandidateReferenceEvaluationError(
                    "described correspondence requires a successful candidate result"
                )
            if self.candidate_bucket not in CANDIDATE_BUCKETS:
                raise CandidateReferenceEvaluationError(
                    "described correspondence requires one candidate direction"
                )
            if self.correspondence is None:
                raise CandidateReferenceEvaluationError(
                    "described correspondence requires preserved counts"
                )
            if self.exclusion_reasons:
                raise CandidateReferenceEvaluationError(
                    "described correspondence may not carry exclusion reasons"
                )
        else:
            if self.correspondence is not None:
                raise CandidateReferenceEvaluationError(
                    "non-described items may not carry correspondence"
                )
            if not self.exclusion_reasons:
                raise CandidateReferenceEvaluationError(
                    "non-described items require explicit exclusion reasons"
                )
        if self.candidate_result_status == ResultStatus.SUCCESS.value:
            if tuple(item.key for item in self.candidate_outputs) != PRESERVED_OUTPUT_KEYS:
                raise CandidateReferenceEvaluationError(
                    "successful candidate output must preserve all four outputs in order"
                )
        elif self.candidate_outputs:
            raise CandidateReferenceEvaluationError(
                "abstained or failed candidate results may not carry numeric outputs"
            )


@dataclass(frozen=True, slots=True)
class DirectionalContingency:
    """Three-by-three candidate-direction by human-direction response counts."""

    candidate_unfavorable_human_unfavorable: int
    candidate_unfavorable_human_neutral: int
    candidate_unfavorable_human_favorable: int
    candidate_neutral_human_unfavorable: int
    candidate_neutral_human_neutral: int
    candidate_neutral_human_favorable: int
    candidate_favorable_human_unfavorable: int
    candidate_favorable_human_neutral: int
    candidate_favorable_human_favorable: int
    directional_denominator: int

    def __post_init__(self) -> None:
        cells = self.cells
        if any(isinstance(value, bool) or value < 0 for value in cells.values()):
            raise CandidateReferenceEvaluationError(
                "contingency counts must be non-negative integers"
            )
        if sum(cells.values()) != self.directional_denominator:
            raise CandidateReferenceEvaluationError(
                "contingency cells must equal the preserved directional denominator"
            )

    @property
    def cells(self) -> Mapping[str, int]:
        return {
            "candidate_unfavorable_human_unfavorable": (
                self.candidate_unfavorable_human_unfavorable
            ),
            "candidate_unfavorable_human_neutral": (
                self.candidate_unfavorable_human_neutral
            ),
            "candidate_unfavorable_human_favorable": (
                self.candidate_unfavorable_human_favorable
            ),
            "candidate_neutral_human_unfavorable": self.candidate_neutral_human_unfavorable,
            "candidate_neutral_human_neutral": self.candidate_neutral_human_neutral,
            "candidate_neutral_human_favorable": self.candidate_neutral_human_favorable,
            "candidate_favorable_human_unfavorable": (
                self.candidate_favorable_human_unfavorable
            ),
            "candidate_favorable_human_neutral": self.candidate_favorable_human_neutral,
            "candidate_favorable_human_favorable": (
                self.candidate_favorable_human_favorable
            ),
        }


@dataclass(frozen=True, slots=True)
class EvaluationLifecycleSummary:
    """Separate execution and coverage counts, never analytical quality."""

    total_items: int
    candidate_successes: int
    candidate_abstentions: int
    candidate_failures: int
    items_with_sufficient_reference_coverage: int
    items_with_insufficient_reference_coverage: int
    items_with_described_correspondence: int
    human_directional_responses_described: int
    human_abstentions_preserved: int
    notes: str = (
        "Lifecycle information only. These counts describe candidate execution, "
        "reference coverage, and bounded correspondence availability. They are not "
        "accuracy, a pass rate, candidate quality, or population evidence."
    )

    def __post_init__(self) -> None:
        values = (
            self.total_items,
            self.candidate_successes,
            self.candidate_abstentions,
            self.candidate_failures,
            self.items_with_sufficient_reference_coverage,
            self.items_with_insufficient_reference_coverage,
            self.items_with_described_correspondence,
            self.human_directional_responses_described,
            self.human_abstentions_preserved,
        )
        if any(isinstance(value, bool) or value < 0 for value in values):
            raise CandidateReferenceEvaluationError(
                "evaluation lifecycle counts must be non-negative integers"
            )
        if (
            self.candidate_successes
            + self.candidate_abstentions
            + self.candidate_failures
            != self.total_items
        ):
            raise CandidateReferenceEvaluationError(
                "candidate result counts must partition the evaluation corpus"
            )
        if (
            self.items_with_sufficient_reference_coverage
            + self.items_with_insufficient_reference_coverage
            != self.total_items
        ):
            raise CandidateReferenceEvaluationError(
                "human coverage counts must partition the evaluation corpus"
            )


@dataclass(frozen=True, slots=True)
class CandidateReferenceEvaluationCompletion:
    """Manifest-last completion for one verified descriptive evaluation."""

    completion_id: str
    evaluation_id: str
    evaluation_version: str
    record_type: str
    status: str
    plan_ref: StoredArtifactRef
    protocol_ref: StoredArtifactRef
    eligibility_ref: StoredArtifactRef
    synthesis_completion_ref: StoredArtifactRef
    synthesis_binding_ref: StoredArtifactRef
    candidate_result_refs: tuple[StoredArtifactRef, ...]
    item_evaluation_refs: tuple[StoredArtifactRef, ...]
    contingency_ref: StoredArtifactRef
    lifecycle_ref: StoredArtifactRef
    lifecycle: EvaluationLifecycleSummary
    candidate_lifecycle_status: str
    synthetic_test_fixture: bool
    non_claims: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.evaluation_version != EVALUATION_VERSION:
            raise CandidateReferenceEvaluationError("unsupported completion version")
        if self.record_type != EVALUATION_RECORD_TYPE:
            raise CandidateReferenceEvaluationError("unsupported completion record type")
        if self.status != "verified":
            raise CandidateReferenceEvaluationError("evaluation completion must be verified")
        if self.candidate_lifecycle_status != REQUIRED_CANDIDATE_STATUS:
            raise CandidateReferenceEvaluationError(
                "evaluation may not advance the candidate lifecycle"
            )
        if len(self.candidate_result_refs) != self.lifecycle.total_items:
            raise CandidateReferenceEvaluationError(
                "one candidate result reference is required per corpus item"
            )
        if len(self.item_evaluation_refs) != self.lifecycle.total_items:
            raise CandidateReferenceEvaluationError(
                "one item evaluation reference is required per corpus item"
            )
        expected_non_claims = (
            (*EVALUATION_NON_CLAIMS, FIXTURE_NON_CLAIM)
            if self.synthetic_test_fixture
            else EVALUATION_NON_CLAIMS
        )
        if self.non_claims != expected_non_claims:
            raise CandidateReferenceEvaluationError(
                "completion must preserve the exact declared non-claims"
            )


@dataclass(frozen=True, slots=True)
class VerifiedCandidateReferenceEvaluation:
    """Returned only after every evaluation and source artifact re-verifies."""

    evaluation_version: str
    artifact_directory: Path
    protocol: CandidateReferenceEvaluationProtocol
    eligibility: CandidateEvaluationEligibility
    plan: CandidateReferenceEvaluationPlan
    plan_ref: StoredArtifactRef
    items: tuple[CandidateReferenceItemEvaluation, ...]
    contingency: DirectionalContingency
    lifecycle: EvaluationLifecycleSummary
    completion: CandidateReferenceEvaluationCompletion
    completion_ref: StoredArtifactRef
    markdown: str

    def __post_init__(self) -> None:
        if self.evaluation_version != EVALUATION_VERSION:
            raise CandidateReferenceEvaluationError("unsupported verified receipt version")


@dataclass(frozen=True, slots=True)
class CandidateReferenceEvaluationRequest:
    """Declared inputs for one production candidate-reference evaluation."""

    workspace: Path
    human_workspace: Path
    run_token: str
    started_at: datetime
    evaluation_protocol_path: Path = DEFAULT_EVALUATION_PROTOCOL
    real_registry_path: Path = DEFAULT_REAL_CANDIDATE_REGISTRY
    annotation_protocol_path: Path = DEFAULT_ANNOTATION_PROTOCOL
    synthesis_protocol_path: Path = DEFAULT_SYNTHESIS_PROTOCOL
    corpus_path: Path = DEFAULT_CORPUS

    def __post_init__(self) -> None:
        if _RUN_TOKEN_PATTERN.fullmatch(self.run_token) is None:
            raise CandidateReferenceEvaluationError(
                "run_token must contain 8-64 lowercase letters, digits, or hyphens"
            )
        if self.started_at.tzinfo is None:
            raise CandidateReferenceEvaluationError("started_at must include a timezone")


def _verify_synthesis_receipt(
    receipt: VerifiedSynthesisReceipt,
    *,
    bindings: RepositoryEvaluationBindings,
    human_workspace: Path,
    allow_test_fixtures: bool,
) -> None:
    """Reverify the synthesis completion and its source collection fixture boundary."""

    if receipt.protocol.protocol_id != bindings.synthesis_protocol.protocol_id:
        raise CandidateReferenceEvaluationError("synthesis protocol ID mismatch")
    if receipt.protocol.protocol_version != bindings.synthesis_protocol.protocol_version:
        raise CandidateReferenceEvaluationError("synthesis protocol version mismatch")
    if receipt.protocol.artifact_hash != bindings.synthesis_protocol.artifact_hash:
        raise CandidateReferenceEvaluationError("synthesis protocol hash mismatch")
    if receipt.plan.annotation_protocol_id != bindings.annotation_protocol.protocol_id:
        raise CandidateReferenceEvaluationError("annotation protocol ID mismatch")
    if receipt.plan.annotation_protocol_version != bindings.annotation_protocol.protocol_version:
        raise CandidateReferenceEvaluationError("annotation protocol version mismatch")
    if receipt.plan.annotation_protocol_hash != bindings.annotation_protocol.artifact_hash:
        raise CandidateReferenceEvaluationError("annotation protocol hash mismatch")
    if receipt.plan.corpus_id != bindings.corpus.corpus_id:
        raise CandidateReferenceEvaluationError("human-reference corpus ID mismatch")
    if receipt.plan.corpus_version != bindings.corpus.corpus_version:
        raise CandidateReferenceEvaluationError("human-reference corpus version mismatch")
    if receipt.plan.corpus_hash != bindings.corpus.artifact_hash:
        raise CandidateReferenceEvaluationError("human-reference corpus hash mismatch")
    if receipt.plan.item_ids != bindings.corpus.item_ids:
        raise CandidateReferenceEvaluationError(
            "human synthesis item order differs from the frozen evaluation corpus"
        )
    if receipt.completion.candidate_lifecycle_status != REQUIRED_CANDIDATE_STATUS:
        raise CandidateReferenceEvaluationError(
            "human synthesis unexpectedly changed candidate lifecycle status"
        )

    synthesis_store = FileSystemArtifactStore(receipt.artifact_directory)
    expected_completion = serialize_artifact(
        receipt.completion.completion_id,
        receipt.completion,
    )
    stored_completion = synthesis_store.get(
        receipt.completion_ref.artifact_id,
        expected_hash=receipt.completion_ref.artifact_hash,
    )
    if stored_completion.payload != expected_completion.payload:
        raise ArtifactIntegrityError(
            "stored human-reference synthesis completion differs from the receipt"
        )
    for reference in (
        receipt.plan_ref,
        receipt.completion.receipt_manifest_ref,
        receipt.completion.lifecycle_ref,
        *receipt.completion.resolution_refs,
        *receipt.completion.item_synthesis_refs,
    ):
        synthesis_store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    if len(receipt.items) != len(receipt.completion.item_synthesis_refs):
        raise CandidateReferenceEvaluationError(
            "human synthesis receipt lacks one item reference per item"
        )
    for item, reference in zip(
        receipt.items,
        receipt.completion.item_synthesis_refs,
        strict=True,
    ):
        expected_item = serialize_artifact(reference.artifact_id, item)
        stored_item = synthesis_store.get(
            reference.artifact_id,
            expected_hash=reference.artifact_hash,
        )
        if stored_item.payload != expected_item.payload:
            raise ArtifactIntegrityError(
                f"stored human synthesis item {item.item_id!r} differs from the receipt"
            )

    for included in receipt.included:
        store = find_collection_store(
            human_workspace,
            included.completion_ref.artifact_id,
        )
        stored = store.get(
            included.completion_ref.artifact_id,
            expected_hash=included.completion_ref.artifact_hash,
        )
        if stored.artifact_hash != included.completion_ref.artifact_hash:
            raise ArtifactIntegrityError("human collection receipt hash changed")
        fixture = is_test_fixture_collection(store, assignment_id=included.assignment_id)
        if fixture and not allow_test_fixtures:
            raise CandidateReferenceEvaluationError(
                f"collection {included.assignment_id!r} is marked as a synthetic "
                "test fixture and may not enter a production evaluation"
            )
        if allow_test_fixtures and not fixture:
            raise CandidateReferenceEvaluationError(
                "the test-only evaluation entry point requires every included "
                "collection to be explicitly marked as a synthetic fixture"
            )


def _authorize_candidate(
    *,
    protocol: CandidateReferenceEvaluationProtocol,
    registry_document: Mapping[str, object],
    bindings: RepositoryEvaluationBindings,
    adapter: VaderSentimentAdapter,
) -> tuple[CandidateRegistrySnapshot, CandidateEvaluationEligibility]:
    registry = CandidateRegistrySnapshot.from_document(registry_document)
    if (
        registry.registry_id != protocol.candidate_registry_id
        or registry.registry_version != protocol.candidate_registry_version
        or registry.artifact_hash != bindings.registry_hash
    ):
        raise CandidateReferenceEvaluationError(
            "candidate registry identity differs from the preregistered binding"
        )
    if registry.status is not RegistryLifecycle.ACCEPTED:
        raise CandidateReferenceEvaluationError(
            "candidate registry must be accepted before evaluation"
        )
    record = registry.candidate(protocol.candidate_id)
    if record is None:
        raise CandidateReferenceEvaluationError(
            f"candidate {protocol.candidate_id!r} is absent from the registry"
        )
    reasons = candidate_authorization_reasons(
        record,
        analyzer_id=adapter.identity.analyzer_id,
        dimension_id=adapter.dimension_id,
        implementation_revision=adapter.implementation_revision,
    )
    if reasons:
        raise CandidateReferenceEvaluationError(
            "candidate eligibility failed: " + "; ".join(reasons)
        )
    binding: RealCandidateBinding = real_candidate_binding(
        registry_document,
        protocol.candidate_id,
    )
    if binding != bindings.candidate:
        raise CandidateReferenceEvaluationError(
            "candidate binding differs from the preregistered repository binding"
        )
    if adapter.package_version != binding.package.version:
        raise CandidateReferenceEvaluationError(
            "installed candidate package version differs from the frozen binding"
        )
    if adapter.implementation_revision != protocol.adapter_revision:
        raise CandidateReferenceEvaluationError(
            "loaded adapter revision differs from the frozen protocol"
        )
    configuration_hash = canonical_sha256(adapter.execution_configuration)
    if configuration_hash != protocol.configuration_hash:
        raise CandidateReferenceEvaluationError(
            "loaded candidate configuration differs from the frozen protocol"
        )
    if adapter.dimension_id != protocol.candidate_dimension_id:
        raise CandidateReferenceEvaluationError(
            "loaded candidate dimension differs from the frozen protocol"
        )
    if adapter.dimension_version != protocol.candidate_dimension_version:
        raise CandidateReferenceEvaluationError(
            "loaded candidate dimension version differs from the frozen protocol"
        )
    return registry, CandidateEvaluationEligibility(
        candidate_registry_ref=registry.reference(),
        candidate_id=record.candidate_id,
        analyzer_id=adapter.identity.analyzer_id,
        dimension_id=adapter.dimension_id,
        dimension_version=adapter.dimension_version,
        adapter_revision=adapter.implementation_revision,
        package_distribution=binding.package.distribution,
        package_version=binding.package.version,
        configuration_hash=configuration_hash,
        lifecycle_status=record.status.value,
        license_review_status=record.license_status.value,
        user_facing_execution_permitted=(
            binding.execution_boundary.user_facing_execution_permitted
        ),
    )


def _candidate_input(item: ItemSynthesis, corpus: EvaluationCorpus) -> ContentItem:
    source = corpus.item(item.item_id)
    if source.content_hash != item.content_hash or source.text != item.text:
        raise CandidateReferenceEvaluationError(
            f"human synthesis item {item.item_id!r} differs from the frozen corpus"
        )
    return ContentItem(
        content_id=item.item_id,
        text=item.text,
        source_type=SourceType(source.source_type),
        content_hash=item.content_hash,
        language=source.language,
        extraction_ref=(
            f"human-reference:{corpus.corpus_id}:{corpus.corpus_version}:"
            f"{item.item_id}:{item.content_hash}"
        ),
    )


def _preserved_outputs(result: ModelResult) -> tuple[PreservedCandidateOutput, ...]:
    if result.status is not ResultStatus.SUCCESS:
        return ()
    scores = {item.key: item for item in result.normalized_scores}
    if tuple(scores) != PRESERVED_OUTPUT_KEYS:
        raise CandidateReferenceEvaluationError(
            "successful VADER result did not preserve all four outputs in exact order"
        )
    return tuple(
        PreservedCandidateOutput(
            key=key,
            value=scores[key].value,
            lower_bound=scores[key].lower_bound,
            upper_bound=scores[key].upper_bound,
        )
        for key in PRESERVED_OUTPUT_KEYS
    )


def _compound(result: ModelResult) -> float:
    value = result.raw_output.get("compound")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CandidateReferenceEvaluationError(
            "successful candidate result requires a numeric compound output"
        )
    return float(value)


def _item_evaluation(
    *,
    position: int,
    item: ItemSynthesis,
    item_ref: StoredArtifactRef,
    result: ModelResult,
    result_ref: StoredArtifactRef,
    protocol: CandidateReferenceEvaluationProtocol,
) -> CandidateReferenceItemEvaluation:
    original = dict(item.valence_distribution.counts)
    human = protocol.collapse_human_distribution(original)
    candidate_bucket: DirectionBucket | None = None
    correspondence: DirectionalCorrespondence | None = None
    reasons: tuple[str, ...] = ()

    if result.status is ResultStatus.ABSTAINED:
        status = ItemEvaluationStatus.CANDIDATE_ABSTAINED
        reasons = tuple(result.confidence.system_abstention.reasons) or (
            "candidate abstained without a more specific reason",
        )
    elif result.status is ResultStatus.FAILED:
        status = ItemEvaluationStatus.CANDIDATE_FAILED
        reasons = result.errors or ("candidate execution failed",)
    elif result.status is not ResultStatus.SUCCESS:
        raise CandidateReferenceEvaluationError(
            f"unsupported candidate result status {result.status.value!r}"
        )
    elif item.coverage_status != protocol.required_item_coverage_status:
        status = ItemEvaluationStatus.INSUFFICIENT_REFERENCE_COVERAGE
        reasons = (
            f"human reference coverage is {item.coverage_status!r}, not "
            f"{protocol.required_item_coverage_status!r}",
        )
        candidate_bucket = protocol.classify_compound(_compound(result))
    else:
        candidate_bucket = protocol.classify_compound(_compound(result))
        correspondence = protocol.describe_correspondence(candidate_bucket, human)
        status = ItemEvaluationStatus.DESCRIBED

    return CandidateReferenceItemEvaluation(
        position=position,
        item_id=item.item_id,
        content_hash=item.content_hash,
        text=item.text,
        human_coverage_status=item.coverage_status,
        original_human_distribution=original,
        human_directional_distribution=human,
        candidate_result_status=result.status.value,
        candidate_raw_output=dict(result.raw_output),
        candidate_outputs=_preserved_outputs(result),
        candidate_bucket=candidate_bucket,
        correspondence=correspondence,
        evaluation_status=status,
        exclusion_reasons=reasons,
        candidate_result_ref=result_ref,
        human_synthesis_ref=item_ref,
    )


def _contingency(
    items: Sequence[CandidateReferenceItemEvaluation],
) -> DirectionalContingency:
    counts = {
        (candidate, human): 0
        for candidate in CANDIDATE_BUCKETS
        for human in CANDIDATE_BUCKETS
    }
    for item in items:
        if item.evaluation_status is not ItemEvaluationStatus.DESCRIBED:
            continue
        candidate_bucket = item.candidate_bucket
        if candidate_bucket is None or candidate_bucket is DirectionBucket.ABSTENTION:
            raise CandidateReferenceEvaluationError(
                "described item is missing its candidate direction"
            )
        human = item.human_directional_distribution
        counts[(candidate_bucket, DirectionBucket.UNFAVORABLE)] += human.unfavorable
        counts[(candidate_bucket, DirectionBucket.NEUTRAL)] += human.neutral
        counts[(candidate_bucket, DirectionBucket.FAVORABLE)] += human.favorable

    return DirectionalContingency(
        candidate_unfavorable_human_unfavorable=counts[
            (DirectionBucket.UNFAVORABLE, DirectionBucket.UNFAVORABLE)
        ],
        candidate_unfavorable_human_neutral=counts[
            (DirectionBucket.UNFAVORABLE, DirectionBucket.NEUTRAL)
        ],
        candidate_unfavorable_human_favorable=counts[
            (DirectionBucket.UNFAVORABLE, DirectionBucket.FAVORABLE)
        ],
        candidate_neutral_human_unfavorable=counts[
            (DirectionBucket.NEUTRAL, DirectionBucket.UNFAVORABLE)
        ],
        candidate_neutral_human_neutral=counts[
            (DirectionBucket.NEUTRAL, DirectionBucket.NEUTRAL)
        ],
        candidate_neutral_human_favorable=counts[
            (DirectionBucket.NEUTRAL, DirectionBucket.FAVORABLE)
        ],
        candidate_favorable_human_unfavorable=counts[
            (DirectionBucket.FAVORABLE, DirectionBucket.UNFAVORABLE)
        ],
        candidate_favorable_human_neutral=counts[
            (DirectionBucket.FAVORABLE, DirectionBucket.NEUTRAL)
        ],
        candidate_favorable_human_favorable=counts[
            (DirectionBucket.FAVORABLE, DirectionBucket.FAVORABLE)
        ],
        directional_denominator=sum(counts.values()),
    )


def _lifecycle(
    items: Sequence[CandidateReferenceItemEvaluation],
) -> EvaluationLifecycleSummary:
    described = [
        item for item in items if item.evaluation_status is ItemEvaluationStatus.DESCRIBED
    ]
    return EvaluationLifecycleSummary(
        total_items=len(items),
        candidate_successes=sum(
            1 for item in items if item.candidate_result_status == ResultStatus.SUCCESS.value
        ),
        candidate_abstentions=sum(
            1
            for item in items
            if item.candidate_result_status == ResultStatus.ABSTAINED.value
        ),
        candidate_failures=sum(
            1 for item in items if item.candidate_result_status == ResultStatus.FAILED.value
        ),
        items_with_sufficient_reference_coverage=sum(
            1 for item in items if item.human_coverage_status == SUFFICIENT_COVERAGE
        ),
        items_with_insufficient_reference_coverage=sum(
            1 for item in items if item.human_coverage_status == INSUFFICIENT_COVERAGE
        ),
        items_with_described_correspondence=len(described),
        human_directional_responses_described=sum(
            item.human_directional_distribution.directional_denominator
            for item in described
        ),
        human_abstentions_preserved=sum(
            item.human_directional_distribution.abstention for item in items
        ),
    )


def _verify_evaluation_store(
    *,
    store: FileSystemArtifactStore,
    completion: CandidateReferenceEvaluationCompletion,
    completion_ref: StoredArtifactRef,
    plan: CandidateReferenceEvaluationPlan,
    plan_ref: StoredArtifactRef,
    items: tuple[CandidateReferenceItemEvaluation, ...],
) -> None:
    expected_completion = serialize_artifact(completion.completion_id, completion)
    stored_completion = store.get(
        completion_ref.artifact_id,
        expected_hash=completion_ref.artifact_hash,
    )
    if stored_completion.payload != expected_completion.payload:
        raise ArtifactIntegrityError(
            "stored candidate-reference completion differs from the expected manifest"
        )
    expected_plan = serialize_artifact(plan.evaluation_id, plan)
    stored_plan = store.get(plan_ref.artifact_id, expected_hash=plan_ref.artifact_hash)
    if stored_plan.payload != expected_plan.payload:
        raise ArtifactIntegrityError(
            "stored candidate-reference plan differs from the expected plan"
        )
    for reference in (
        completion.protocol_ref,
        completion.eligibility_ref,
        completion.synthesis_binding_ref,
        completion.contingency_ref,
        completion.lifecycle_ref,
        *completion.candidate_result_refs,
        *completion.item_evaluation_refs,
    ):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
    for item, reference in zip(items, completion.item_evaluation_refs, strict=True):
        expected = serialize_artifact(reference.artifact_id, item)
        stored = store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        if stored.payload != expected.payload:
            raise ArtifactIntegrityError(
                f"stored item evaluation {item.item_id!r} differs from the receipt"
            )


def _run_candidate_reference_evaluation(
    request: CandidateReferenceEvaluationRequest,
    *,
    synthesis: VerifiedSynthesisReceipt,
    adapter: VaderSentimentAdapter | None,
    synthetic_test_fixture: bool,
) -> VerifiedCandidateReferenceEvaluation:
    protocol = load_default_evaluation_protocol(request.evaluation_protocol_path)
    bindings = validate_repository_bindings(
        protocol,
        registry_path=request.real_registry_path,
        annotation_protocol_path=request.annotation_protocol_path,
        synthesis_protocol_path=request.synthesis_protocol_path,
        corpus_path=request.corpus_path,
    )
    _verify_synthesis_receipt(
        synthesis,
        bindings=bindings,
        human_workspace=request.human_workspace,
        allow_test_fixtures=synthetic_test_fixture,
    )
    loaded_adapter = adapter or load_vader_sentiment_adapter()
    registry_document = _load_document(
        request.real_registry_path,
        "real candidate registry",
    )
    registry, eligibility = _authorize_candidate(
        protocol=protocol,
        registry_document=registry_document,
        bindings=bindings,
        adapter=loaded_adapter,
    )

    created_at = _iso(request.started_at)
    evaluation_id = f"evaluation.vader-human-reference.{request.run_token}"
    non_claims = (
        (*EVALUATION_NON_CLAIMS, FIXTURE_NON_CLAIM)
        if synthetic_test_fixture
        else EVALUATION_NON_CLAIMS
    )
    plan = CandidateReferenceEvaluationPlan(
        evaluation_id=evaluation_id,
        evaluation_version=EVALUATION_VERSION,
        record_type=EVALUATION_RECORD_TYPE,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_hash=protocol.artifact_hash,
        candidate_registry_ref=registry.reference(),
        candidate_id=eligibility.candidate_id,
        analyzer_id=eligibility.analyzer_id,
        adapter_revision=eligibility.adapter_revision,
        configuration_hash=eligibility.configuration_hash,
        annotation_protocol_id=bindings.annotation_protocol.protocol_id,
        annotation_protocol_version=bindings.annotation_protocol.protocol_version,
        synthesis_protocol_id=bindings.synthesis_protocol.protocol_id,
        synthesis_protocol_version=bindings.synthesis_protocol.protocol_version,
        synthesis_completion_ref=synthesis.completion_ref,
        corpus_id=bindings.corpus.corpus_id,
        corpus_version=bindings.corpus.corpus_version,
        corpus_hash=bindings.corpus.artifact_hash,
        dimension_id=protocol.candidate_dimension_id,
        dimension_version=protocol.candidate_dimension_version,
        item_ids=bindings.corpus.item_ids,
        synthetic_test_fixture=synthetic_test_fixture,
        non_claims=non_claims,
        created_at=created_at,
    )

    artifact_directory = request.workspace / request.run_token / "artifacts"
    store = FileSystemArtifactStore(artifact_directory)
    protocol_ref = store.append(
        serialize_artifact(
            f"{protocol.protocol_id}:{protocol.protocol_version}",
            json.loads(protocol.canonical_payload.decode("utf-8")),
        )
    )
    plan_ref = store.append(serialize_artifact(plan.evaluation_id, plan))
    eligibility_ref = store.append(
        serialize_artifact(f"{evaluation_id}:candidate-eligibility", eligibility)
    )
    synthesis_binding_ref = store.append(
        serialize_artifact(
            f"{evaluation_id}:human-synthesis-binding",
            {
                "synthesis_completion_ref": _ref_document(synthesis.completion_ref),
                "synthesis_plan_ref": _ref_document(synthesis.plan_ref),
                "synthetic_test_fixture": synthetic_test_fixture,
            },
        )
    )

    if len(synthesis.items) != len(bindings.corpus.items):
        raise CandidateReferenceEvaluationError(
            "human synthesis item count differs from the frozen evaluation corpus"
        )
    if len(synthesis.completion.item_synthesis_refs) != len(synthesis.items):
        raise CandidateReferenceEvaluationError(
            "human synthesis completion lacks one item reference per item"
        )

    result_refs: list[StoredArtifactRef] = []
    evaluations: list[CandidateReferenceItemEvaluation] = []
    evaluation_refs: list[StoredArtifactRef] = []
    for position, (human_item, human_ref) in enumerate(
        zip(
            synthesis.items,
            synthesis.completion.item_synthesis_refs,
            strict=True,
        )
    ):
        expected_item = bindings.corpus.items[position]
        if human_item.item_id != expected_item.item_id:
            raise CandidateReferenceEvaluationError(
                "human synthesis item order differs from the frozen corpus"
            )
        candidate_input = _candidate_input(human_item, bindings.corpus)
        result = loaded_adapter.analyze(candidate_input)
        if result.content_id != human_item.item_id:
            raise CandidateReferenceEvaluationError(
                "candidate result content identity differs from the frozen item"
            )
        if result.dimension_id != protocol.candidate_dimension_id:
            raise CandidateReferenceEvaluationError(
                "candidate result dimension differs from the frozen protocol"
            )
        result_ref = store.append(
            serialize_artifact(
                f"{evaluation_id}:{human_item.item_id}:candidate-result",
                result,
            )
        )
        item_evaluation = _item_evaluation(
            position=position,
            item=human_item,
            item_ref=human_ref,
            result=result,
            result_ref=result_ref,
            protocol=protocol,
        )
        item_ref = store.append(
            serialize_artifact(
                f"{evaluation_id}:{human_item.item_id}:evaluation",
                item_evaluation,
            )
        )
        result_refs.append(result_ref)
        evaluations.append(item_evaluation)
        evaluation_refs.append(item_ref)

    evaluated_items = tuple(evaluations)
    contingency = _contingency(evaluated_items)
    lifecycle = _lifecycle(evaluated_items)
    contingency_ref = store.append(
        serialize_artifact(f"{evaluation_id}:directional-contingency", contingency)
    )
    lifecycle_ref = store.append(
        serialize_artifact(f"{evaluation_id}:lifecycle", lifecycle)
    )
    completion = CandidateReferenceEvaluationCompletion(
        completion_id=f"{evaluation_id}:completion",
        evaluation_id=evaluation_id,
        evaluation_version=EVALUATION_VERSION,
        record_type=EVALUATION_RECORD_TYPE,
        status="verified",
        plan_ref=plan_ref,
        protocol_ref=protocol_ref,
        eligibility_ref=eligibility_ref,
        synthesis_completion_ref=synthesis.completion_ref,
        synthesis_binding_ref=synthesis_binding_ref,
        candidate_result_refs=tuple(result_refs),
        item_evaluation_refs=tuple(evaluation_refs),
        contingency_ref=contingency_ref,
        lifecycle_ref=lifecycle_ref,
        lifecycle=lifecycle,
        candidate_lifecycle_status=eligibility.lifecycle_status,
        synthetic_test_fixture=synthetic_test_fixture,
        non_claims=non_claims,
        completed_at=created_at,
    )
    completion_ref = store.append(
        serialize_artifact(completion.completion_id, completion)
    )
    _verify_evaluation_store(
        store=store,
        completion=completion,
        completion_ref=completion_ref,
        plan=plan,
        plan_ref=plan_ref,
        items=evaluated_items,
    )
    markdown = render_candidate_reference_evaluation_markdown(
        protocol=protocol,
        eligibility=eligibility,
        plan=plan,
        items=evaluated_items,
        contingency=contingency,
        lifecycle=lifecycle,
        completion=completion,
        completion_ref=completion_ref,
    )
    return VerifiedCandidateReferenceEvaluation(
        evaluation_version=EVALUATION_VERSION,
        artifact_directory=artifact_directory,
        protocol=protocol,
        eligibility=eligibility,
        plan=plan,
        plan_ref=plan_ref,
        items=evaluated_items,
        contingency=contingency,
        lifecycle=lifecycle,
        completion=completion,
        completion_ref=completion_ref,
        markdown=markdown,
    )


def run_candidate_reference_evaluation(
    request: CandidateReferenceEvaluationRequest,
    *,
    synthesis: VerifiedSynthesisReceipt,
) -> VerifiedCandidateReferenceEvaluation:
    """Run the production evaluation, refusing every synthetic fixture collection."""

    return _run_candidate_reference_evaluation(
        request,
        synthesis=synthesis,
        adapter=None,
        synthetic_test_fixture=False,
    )


def run_candidate_reference_evaluation_with_test_fixtures(
    request: CandidateReferenceEvaluationRequest,
    *,
    synthesis: VerifiedSynthesisReceipt,
    adapter: VaderSentimentAdapter,
) -> VerifiedCandidateReferenceEvaluation:
    """Test-only entry point requiring explicit fixture markers and visible tagging."""

    return _run_candidate_reference_evaluation(
        request,
        synthesis=synthesis,
        adapter=adapter,
        synthetic_test_fixture=True,
    )


def _format_number(value: float) -> str:
    return f"{value:.4f}"


def render_candidate_reference_evaluation_markdown(
    *,
    protocol: CandidateReferenceEvaluationProtocol,
    eligibility: CandidateEvaluationEligibility,
    plan: CandidateReferenceEvaluationPlan,
    items: tuple[CandidateReferenceItemEvaluation, ...],
    contingency: DirectionalContingency,
    lifecycle: EvaluationLifecycleSummary,
    completion: CandidateReferenceEvaluationCompletion,
    completion_ref: StoredArtifactRef,
) -> str:
    """Render a deterministic research report from reverified canonical artifacts."""

    title = "# VADER-to-human-reference descriptive evaluation (research only)"
    lines: list[str] = [
        title,
        "",
        "Human-reference judgments are not ground truth. Candidate correspondence "
        "with them is not correctness.",
        "",
    ]
    if plan.synthetic_test_fixture:
        lines.extend(
            [
                "> **SYNTHETIC TEST FIXTURE — NOT HUMAN RESEARCH EVIDENCE.**",
                ">",
                f"> {FIXTURE_NON_CLAIM}",
                "",
            ]
        )
    lines.extend(
        [
            "## 1. Frozen protocol and exact identities",
            "",
            f"- Evaluation contract: `{plan.evaluation_version}`",
            f"- Evaluation ID: `{plan.evaluation_id}`",
            f"- Preregistered protocol: `{plan.protocol_id}` @ `{plan.protocol_version}`",
            f"- Protocol hash: `{plan.protocol_hash}`",
            f"- Candidate registry: `{plan.candidate_registry_ref.artifact_id}` @ "
            f"`{plan.candidate_registry_ref.artifact_version}`",
            f"- Candidate registry hash: `{plan.candidate_registry_ref.artifact_hash}`",
            f"- Candidate: `{eligibility.candidate_id}`",
            f"- Analyzer: `{eligibility.analyzer_id}`",
            f"- Distribution: `{eligibility.package_distribution}=="
            f"{eligibility.package_version}`",
            f"- Adapter revision: `{eligibility.adapter_revision}`",
            f"- Configuration hash: `{eligibility.configuration_hash}`",
            f"- Candidate lifecycle: `{completion.candidate_lifecycle_status}` "
            "(unchanged by this evaluation)",
            f"- License review: `{eligibility.license_review_status}`",
            "- User-facing execution permitted: no",
            f"- Annotation protocol: `{plan.annotation_protocol_id}` @ "
            f"`{plan.annotation_protocol_version}`",
            f"- Synthesis protocol: `{plan.synthesis_protocol_id}` @ "
            f"`{plan.synthesis_protocol_version}`",
            f"- Synthesis completion: `{plan.synthesis_completion_ref.artifact_id}` "
            f"(`{plan.synthesis_completion_ref.artifact_hash}`)",
            f"- Corpus: `{plan.corpus_id}` @ `{plan.corpus_version}`",
            f"- Corpus hash: `{plan.corpus_hash}`",
            f"- Dimension: `{plan.dimension_id}` @ `{plan.dimension_version}`",
            "",
            "The protocol, thresholds, mappings, permitted descriptions, and "
            "prohibited claims were frozen before candidate outputs were paired with "
            "human-reference synthesis.",
            "",
            "## 2. Lifecycle and coverage",
            "",
            f"- Total frozen items: {lifecycle.total_items}",
            f"- Candidate successes: {lifecycle.candidate_successes}",
            f"- Candidate abstentions: {lifecycle.candidate_abstentions}",
            f"- Candidate failures: {lifecycle.candidate_failures}",
            f"- Items with sufficient human-reference coverage: "
            f"{lifecycle.items_with_sufficient_reference_coverage}",
            f"- Items with insufficient human-reference coverage: "
            f"{lifecycle.items_with_insufficient_reference_coverage}",
            f"- Items with described correspondence: "
            f"{lifecycle.items_with_described_correspondence}",
            f"- Human directional responses described: "
            f"{lifecycle.human_directional_responses_described}",
            f"- Human abstentions preserved: {lifecycle.human_abstentions_preserved}",
            "",
            lifecycle.notes,
            "",
            "## 3. Per-item descriptive records",
            "",
            "Every original six-option human distribution remains visible. Candidate "
            "abstention, candidate failure, and insufficient human coverage are never "
            "forced into a directional correspondence.",
            "",
        ]
    )

    for item in items:
        lines.extend(
            [
                f"### {item.item_id} (position {item.position})",
                "",
                f"- Content hash: `{item.content_hash}`",
                f"- Human coverage: `{item.human_coverage_status}`",
                f"- Candidate result: `{item.candidate_result_status}`",
                f"- Evaluation status: `{item.evaluation_status.value}`",
                "",
                "Exact text:",
                "",
                f"> {item.text}",
                "",
                "Original human-reference distribution:",
                "",
                "| Response option | Count |",
                "| --- | --- |",
            ]
        )
        lines.extend(
            f"| `{label.value}` | {item.original_human_distribution[label.value]} |"
            for label in ValenceLabel
        )
        human = item.human_directional_distribution
        lines.extend(
            [
                "",
                "Derived directional counts, with abstention retained separately:",
                "",
                f"- Unfavorable: {human.unfavorable}",
                f"- Neutral: {human.neutral}",
                f"- Favorable: {human.favorable}",
                f"- Directional denominator: {human.directional_denominator}",
                f"- Human abstention: {human.abstention}",
                "",
            ]
        )
        if item.candidate_outputs:
            lines.extend(
                [
                    "Candidate outputs, preserved separately:",
                    "",
                    "| Output | Value | Lower bound | Upper bound |",
                    "| --- | --- | --- | --- |",
                ]
            )
            lines.extend(
                f"| `{output.key}` | {_format_number(output.value)} | "
                f"{_format_number(output.lower_bound)} | "
                f"{_format_number(output.upper_bound)} |"
                for output in item.candidate_outputs
            )
            lines.extend(
                [
                    "",
                    "`compound` is used only for the preregistered directional "
                    "partition. It is not confidence, probability, calibration, or "
                    "an overall CTRT score.",
                    "",
                ]
            )
        else:
            lines.extend(["No numeric candidate output was emitted.", ""])

        if item.correspondence is not None:
            correspondence = item.correspondence
            lines.extend(
                [
                    f"- Candidate directional bucket: "
                    f"`{correspondence.candidate_bucket.value}`",
                    f"- Same-direction human count: "
                    f"{correspondence.same_direction_count} of "
                    f"{correspondence.directional_denominator} non-abstaining responses",
                    f"- Human unfavorable count: {correspondence.unfavorable_count}",
                    f"- Human neutral count: {correspondence.neutral_count}",
                    f"- Human favorable count: {correspondence.favorable_count}",
                    f"- Human abstention count: "
                    f"{correspondence.human_abstention_count}",
                    "",
                    "The same-direction count is descriptive correspondence, not "
                    "accuracy and not proof that either response is correct.",
                    "",
                ]
            )
        else:
            lines.append("No directional correspondence was produced:")
            lines.extend(f"- {reason}" for reason in item.exclusion_reasons)
            lines.append("")
        lines.extend(
            [
                f"- Candidate result artifact: `{item.candidate_result_ref.artifact_id}` "
                f"(`{item.candidate_result_ref.artifact_hash}`)",
                f"- Human synthesis artifact: `{item.human_synthesis_ref.artifact_id}` "
                f"(`{item.human_synthesis_ref.artifact_hash}`)",
                "",
            ]
        )

    lines.extend(
        [
            "## 4. Candidate-direction by human-direction contingency counts",
            "",
            "Only items with a successful candidate direction and sufficient declared "
            "human-reference coverage enter this table. Counts are human responses, "
            "not item-level correct answers.",
            "",
            "| Candidate direction | Human unfavorable | Human neutral | "
            "Human favorable |",
            "| --- | ---: | ---: | ---: |",
            f"| Unfavorable | "
            f"{contingency.candidate_unfavorable_human_unfavorable} | "
            f"{contingency.candidate_unfavorable_human_neutral} | "
            f"{contingency.candidate_unfavorable_human_favorable} |",
            f"| Neutral | {contingency.candidate_neutral_human_unfavorable} | "
            f"{contingency.candidate_neutral_human_neutral} | "
            f"{contingency.candidate_neutral_human_favorable} |",
            f"| Favorable | {contingency.candidate_favorable_human_unfavorable} | "
            f"{contingency.candidate_favorable_human_neutral} | "
            f"{contingency.candidate_favorable_human_favorable} |",
            "",
            f"Preserved directional denominator: {contingency.directional_denominator}",
            "",
            "No accuracy, precision, recall, F1, correlation, significance test, "
            "confidence interval, majority human label, or merged score is computed.",
            "",
            "## 5. Immutable artifact references",
            "",
            f"- `evaluation-plan` → `{completion.plan_ref.artifact_id}` "
            f"(`{completion.plan_ref.artifact_hash}`)",
            f"- `evaluation-protocol` → `{completion.protocol_ref.artifact_id}` "
            f"(`{completion.protocol_ref.artifact_hash}`)",
            f"- `candidate-eligibility` → `{completion.eligibility_ref.artifact_id}` "
            f"(`{completion.eligibility_ref.artifact_hash}`)",
            f"- `human-synthesis-completion` → "
            f"`{completion.synthesis_completion_ref.artifact_id}` "
            f"(`{completion.synthesis_completion_ref.artifact_hash}`)",
            f"- `human-synthesis-binding` → "
            f"`{completion.synthesis_binding_ref.artifact_id}` "
            f"(`{completion.synthesis_binding_ref.artifact_hash}`)",
            f"- `directional-contingency` → `{completion.contingency_ref.artifact_id}` "
            f"(`{completion.contingency_ref.artifact_hash}`)",
            f"- `evaluation-lifecycle` → `{completion.lifecycle_ref.artifact_id}` "
            f"(`{completion.lifecycle_ref.artifact_hash}`)",
            f"- `evaluation-completion` → `{completion_ref.artifact_id}` "
            f"(`{completion_ref.artifact_hash}`)",
            f"- Candidate result artifacts: {len(completion.candidate_result_refs)}",
            f"- Item evaluation artifacts: {len(completion.item_evaluation_refs)}",
            "",
            "## 6. Interpretation boundary and non-claims",
            "",
        ]
    )
    lines.extend(f"- {claim}" for claim in completion.non_claims)
    lines.extend(
        [
            "",
            "This report does not create a candidate selection record. A separate, "
            "later governance decision would be required to change candidate status "
            "or authorize any domain-bounded product use.",
            "",
            f"Frozen protocol prohibited measures remain controlling: "
            f"{len(protocol.prohibited_measures)} declared prohibitions.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.candidate_reference_evaluation",
        description=(
            "RESEARCH ONLY. Run the preregistered VADER-to-human-reference "
            "descriptive evaluation. Human judgments are not ground truth and "
            "correspondence is not accuracy."
        ),
    )
    parser.add_argument(
        "--human-workspace",
        type=Path,
        default=Path(".ctrt") / "human-reference",
        help="Directory containing one append-only collection store per annotator.",
    )
    parser.add_argument(
        "--receipt",
        action="append",
        default=[],
        dest="receipts",
        required=True,
        help="Verified human collection receipt ID. Repeat once per annotator.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".ctrt") / "candidate-reference-evaluation",
        help="Directory containing one append-only artifact store per evaluation.",
    )
    parser.add_argument(
        "--run-token",
        required=True,
        help="Reproducible lowercase evaluation token, 8-64 characters.",
    )
    parser.add_argument("--output", type=Path, help="Optional Markdown report path.")
    parser.add_argument(
        "--evaluation-protocol",
        type=Path,
        default=DEFAULT_EVALUATION_PROTOCOL,
    )
    parser.add_argument(
        "--real-registry",
        type=Path,
        default=DEFAULT_REAL_CANDIDATE_REGISTRY,
    )
    parser.add_argument(
        "--annotation-protocol",
        type=Path,
        default=DEFAULT_ANNOTATION_PROTOCOL,
    )
    parser.add_argument(
        "--synthesis-protocol",
        type=Path,
        default=DEFAULT_SYNTHESIS_PROTOCOL,
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for production, non-fixture research evaluation."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    started_at = datetime.now(UTC)
    try:
        synthesis = run_human_reference_synthesis(
            workspace=arguments.human_workspace,
            completion_ids=tuple(arguments.receipts),
            synthesis_protocol_path=arguments.synthesis_protocol,
            annotation_protocol_path=arguments.annotation_protocol,
            corpus_path=arguments.corpus,
            created_at=started_at,
            output_directory=(
                arguments.workspace / arguments.run_token / "human-synthesis-artifacts"
            ),
        )
        receipt = run_candidate_reference_evaluation(
            CandidateReferenceEvaluationRequest(
                workspace=arguments.workspace,
                human_workspace=arguments.human_workspace,
                run_token=arguments.run_token,
                started_at=started_at,
                evaluation_protocol_path=arguments.evaluation_protocol,
                real_registry_path=arguments.real_registry,
                annotation_protocol_path=arguments.annotation_protocol,
                synthesis_protocol_path=arguments.synthesis_protocol,
                corpus_path=arguments.corpus,
            ),
            synthesis=synthesis,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"candidate-reference evaluation failed: {exc}\n")
        return 2

    if arguments.output is None:
        sys.stdout.write(receipt.markdown)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(receipt.markdown, encoding="utf-8")
        sys.stdout.write(f"Wrote evaluation report to {arguments.output}\n")
    sys.stderr.write(f"Artifact store: {receipt.artifact_directory}\n")
    sys.stderr.write(
        "Research only. Human-reference correspondence is not correctness.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EVALUATION_NON_CLAIMS",
    "EVALUATION_RECORD_TYPE",
    "EVALUATION_VERSION",
    "FIXTURE_NON_CLAIM",
    "CandidateEvaluationEligibility",
    "CandidateReferenceEvaluationCompletion",
    "CandidateReferenceEvaluationError",
    "CandidateReferenceEvaluationPlan",
    "CandidateReferenceEvaluationRequest",
    "CandidateReferenceItemEvaluation",
    "DirectionalContingency",
    "EvaluationLifecycleSummary",
    "ItemEvaluationStatus",
    "PreservedCandidateOutput",
    "VerifiedCandidateReferenceEvaluation",
    "main",
    "render_candidate_reference_evaluation_markdown",
    "run_candidate_reference_evaluation",
    "run_candidate_reference_evaluation_with_test_fixtures",
]
