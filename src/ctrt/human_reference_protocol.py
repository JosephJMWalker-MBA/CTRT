"""Contracts for blinded human-reference annotation of one declared dimension.

Human-reference annotations preserve independent judgments under a declared
protocol. They do not become ground truth merely because humans supplied them.

Disagreement, ambiguity, insufficient context, and abstention are evidence to
preserve, not errors to erase. Nothing in this module aggregates, adjudicates,
or reconciles annotations, and nothing here references any analyzer candidate.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ctrt.serialization import canonical_json_bytes

#: Locally chosen pseudonymous identity only. Deliberately too narrow to hold an
#: email address, a phone number, or an account identifier.
ANNOTATOR_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,31}$")

#: Keys that would turn a research corpus into an answer key.
FORBIDDEN_CORPUS_ITEM_KEYS = frozenset(
    {
        "label",
        "labels",
        "expected_label",
        "expected_response",
        "gold",
        "gold_label",
        "ground_truth",
        "answer",
        "correct_answer",
        "valence",
        "valence_label",
        "sentiment",
        "score",
    }
)

#: Keys that would leak the blinded candidate into annotation material.
FORBIDDEN_CANDIDATE_KEYS = frozenset(
    {
        "candidate_id",
        "analyzer_id",
        "analyzer",
        "model_id",
        "model_version",
        "package_version",
        "distribution",
        "compound",
        "neg",
        "neu",
        "pos",
        "registry_status",
        "expectation_id",
        "characterization_id",
    }
)


class HumanReferenceError(ValueError):
    """Raised when human-reference material violates its declared contract."""


class ValenceLabel(StrEnum):
    """Exact ordered categorical response scale, preserved as entered."""

    STRONGLY_UNFAVORABLE = "strongly_unfavorable"
    SOMEWHAT_UNFAVORABLE = "somewhat_unfavorable"
    NEITHER = "neither_clearly_favorable_nor_unfavorable"
    SOMEWHAT_FAVORABLE = "somewhat_favorable"
    STRONGLY_FAVORABLE = "strongly_favorable"
    CANNOT_DETERMINE = "cannot_determine_responsibly"


class ContextSufficiency(StrEnum):
    """Whether the exact shown text was enough to answer responsibly."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    UNSURE = "unsure"


class PerceivedAmbiguity(StrEnum):
    """How open to more than one reading the passage seemed."""

    NONE = "none"
    SOME = "some"
    HIGH = "high"


class SelfReportedCertainty(StrEnum):
    """An annotator's self-report. Never analyzer confidence."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AbstentionReason(StrEnum):
    """Why an annotator declined to record a valence judgment."""

    INSUFFICIENT_CONTEXT = "insufficient_context"
    AMBIGUOUS_BETWEEN_READINGS = "ambiguous_between_readings"
    UNFAMILIAR_VOCABULARY_OR_REFERENCE = "unfamiliar_vocabulary_or_reference"
    REQUIRES_DOMAIN_KNOWLEDGE = "requires_domain_knowledge"
    OTHER_RECORDED_IN_RATIONALE = "other_recorded_in_rationale"


#: The one abstention option in the versioned valence scale.
ABSTENTION_LABEL = ValenceLabel.CANNOT_DETERMINE

#: Declared serialization convenience only. Never an interval measurement.
ORDINAL_POSITIONS: Mapping[ValenceLabel, int | None] = {
    ValenceLabel.STRONGLY_UNFAVORABLE: 0,
    ValenceLabel.SOMEWHAT_UNFAVORABLE: 1,
    ValenceLabel.NEITHER: 2,
    ValenceLabel.SOMEWHAT_FAVORABLE: 3,
    ValenceLabel.STRONGLY_FAVORABLE: 4,
    ValenceLabel.CANNOT_DETERMINE: None,
}


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HumanReferenceError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise HumanReferenceError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanReferenceError(f"{field_name} must be a non-empty string")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise HumanReferenceError(f"{field_name} must be a boolean")
    return value


def _int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HumanReferenceError(f"{field_name} must be an integer")
    return value


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise HumanReferenceError(f"{field_name} must be an array")
    result = tuple(_string(item, f"{field_name} item") for item in value)
    if len(result) != len(set(result)):
        raise HumanReferenceError(f"{field_name} must not contain duplicates")
    return result


def content_hash(text: str) -> str:
    """Return the canonical hash of exact UTF-8 item bytes."""

    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def validate_annotator_id(value: str) -> str:
    """Return a pseudonymous annotator ID, or fail closed.

    The accepted format is deliberately too narrow to carry an email address, a
    phone number, an account handle, or a path fragment.
    """

    if ANNOTATOR_ID_PATTERN.fullmatch(value) is None:
        raise HumanReferenceError(
            "annotator_id must be 3-32 characters of lowercase letters, digits, or "
            "hyphens, starting with a letter, and must not contain personal "
            "information such as a name, email address, or account identifier"
        )
    return value


@dataclass(frozen=True, slots=True)
class EvaluationItem:
    """One exact repository-authored item with no expected response."""

    position: int
    item_id: str
    text: str
    content_hash: str
    language: str
    source_type: str
    categories: tuple[str, ...]
    includes_condition: str

    def __post_init__(self) -> None:
        if self.position < 0:
            raise HumanReferenceError("item position must be non-negative")
        if not self.text.strip():
            raise HumanReferenceError("item text must not be empty")
        if not self.categories:
            raise HumanReferenceError("item requires at least one design category")
        if not self.includes_condition.strip():
            raise HumanReferenceError("item requires a condition description")
        if self.content_hash != content_hash(self.text):
            raise HumanReferenceError(
                f"item {self.item_id} content hash does not match its exact text"
            )


@dataclass(frozen=True, slots=True)
class EvaluationCorpus:
    """A frozen, repository-authored, answer-free human-reference corpus."""

    corpus_id: str
    corpus_version: str
    purpose: str
    dimension_id: str
    dimension_version: str
    items: tuple[EvaluationItem, ...]
    categories: tuple[str, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.items:
            raise HumanReferenceError("evaluation corpus must not be empty")
        positions = tuple(item.position for item in self.items)
        if positions != tuple(range(len(self.items))):
            raise HumanReferenceError(
                "item positions must be contiguous, ordered, and zero-based"
            )
        item_ids = tuple(item.item_id for item in self.items)
        if len(item_ids) != len(set(item_ids)):
            raise HumanReferenceError("item IDs must be unique")
        declared = set(self.categories)
        for item in self.items:
            undeclared = set(item.categories) - declared
            if undeclared:
                raise HumanReferenceError(
                    f"item {item.item_id} uses undeclared categories: "
                    + ", ".join(sorted(undeclared))
                )
        scale_values = {label.value for label in ValenceLabel}
        for category in self.categories:
            if category in scale_values:
                raise HumanReferenceError(
                    f"design category {category!r} must not name a response option"
                )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise HumanReferenceError(
                "evaluation corpus hash must match its canonical payload"
            )

    @property
    def item_ids(self) -> tuple[str, ...]:
        """Return item identities in exact frozen order."""

        return tuple(item.item_id for item in self.items)

    def item(self, item_id: str) -> EvaluationItem:
        """Return one item by stable ID, or fail closed."""

        for item in self.items:
            if item.item_id == item_id:
                return item
        raise HumanReferenceError(f"item {item_id!r} is absent from the frozen corpus")

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> EvaluationCorpus:
        """Parse and canonically identify a frozen evaluation-corpus document."""

        if _string(document.get("status"), "status") != "frozen":
            raise HumanReferenceError("evaluation corpus must be frozen")

        provenance = _mapping(document.get("provenance"), "provenance")
        if _string(provenance.get("authorship"), "provenance.authorship") != (
            "repository_authored"
        ):
            raise HumanReferenceError("evaluation corpus must be repository authored")
        for flag in (
            "external_dataset",
            "scraped_content",
            "network_retrieval",
            "personal_information",
        ):
            if _bool(provenance.get(flag), f"provenance.{flag}"):
                raise HumanReferenceError(
                    f"evaluation corpus must not declare provenance.{flag}"
                )

        expected = _mapping(document.get("expected_responses"), "expected_responses")
        if _bool(expected.get("expected_labels_present"), "expected_labels_present"):
            raise HumanReferenceError(
                "evaluation corpus must not contain expected responses"
            )

        population = _mapping(document.get("population_claim"), "population_claim")
        if _bool(population.get("represents_population"), "represents_population"):
            raise HumanReferenceError(
                "a pilot evaluation corpus may not claim to represent a population"
            )

        raw_items = document.get("items")
        if not isinstance(raw_items, list):
            raise HumanReferenceError("items must be an array")
        items = tuple(_item_from_document(_mapping(item, "item")) for item in raw_items)

        payload = canonical_json_bytes(document)
        return cls(
            corpus_id=_string(document.get("corpus_id"), "corpus_id"),
            corpus_version=_string(document.get("corpus_version"), "corpus_version"),
            purpose=_string(document.get("purpose"), "purpose"),
            dimension_id=_string(document.get("dimension_id"), "dimension_id"),
            dimension_version=_string(
                document.get("dimension_version"), "dimension_version"
            ),
            items=items,
            categories=_strings(document.get("categories"), "categories"),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )


def _item_from_document(document: Mapping[str, object]) -> EvaluationItem:
    present = FORBIDDEN_CORPUS_ITEM_KEYS & set(document)
    if present:
        raise HumanReferenceError(
            "evaluation item must not carry answer-shaped fields: "
            + ", ".join(sorted(present))
        )
    if not _bool(
        document.get("not_an_expected_response"),
        "item.not_an_expected_response",
    ):
        raise HumanReferenceError(
            "every item must declare not_an_expected_response as true"
        )
    text = _string(document.get("text"), "item.text")
    return EvaluationItem(
        position=_int(document.get("position"), "item.position"),
        item_id=_string(document.get("item_id"), "item.item_id"),
        text=text,
        content_hash=_string(document.get("content_hash"), "item.content_hash"),
        language=_string(document.get("language"), "item.language"),
        source_type=_string(document.get("source_type"), "item.source_type"),
        categories=_strings(document.get("categories"), "item.categories"),
        includes_condition=_string(
            document.get("includes_condition"), "item.includes_condition"
        ),
    )


@dataclass(frozen=True, slots=True)
class AnnotationProtocol:
    """A frozen, blinded, aggregation-free annotation protocol."""

    protocol_id: str
    protocol_version: str
    dimension_id: str
    dimension_version: str
    task_statement: str
    instructions: tuple[str, ...]
    scale_id: str
    scale_version: str
    valence_options: tuple[ValenceLabel, ...]
    abstention_reasons: tuple[AbstentionReason, ...]
    non_claims: tuple[str, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if self.valence_options != tuple(ValenceLabel):
            raise HumanReferenceError(
                "protocol must declare the exact versioned valence scale"
            )
        if not self.instructions or not self.non_claims:
            raise HumanReferenceError(
                "protocol requires instructions and declared non-claims"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise HumanReferenceError(
                "protocol hash must match its canonical payload"
            )

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> AnnotationProtocol:
        """Parse and canonically identify a frozen annotation protocol."""

        if _string(document.get("status"), "status") != "frozen":
            raise HumanReferenceError("annotation protocol must be frozen")

        aggregation = _mapping(document.get("aggregation_policy"), "aggregation_policy")
        if _bool(aggregation.get("aggregation_permitted"), "aggregation_permitted"):
            raise HumanReferenceError(
                "this protocol version must forbid aggregation and adjudication"
            )

        scale = _mapping(document.get("valence_scale"), "valence_scale")
        raw_options = scale.get("options")
        if not isinstance(raw_options, list):
            raise HumanReferenceError("valence_scale.options must be an array")
        options: list[ValenceLabel] = []
        for entry in raw_options:
            option = _mapping(entry, "valence option")
            label = ValenceLabel(_string(option.get("value"), "option.value"))
            is_abstention = _bool(option.get("is_abstention"), "option.is_abstention")
            if is_abstention != (label is ABSTENTION_LABEL):
                raise HumanReferenceError(
                    f"option {label.value!r} declares the wrong abstention state"
                )
            if option.get("ordinal_position") != ORDINAL_POSITIONS[label]:
                raise HumanReferenceError(
                    f"option {label.value!r} declares an unexpected ordinal position"
                )
            options.append(label)

        payload = canonical_json_bytes(document)
        return cls(
            protocol_id=_string(document.get("protocol_id"), "protocol_id"),
            protocol_version=_string(
                document.get("protocol_version"), "protocol_version"
            ),
            dimension_id=_string(document.get("dimension_id"), "dimension_id"),
            dimension_version=_string(
                document.get("dimension_version"), "dimension_version"
            ),
            task_statement=_string(document.get("task_statement"), "task_statement"),
            instructions=_strings(document.get("instructions"), "instructions"),
            scale_id=_string(scale.get("scale_id"), "valence_scale.scale_id"),
            scale_version=_string(
                scale.get("scale_version"), "valence_scale.scale_version"
            ),
            valence_options=tuple(options),
            abstention_reasons=tuple(
                AbstentionReason(item)
                for item in _strings(
                    document.get("abstention_reasons"), "abstention_reasons"
                )
            ),
            non_claims=_strings(document.get("non_claims"), "non_claims"),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )


@dataclass(frozen=True, slots=True)
class SupportingSpan:
    """A zero-based half-open span inside the exact item text."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise HumanReferenceError("span start must be non-negative")
        if self.end <= self.start:
            raise HumanReferenceError("span end must be greater than start")


def validate_spans(
    spans: tuple[SupportingSpan, ...],
    text: str,
) -> tuple[SupportingSpan, ...]:
    """Return spans only when every one falls inside the exact item text."""

    for span in spans:
        if span.end > len(text):
            raise HumanReferenceError(
                f"supporting span [{span.start}:{span.end}] falls outside the exact "
                f"{len(text)}-character item text"
            )
    return spans


def load_evaluation_corpus(document: Mapping[str, object]) -> EvaluationCorpus:
    """Parse one frozen human-reference evaluation corpus."""

    return EvaluationCorpus.from_document(document)


def load_annotation_protocol(document: Mapping[str, object]) -> AnnotationProtocol:
    """Parse one frozen blinded annotation protocol."""

    return AnnotationProtocol.from_document(document)


__all__ = [
    "ABSTENTION_LABEL",
    "ANNOTATOR_ID_PATTERN",
    "FORBIDDEN_CANDIDATE_KEYS",
    "FORBIDDEN_CORPUS_ITEM_KEYS",
    "ORDINAL_POSITIONS",
    "AbstentionReason",
    "AnnotationProtocol",
    "ContextSufficiency",
    "EvaluationCorpus",
    "EvaluationItem",
    "HumanReferenceError",
    "PerceivedAmbiguity",
    "SelfReportedCertainty",
    "SupportingSpan",
    "ValenceLabel",
    "content_hash",
    "load_annotation_protocol",
    "load_evaluation_corpus",
    "validate_annotator_id",
    "validate_spans",
]
