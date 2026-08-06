"""Preregister a descriptive candidate-to-human-reference evaluation.

The protocol freezes candidate identity, human-reference identity, directional
mapping, permitted descriptions, and prohibited claims before candidate outputs
are paired with human-reference synthesis.

Human-reference judgments are not ground truth. Candidate correspondence with
them is not correctness. This module executes no analyzer, reads no annotation
collection, creates no evaluation result, and advances no candidate lifecycle.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from ctrt.human_reference_protocol import (
    AnnotationProtocol,
    EvaluationCorpus,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
)
from ctrt.human_reference_synthesis import (
    INSUFFICIENT_COVERAGE,
    SUFFICIENT_COVERAGE,
    SynthesisProtocol,
)
from ctrt.real_candidate_registry import (
    RealCandidateBinding,
    real_candidate_binding,
)
from ctrt.serialization import canonical_json_bytes
from ctrt.vader_adapter import (
    PRESERVED_OUTPUT_KEYS,
    VADER_ADAPTER_REVISION,
    VADER_ANALYZER_ID,
    VADER_CANDIDATE_ID,
    VADER_DISTRIBUTION,
    VADER_PINNED_VERSION,
    vader_configuration_hash,
)

EVALUATION_PROTOCOL_VERSION = "ctrt-candidate-reference-evaluation-protocol@0.1.0"
DEFAULT_PROTOCOL_ID = "protocol.vader-human-reference-evaluation"
DEFAULT_PROTOCOL_VERSION = "0.1.0"
DEFAULT_REGISTRY_ID = "registry.real-candidates"
DEFAULT_REGISTRY_VERSION = "0.1.0"
REQUIRED_CANDIDATE_STATUS = "eligible_for_evaluation"
REQUIRED_HUMAN_COVERAGE_STATUS = SUFFICIENT_COVERAGE


class CandidateReferenceProtocolError(ValueError):
    """Raised when the preregistered comparison protocol is not exact."""


class DirectionBucket(StrEnum):
    """Three directional buckets plus first-class human abstention."""

    UNFAVORABLE = "unfavorable"
    NEUTRAL = "neutral"
    FAVORABLE = "favorable"
    ABSTENTION = "abstention"


CANDIDATE_BUCKETS = (
    DirectionBucket.UNFAVORABLE,
    DirectionBucket.NEUTRAL,
    DirectionBucket.FAVORABLE,
)

EXPECTED_HUMAN_MAPPING: Mapping[str, DirectionBucket] = MappingProxyType(
    {
        ValenceLabel.STRONGLY_UNFAVORABLE.value: DirectionBucket.UNFAVORABLE,
        ValenceLabel.SOMEWHAT_UNFAVORABLE.value: DirectionBucket.UNFAVORABLE,
        ValenceLabel.NEITHER.value: DirectionBucket.NEUTRAL,
        ValenceLabel.SOMEWHAT_FAVORABLE.value: DirectionBucket.FAVORABLE,
        ValenceLabel.STRONGLY_FAVORABLE.value: DirectionBucket.FAVORABLE,
        ValenceLabel.CANNOT_DETERMINE.value: DirectionBucket.ABSTENTION,
    }
)

REQUIRED_NON_CLAIMS = (
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_EVALUATION_PROTOCOL = (
    _repo_root()
    / "docs"
    / "protocols"
    / "vader-human-reference-evaluation.v0.1.0.json"
)
DEFAULT_REAL_CANDIDATE_REGISTRY = (
    _repo_root() / "docs" / "candidates" / "real-registry.v0.1.0.json"
)
DEFAULT_ANNOTATION_PROTOCOL = (
    _repo_root()
    / "docs"
    / "protocols"
    / "human-reference-sentiment-valence.v0.1.0.json"
)
DEFAULT_SYNTHESIS_PROTOCOL = (
    _repo_root() / "docs" / "protocols" / "human-reference-synthesis.v0.1.0.json"
)
DEFAULT_CORPUS = (
    _repo_root() / "docs" / "corpora" / "human-reference-sentiment.v0.1.0.json"
)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CandidateReferenceProtocolError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise CandidateReferenceProtocolError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateReferenceProtocolError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise CandidateReferenceProtocolError(f"{field_name} must be a boolean")
    return value


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CandidateReferenceProtocolError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise CandidateReferenceProtocolError(f"{field_name} must be finite")
    return result


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CandidateReferenceProtocolError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise CandidateReferenceProtocolError(f"{field_name} must not contain duplicates")
    return result


def _load_document(path: Path, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateReferenceProtocolError(
            f"unable to read {field_name} from {path}"
        ) from exc
    return _mapping(value, field_name)


def _sha256(document: Mapping[str, object]) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(document)).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DirectionThreshold:
    """One immutable interval used to classify the VADER compound output."""

    bucket: DirectionBucket
    rule: str
    lower_bound: float
    lower_inclusive: bool
    upper_bound: float
    upper_inclusive: bool

    def __post_init__(self) -> None:
        if self.bucket is DirectionBucket.ABSTENTION:
            raise CandidateReferenceProtocolError(
                "candidate thresholds may not encode abstention as a number"
            )
        if not self.rule.strip():
            raise CandidateReferenceProtocolError("threshold rule must not be empty")
        if not math.isfinite(self.lower_bound) or not math.isfinite(self.upper_bound):
            raise CandidateReferenceProtocolError("threshold bounds must be finite")
        if self.lower_bound >= self.upper_bound:
            raise CandidateReferenceProtocolError(
                "threshold lower bound must be less than upper bound"
            )

    def contains(self, value: float) -> bool:
        """Return whether one finite compound value lies in this interval."""

        lower = value >= self.lower_bound if self.lower_inclusive else value > self.lower_bound
        upper = value <= self.upper_bound if self.upper_inclusive else value < self.upper_bound
        return lower and upper


@dataclass(frozen=True, slots=True)
class HumanDirectionalDistribution:
    """Derived directional counts that retain abstention as its own category."""

    unfavorable: int
    neutral: int
    favorable: int
    abstention: int

    def __post_init__(self) -> None:
        values = (self.unfavorable, self.neutral, self.favorable, self.abstention)
        if any(isinstance(value, bool) or value < 0 for value in values):
            raise CandidateReferenceProtocolError(
                "directional distribution counts must be non-negative integers"
            )

    @property
    def directional_denominator(self) -> int:
        """Return the non-abstaining denominator without hiding abstention."""

        return self.unfavorable + self.neutral + self.favorable

    @property
    def total_responses(self) -> int:
        """Return all responses, including abstention."""

        return self.directional_denominator + self.abstention

    def count(self, bucket: DirectionBucket) -> int:
        """Return the exact count for one declared bucket."""

        return {
            DirectionBucket.UNFAVORABLE: self.unfavorable,
            DirectionBucket.NEUTRAL: self.neutral,
            DirectionBucket.FAVORABLE: self.favorable,
            DirectionBucket.ABSTENTION: self.abstention,
        }[bucket]


@dataclass(frozen=True, slots=True)
class DirectionalCorrespondence:
    """Denominator-preserving item-level correspondence, never accuracy."""

    candidate_bucket: DirectionBucket
    same_direction_count: int
    unfavorable_count: int
    neutral_count: int
    favorable_count: int
    directional_denominator: int
    human_abstention_count: int

    def __post_init__(self) -> None:
        if self.candidate_bucket not in CANDIDATE_BUCKETS:
            raise CandidateReferenceProtocolError(
                "candidate correspondence requires a measured direction"
            )
        counts = (
            self.same_direction_count,
            self.unfavorable_count,
            self.neutral_count,
            self.favorable_count,
            self.directional_denominator,
            self.human_abstention_count,
        )
        if any(isinstance(value, bool) or value < 0 for value in counts):
            raise CandidateReferenceProtocolError(
                "correspondence counts must be non-negative integers"
            )
        if (
            self.unfavorable_count + self.neutral_count + self.favorable_count
            != self.directional_denominator
        ):
            raise CandidateReferenceProtocolError(
                "directional counts must equal their preserved denominator"
            )
        expected_same = {
            DirectionBucket.UNFAVORABLE: self.unfavorable_count,
            DirectionBucket.NEUTRAL: self.neutral_count,
            DirectionBucket.FAVORABLE: self.favorable_count,
        }[self.candidate_bucket]
        if self.same_direction_count != expected_same:
            raise CandidateReferenceProtocolError(
                "same-direction count must be derived from the exact candidate bucket"
            )


@dataclass(frozen=True, slots=True)
class CandidateReferenceEvaluationProtocol:
    """One frozen protocol binding exact candidate and human-reference identities."""

    protocol_id: str
    protocol_version: str
    purpose: str
    candidate_registry_id: str
    candidate_registry_version: str
    candidate_id: str
    required_candidate_status: str
    analyzer_id: str
    adapter_revision: str
    distribution: str
    distribution_version: str
    configuration_hash: str
    candidate_dimension_id: str
    candidate_dimension_version: str
    preserved_output_keys: tuple[str, ...]
    directional_output_key: str
    annotation_protocol_id: str
    annotation_protocol_version: str
    synthesis_protocol_id: str
    synthesis_protocol_version: str
    corpus_id: str
    corpus_version: str
    human_dimension_id: str
    human_dimension_version: str
    required_item_coverage_status: str
    thresholds: tuple[DirectionThreshold, ...]
    human_bucket_mapping: Mapping[str, DirectionBucket]
    permitted_descriptive_measures: tuple[str, ...]
    prohibited_measures: tuple[str, ...]
    required_provenance: tuple[str, ...]
    non_claims: tuple[str, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if self.protocol_id != DEFAULT_PROTOCOL_ID:
            raise CandidateReferenceProtocolError("unexpected evaluation protocol ID")
        if self.protocol_version != DEFAULT_PROTOCOL_VERSION:
            raise CandidateReferenceProtocolError(
                "unexpected evaluation protocol version"
            )
        if self.required_candidate_status != REQUIRED_CANDIDATE_STATUS:
            raise CandidateReferenceProtocolError(
                "evaluation protocol may not advance or weaken candidate eligibility"
            )
        if self.required_item_coverage_status != REQUIRED_HUMAN_COVERAGE_STATUS:
            raise CandidateReferenceProtocolError(
                "evaluation requires the declared human synthesis coverage status"
            )
        if self.preserved_output_keys != PRESERVED_OUTPUT_KEYS:
            raise CandidateReferenceProtocolError(
                "the evaluation must preserve all four VADER outputs in exact order"
            )
        if self.directional_output_key != "compound":
            raise CandidateReferenceProtocolError(
                "the frozen directional mapping must use compound only"
            )
        if tuple(item.bucket for item in self.thresholds) != CANDIDATE_BUCKETS:
            raise CandidateReferenceProtocolError(
                "candidate thresholds must be ordered unfavorable, neutral, favorable"
            )
        _validate_threshold_partition(self.thresholds)
        if dict(self.human_bucket_mapping) != dict(EXPECTED_HUMAN_MAPPING):
            raise CandidateReferenceProtocolError(
                "human response mapping must preserve the exact preregistered collapse"
            )
        if not self.permitted_descriptive_measures or not self.prohibited_measures:
            raise CandidateReferenceProtocolError(
                "evaluation protocol must declare permitted and prohibited measures"
            )
        required_prohibitions = {
            "accuracy",
            "majority human label",
            "threshold tuning",
            "candidate selection",
            "candidate lifecycle advancement",
            "creator-facing authorization",
        }
        if not required_prohibitions.issubset(set(self.prohibited_measures)):
            raise CandidateReferenceProtocolError(
                "evaluation protocol is missing required prohibitions"
            )
        if self.non_claims != REQUIRED_NON_CLAIMS:
            raise CandidateReferenceProtocolError(
                "evaluation protocol must preserve the exact declared non-claims"
            )
        expected_hash = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected_hash:
            raise CandidateReferenceProtocolError(
                "evaluation protocol hash must match its canonical payload"
            )

    def classify_compound(self, value: float) -> DirectionBucket:
        """Classify one exact finite VADER compound output under frozen thresholds."""

        if isinstance(value, bool) or not isinstance(value, int | float):
            raise CandidateReferenceProtocolError("compound output must be numeric")
        measured = float(value)
        if not math.isfinite(measured):
            raise CandidateReferenceProtocolError("compound output must be finite")
        if not -1.0 <= measured <= 1.0:
            raise CandidateReferenceProtocolError(
                "compound output must remain inside its declared [-1, 1] bounds"
            )
        matches = tuple(item.bucket for item in self.thresholds if item.contains(measured))
        if len(matches) != 1:
            raise CandidateReferenceProtocolError(
                "compound output must match exactly one frozen threshold interval"
            )
        return matches[0]

    def collapse_human_distribution(
        self,
        counts: Mapping[str, int],
    ) -> HumanDirectionalDistribution:
        """Derive four counts while requiring the full original distribution."""

        expected = {label.value for label in ValenceLabel}
        if set(counts) != expected:
            raise CandidateReferenceProtocolError(
                "human counts must include every original response option"
            )
        for key, value in counts.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CandidateReferenceProtocolError(
                    f"human count {key!r} must be a non-negative integer"
                )
        return HumanDirectionalDistribution(
            unfavorable=(
                counts[ValenceLabel.STRONGLY_UNFAVORABLE.value]
                + counts[ValenceLabel.SOMEWHAT_UNFAVORABLE.value]
            ),
            neutral=counts[ValenceLabel.NEITHER.value],
            favorable=(
                counts[ValenceLabel.SOMEWHAT_FAVORABLE.value]
                + counts[ValenceLabel.STRONGLY_FAVORABLE.value]
            ),
            abstention=counts[ValenceLabel.CANNOT_DETERMINE.value],
        )

    def describe_correspondence(
        self,
        candidate_bucket: DirectionBucket,
        human: HumanDirectionalDistribution,
    ) -> DirectionalCorrespondence:
        """Describe same and different directions without producing an accuracy rate."""

        if candidate_bucket not in CANDIDATE_BUCKETS:
            raise CandidateReferenceProtocolError(
                "candidate abstention or failure cannot be forced into a direction"
            )
        return DirectionalCorrespondence(
            candidate_bucket=candidate_bucket,
            same_direction_count=human.count(candidate_bucket),
            unfavorable_count=human.unfavorable,
            neutral_count=human.neutral,
            favorable_count=human.favorable,
            directional_denominator=human.directional_denominator,
            human_abstention_count=human.abstention,
        )


@dataclass(frozen=True, slots=True)
class RepositoryEvaluationBindings:
    """Exact repository identities verified without executing the candidate."""

    registry_hash: str
    candidate: RealCandidateBinding
    annotation_protocol: AnnotationProtocol
    synthesis_protocol: SynthesisProtocol
    corpus: EvaluationCorpus


def _validate_threshold_partition(
    thresholds: tuple[DirectionThreshold, ...],
) -> None:
    if len(thresholds) != 3:
        raise CandidateReferenceProtocolError(
            "exactly three candidate threshold intervals are required"
        )
    unfavorable, neutral, favorable = thresholds
    if (
        unfavorable.lower_bound != -1.0
        or not unfavorable.lower_inclusive
        or unfavorable.upper_bound != -0.05
        or not unfavorable.upper_inclusive
        or neutral.lower_bound != -0.05
        or neutral.lower_inclusive
        or neutral.upper_bound != 0.05
        or neutral.upper_inclusive
        or favorable.lower_bound != 0.05
        or not favorable.lower_inclusive
        or favorable.upper_bound != 1.0
        or not favorable.upper_inclusive
    ):
        raise CandidateReferenceProtocolError(
            "candidate thresholds must be the frozen upstream -0.05 and 0.05 partition"
        )


def _thresholds(value: object) -> tuple[DirectionThreshold, ...]:
    if not isinstance(value, list):
        raise CandidateReferenceProtocolError("candidate_buckets must be an array")
    result: list[DirectionThreshold] = []
    for item in value:
        document = _mapping(item, "candidate bucket")
        result.append(
            DirectionThreshold(
                bucket=DirectionBucket(
                    _string(document.get("bucket"), "candidate bucket.bucket")
                ),
                rule=_string(document.get("rule"), "candidate bucket.rule"),
                lower_bound=_number(
                    document.get("lower_bound"), "candidate bucket.lower_bound"
                ),
                lower_inclusive=_bool(
                    document.get("lower_inclusive"),
                    "candidate bucket.lower_inclusive",
                ),
                upper_bound=_number(
                    document.get("upper_bound"), "candidate bucket.upper_bound"
                ),
                upper_inclusive=_bool(
                    document.get("upper_inclusive"),
                    "candidate bucket.upper_inclusive",
                ),
            )
        )
    return tuple(result)


def load_candidate_reference_evaluation_protocol(
    document: Mapping[str, object],
) -> CandidateReferenceEvaluationProtocol:
    """Parse and canonically identify one frozen evaluation protocol."""

    if _string(document.get("status"), "status") != "frozen":
        raise CandidateReferenceProtocolError("evaluation protocol must be frozen")

    candidate = _mapping(document.get("candidate_binding"), "candidate_binding")
    human = _mapping(document.get("human_reference_binding"), "human_reference_binding")
    preregistration = _mapping(
        document.get("preregistration_and_blinding"),
        "preregistration_and_blinding",
    )
    mapping = _mapping(document.get("directional_mapping"), "directional_mapping")
    lifecycle = _mapping(document.get("lifecycle_boundary"), "lifecycle_boundary")

    required_true = (
        "protocol_frozen_before_candidate_outputs_are_paired_with_human_synthesis",
        "candidate_execution_must_be_independent_of_human_responses",
    )
    for field_name in required_true:
        if not _bool(preregistration.get(field_name), field_name):
            raise CandidateReferenceProtocolError(
                f"preregistration field {field_name} must be true"
            )
    required_false = (
        "threshold_tuning_after_observing_results_permitted",
        "measure_selection_after_observing_results_permitted",
        "human_collection_artifacts_may_contain_candidate_identity_or_output",
    )
    for field_name in required_false:
        if _bool(preregistration.get(field_name), field_name):
            raise CandidateReferenceProtocolError(
                f"preregistration field {field_name} must be false"
            )
    if _bool(candidate.get("compound_is_confidence"), "compound_is_confidence"):
        raise CandidateReferenceProtocolError("compound must never be confidence")
    if _bool(
        candidate.get("user_facing_execution_permitted"),
        "candidate user-facing execution",
    ):
        raise CandidateReferenceProtocolError(
            "evaluation protocol may not authorize user-facing execution"
        )
    if not _bool(
        human.get("full_original_distribution_required"),
        "full_original_distribution_required",
    ):
        raise CandidateReferenceProtocolError(
            "the original human distribution must remain required"
        )
    if not _bool(
        human.get("abstention_preserved_separately"),
        "abstention_preserved_separately",
    ):
        raise CandidateReferenceProtocolError(
            "human abstention must remain a separate category"
        )
    if _string(lifecycle.get("candidate_status_before"), "candidate_status_before") != (
        REQUIRED_CANDIDATE_STATUS
    ) or _string(lifecycle.get("candidate_status_after"), "candidate_status_after") != (
        REQUIRED_CANDIDATE_STATUS
    ):
        raise CandidateReferenceProtocolError(
            "evaluation must leave the candidate lifecycle unchanged"
        )
    for field_name in (
        "selection_record_created",
        "creator_facing_execution_permitted",
        "license_status_changed",
    ):
        if _bool(lifecycle.get(field_name), field_name):
            raise CandidateReferenceProtocolError(
                f"lifecycle field {field_name} must remain false"
            )

    raw_human_mapping = _mapping(
        mapping.get("human_bucket_mapping"), "human_bucket_mapping"
    )
    human_mapping = MappingProxyType(
        {
            key: DirectionBucket(_string(value, f"human_bucket_mapping.{key}"))
            for key, value in raw_human_mapping.items()
        }
    )
    payload = canonical_json_bytes(document)
    return CandidateReferenceEvaluationProtocol(
        protocol_id=_string(document.get("protocol_id"), "protocol_id"),
        protocol_version=_string(
            document.get("protocol_version"), "protocol_version"
        ),
        purpose=_string(document.get("purpose"), "purpose"),
        candidate_registry_id=_string(
            candidate.get("registry_id"), "candidate_binding.registry_id"
        ),
        candidate_registry_version=_string(
            candidate.get("registry_version"), "candidate_binding.registry_version"
        ),
        candidate_id=_string(
            candidate.get("candidate_id"), "candidate_binding.candidate_id"
        ),
        required_candidate_status=_string(
            candidate.get("required_candidate_status"),
            "candidate_binding.required_candidate_status",
        ),
        analyzer_id=_string(
            candidate.get("analyzer_id"), "candidate_binding.analyzer_id"
        ),
        adapter_revision=_string(
            candidate.get("adapter_revision"), "candidate_binding.adapter_revision"
        ),
        distribution=_string(
            candidate.get("distribution"), "candidate_binding.distribution"
        ),
        distribution_version=_string(
            candidate.get("distribution_version"),
            "candidate_binding.distribution_version",
        ),
        configuration_hash=_string(
            candidate.get("configuration_hash"),
            "candidate_binding.configuration_hash",
        ),
        candidate_dimension_id=_string(
            candidate.get("dimension_id"), "candidate_binding.dimension_id"
        ),
        candidate_dimension_version=_string(
            candidate.get("dimension_version"),
            "candidate_binding.dimension_version",
        ),
        preserved_output_keys=_strings(
            candidate.get("preserved_output_keys"),
            "candidate_binding.preserved_output_keys",
        ),
        directional_output_key=_string(
            candidate.get("directional_output_key"),
            "candidate_binding.directional_output_key",
        ),
        annotation_protocol_id=_string(
            human.get("annotation_protocol_id"),
            "human_reference_binding.annotation_protocol_id",
        ),
        annotation_protocol_version=_string(
            human.get("annotation_protocol_version"),
            "human_reference_binding.annotation_protocol_version",
        ),
        synthesis_protocol_id=_string(
            human.get("synthesis_protocol_id"),
            "human_reference_binding.synthesis_protocol_id",
        ),
        synthesis_protocol_version=_string(
            human.get("synthesis_protocol_version"),
            "human_reference_binding.synthesis_protocol_version",
        ),
        corpus_id=_string(
            human.get("corpus_id"), "human_reference_binding.corpus_id"
        ),
        corpus_version=_string(
            human.get("corpus_version"), "human_reference_binding.corpus_version"
        ),
        human_dimension_id=_string(
            human.get("dimension_id"), "human_reference_binding.dimension_id"
        ),
        human_dimension_version=_string(
            human.get("dimension_version"),
            "human_reference_binding.dimension_version",
        ),
        required_item_coverage_status=_string(
            human.get("required_item_coverage_status"),
            "human_reference_binding.required_item_coverage_status",
        ),
        thresholds=_thresholds(mapping.get("candidate_buckets")),
        human_bucket_mapping=human_mapping,
        permitted_descriptive_measures=_strings(
            document.get("permitted_descriptive_measures"),
            "permitted_descriptive_measures",
        ),
        prohibited_measures=_strings(
            document.get("prohibited_measures"), "prohibited_measures"
        ),
        required_provenance=_strings(
            document.get("required_provenance"), "required_provenance"
        ),
        non_claims=_strings(document.get("non_claims"), "non_claims"),
        created_at=_string(document.get("created_at"), "created_at"),
        canonical_payload=payload,
        artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
    )


def load_default_evaluation_protocol(
    path: Path = DEFAULT_EVALUATION_PROTOCOL,
) -> CandidateReferenceEvaluationProtocol:
    """Load the repository's frozen candidate-reference evaluation protocol."""

    return load_candidate_reference_evaluation_protocol(
        _load_document(path, "candidate-reference evaluation protocol")
    )


def _candidate_record(
    registry: Mapping[str, object],
    candidate_id: str,
) -> Mapping[str, object]:
    candidates = registry.get("candidates")
    if not isinstance(candidates, list):
        raise CandidateReferenceProtocolError("candidate registry requires candidates")
    for item in candidates:
        record = _mapping(item, "candidate record")
        if record.get("candidate_id") == candidate_id:
            return record
    raise CandidateReferenceProtocolError(
        f"candidate {candidate_id!r} is absent from the real registry"
    )


def validate_repository_bindings(
    protocol: CandidateReferenceEvaluationProtocol,
    *,
    registry_path: Path = DEFAULT_REAL_CANDIDATE_REGISTRY,
    annotation_protocol_path: Path = DEFAULT_ANNOTATION_PROTOCOL,
    synthesis_protocol_path: Path = DEFAULT_SYNTHESIS_PROTOCOL,
    corpus_path: Path = DEFAULT_CORPUS,
) -> RepositoryEvaluationBindings:
    """Verify exact repository identities without running or importing VADER."""

    registry = _load_document(registry_path, "real-candidate registry")
    if _string(registry.get("registry_id"), "registry_id") != protocol.candidate_registry_id:
        raise CandidateReferenceProtocolError("candidate registry ID mismatch")
    if _string(registry.get("registry_version"), "registry_version") != (
        protocol.candidate_registry_version
    ):
        raise CandidateReferenceProtocolError("candidate registry version mismatch")
    if _string(registry.get("status"), "registry status") != "accepted":
        raise CandidateReferenceProtocolError("candidate registry must be accepted")

    record = _candidate_record(registry, protocol.candidate_id)
    if _string(record.get("status"), "candidate status") != (
        protocol.required_candidate_status
    ):
        raise CandidateReferenceProtocolError("candidate lifecycle status mismatch")
    authorized = _strings(
        record.get("authorized_analyzer_ids"), "authorized_analyzer_ids"
    )
    if protocol.analyzer_id not in authorized:
        raise CandidateReferenceProtocolError(
            "evaluation analyzer is not authorized by the candidate registry"
        )
    dimensions = _strings(record.get("dimensions"), "candidate dimensions")
    if protocol.candidate_dimension_id not in dimensions:
        raise CandidateReferenceProtocolError(
            "candidate registry does not declare the evaluation dimension"
        )

    binding = real_candidate_binding(registry, protocol.candidate_id)
    if binding.candidate_id != VADER_CANDIDATE_ID:
        raise CandidateReferenceProtocolError("unexpected candidate identity")
    if protocol.candidate_id != VADER_CANDIDATE_ID:
        raise CandidateReferenceProtocolError("protocol candidate identity mismatch")
    if protocol.analyzer_id != VADER_ANALYZER_ID:
        raise CandidateReferenceProtocolError("protocol analyzer identity mismatch")
    if protocol.adapter_revision != VADER_ADAPTER_REVISION:
        raise CandidateReferenceProtocolError("protocol adapter revision mismatch")
    if protocol.distribution != VADER_DISTRIBUTION:
        raise CandidateReferenceProtocolError("protocol distribution mismatch")
    if protocol.distribution_version != VADER_PINNED_VERSION:
        raise CandidateReferenceProtocolError("protocol distribution version mismatch")
    if binding.package.distribution != protocol.distribution:
        raise CandidateReferenceProtocolError("registry distribution mismatch")
    if binding.package.version != protocol.distribution_version:
        raise CandidateReferenceProtocolError("registry distribution version mismatch")
    if binding.configuration_hash != protocol.configuration_hash:
        raise CandidateReferenceProtocolError("registry configuration hash mismatch")
    if protocol.configuration_hash != vader_configuration_hash():
        raise CandidateReferenceProtocolError(
            "protocol configuration hash does not match the admitted adapter"
        )
    if binding.execution_boundary.user_facing_execution_permitted:
        raise CandidateReferenceProtocolError(
            "candidate registry unexpectedly permits user-facing execution"
        )

    annotation_protocol = load_annotation_protocol(
        _load_document(annotation_protocol_path, "annotation protocol")
    )
    synthesis_protocol = SynthesisProtocol.from_document(
        _load_document(synthesis_protocol_path, "synthesis protocol")
    )
    corpus = load_evaluation_corpus(_load_document(corpus_path, "evaluation corpus"))

    if (
        annotation_protocol.protocol_id != protocol.annotation_protocol_id
        or annotation_protocol.protocol_version != protocol.annotation_protocol_version
    ):
        raise CandidateReferenceProtocolError("annotation protocol binding mismatch")
    if (
        synthesis_protocol.protocol_id != protocol.synthesis_protocol_id
        or synthesis_protocol.protocol_version != protocol.synthesis_protocol_version
    ):
        raise CandidateReferenceProtocolError("synthesis protocol binding mismatch")
    if corpus.corpus_id != protocol.corpus_id or corpus.corpus_version != protocol.corpus_version:
        raise CandidateReferenceProtocolError("evaluation corpus binding mismatch")
    if (
        annotation_protocol.dimension_id != protocol.human_dimension_id
        or annotation_protocol.dimension_version != protocol.human_dimension_version
        or corpus.dimension_id != protocol.human_dimension_id
        or corpus.dimension_version != protocol.human_dimension_version
        or synthesis_protocol.dimension_id != protocol.human_dimension_id
    ):
        raise CandidateReferenceProtocolError("human-reference dimension mismatch")
    if (
        synthesis_protocol.compatible_annotation_protocol_id
        != annotation_protocol.protocol_id
        or synthesis_protocol.compatible_annotation_protocol_version
        != annotation_protocol.protocol_version
        or synthesis_protocol.compatible_corpus_id != corpus.corpus_id
        or synthesis_protocol.compatible_corpus_version != corpus.corpus_version
    ):
        raise CandidateReferenceProtocolError(
            "synthesis protocol compatibility bindings are inconsistent"
        )
    if synthesis_protocol.below_threshold_status != INSUFFICIENT_COVERAGE:
        raise CandidateReferenceProtocolError(
            "synthesis protocol below-threshold status changed"
        )

    return RepositoryEvaluationBindings(
        registry_hash=_sha256(registry),
        candidate=binding,
        annotation_protocol=annotation_protocol,
        synthesis_protocol=synthesis_protocol,
        corpus=corpus,
    )


__all__ = [
    "CANDIDATE_BUCKETS",
    "DEFAULT_ANNOTATION_PROTOCOL",
    "DEFAULT_CORPUS",
    "DEFAULT_EVALUATION_PROTOCOL",
    "DEFAULT_REAL_CANDIDATE_REGISTRY",
    "DEFAULT_SYNTHESIS_PROTOCOL",
    "EVALUATION_PROTOCOL_VERSION",
    "EXPECTED_HUMAN_MAPPING",
    "REQUIRED_CANDIDATE_STATUS",
    "REQUIRED_HUMAN_COVERAGE_STATUS",
    "CandidateReferenceEvaluationProtocol",
    "CandidateReferenceProtocolError",
    "DirectionBucket",
    "DirectionThreshold",
    "DirectionalCorrespondence",
    "HumanDirectionalDistribution",
    "RepositoryEvaluationBindings",
    "load_candidate_reference_evaluation_protocol",
    "load_default_evaluation_protocol",
    "validate_repository_bindings",
]
