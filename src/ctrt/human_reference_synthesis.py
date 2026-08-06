"""Preregistered descriptive synthesis of multiple human-reference collections.

Human-reference synthesis describes the judgments collected under a declared
protocol. It does not convert those judgments into truth.

Disagreement is a result to preserve. It is not automatically a defect
requiring majority rule or adjudication.

This protocol permits descriptive human-human concordance. It does not
establish correctness, population validity, or candidate fitness.

Nothing here computes a majority, mode-as-answer, median, mean, consensus,
adjudicated, gold, or correct label, ranks or scores an annotator, or names,
imports, or evaluates any analyzer candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.human_reference_annotation import (
    COLLECTION_VERSION,
    AnnotationResponse,
    _response_from_artifact_text,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    FORBIDDEN_CANDIDATE_KEYS,
    ORDINAL_POSITIONS,
    AnnotationProtocol,
    ContextSufficiency,
    EvaluationCorpus,
    HumanReferenceError,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
    validate_annotator_id,
)
from ctrt.serialization import canonical_json_bytes, serialize_artifact

SYNTHESIS_VERSION = "ctrt-human-reference-synthesis@0.1.0"
SYNTHESIS_RECORD_TYPE = "descriptive_human_reference_synthesis"
INSUFFICIENT_COVERAGE = "insufficient_reference_coverage"
SUFFICIENT_COVERAGE = "meets_declared_minimum_coverage"
ORDINAL_DISTANCE_BUCKETS = (0, 1, 2, 3, 4)

FIXTURE_MARKER_SUFFIX = "fixture-marker"

SYNTHESIS_NON_CLAIMS = (
    "Human-reference synthesis describes the judgments collected under a declared "
    "protocol. It does not convert those judgments into truth.",
    "Disagreement is a result to preserve. It is not automatically a defect "
    "requiring majority rule or adjudication.",
    "This protocol permits descriptive human-human concordance. It does not "
    "establish correctness, population validity, or candidate fitness.",
    "This synthesis produces no majority, mode-as-answer, median, mean, consensus, "
    "adjudicated, gold, or correct label, and no merged human score.",
    "This synthesis ranks no annotator and scores no annotator.",
    "This synthesis does not run, name, import, compare against, evaluate, or "
    "select any analyzer candidate, and the candidate lifecycle is unchanged.",
    "The participating annotators do not represent any population.",
    "Coverage and abstention counts are lifecycle information. They are never a "
    "measure of annotation quality.",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_SYNTHESIS_PROTOCOL = (
    _repo_root() / "docs" / "protocols" / "human-reference-synthesis.v0.1.0.json"
)
DEFAULT_ANNOTATION_PROTOCOL = (
    _repo_root()
    / "docs"
    / "protocols"
    / "human-reference-sentiment-valence.v0.1.0.json"
)
DEFAULT_CORPUS = (
    _repo_root() / "docs" / "corpora" / "human-reference-sentiment.v0.1.0.json"
)


class SynthesisError(ValueError):
    """Raised when human-reference synthesis cannot proceed exactly."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SynthesisError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise SynthesisError(f"{field_name} keys must be strings")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SynthesisError(f"{field_name} must be a non-empty string")
    return value


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SynthesisError(f"{field_name} must be a boolean")
    return value


def _int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SynthesisError(f"{field_name} must be an integer")
    return value


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise SynthesisError(f"{field_name} must be an array")
    return tuple(_string(item, f"{field_name} item") for item in value)


def _load_document(path: Path, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SynthesisError(f"unable to read {field_name} from {path}") from exc
    return _mapping(value, field_name)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise SynthesisError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SynthesisProtocol:
    """A frozen, preregistered, aggregation-free synthesis protocol."""

    protocol_id: str
    protocol_version: str
    purpose: str
    compatible_annotation_protocol_id: str
    compatible_annotation_protocol_version: str
    compatible_corpus_id: str
    compatible_corpus_version: str
    dimension_id: str
    minimum_distinct_annotators_per_item: int
    below_threshold_status: str
    permitted_descriptive_measures: tuple[str, ...]
    prohibited_measures: tuple[str, ...]
    non_claims: tuple[str, ...]
    created_at: str
    canonical_payload: bytes
    artifact_hash: str

    def __post_init__(self) -> None:
        if self.minimum_distinct_annotators_per_item < 2:
            raise SynthesisError(
                "minimum coverage must permit at least a pair of independent readers"
            )
        if self.below_threshold_status != INSUFFICIENT_COVERAGE:
            raise SynthesisError("below-threshold status must be explicit")
        if not self.permitted_descriptive_measures or not self.prohibited_measures:
            raise SynthesisError(
                "synthesis protocol must declare permitted and prohibited measures"
            )
        expected = f"sha256:{hashlib.sha256(self.canonical_payload).hexdigest()}"
        if self.artifact_hash != expected:
            raise SynthesisError("synthesis protocol hash must match its payload")

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> SynthesisProtocol:
        """Parse and canonically identify one frozen synthesis protocol."""

        if _string(document.get("status"), "status") != "frozen":
            raise SynthesisError("synthesis protocol must be frozen")

        coverage = _mapping(
            document.get("minimum_reference_coverage"), "minimum_reference_coverage"
        )
        abstention = _mapping(
            document.get("abstention_treatment"), "abstention_treatment"
        )
        if not _bool(abstention.get("separate_category"), "separate_category"):
            raise SynthesisError("abstention must remain a separate category")
        if _bool(abstention.get("numerically_encoded"), "numerically_encoded"):
            raise SynthesisError("abstention must not be numerically encoded")

        concordance = _mapping(document.get("concordance_rules"), "concordance_rules")
        if not _bool(
            concordance.get("denominator_preserving"), "denominator_preserving"
        ):
            raise SynthesisError("concordance must preserve denominators")
        buckets = concordance.get("ordinal_distance_buckets")
        if list(ORDINAL_DISTANCE_BUCKETS) != buckets:
            raise SynthesisError("ordinal distance buckets must be exactly 0 through 4")

        payload = canonical_json_bytes(document)
        return cls(
            protocol_id=_string(document.get("protocol_id"), "protocol_id"),
            protocol_version=_string(
                document.get("protocol_version"), "protocol_version"
            ),
            purpose=_string(document.get("purpose"), "purpose"),
            compatible_annotation_protocol_id=_string(
                document.get("compatible_annotation_protocol_id"),
                "compatible_annotation_protocol_id",
            ),
            compatible_annotation_protocol_version=_string(
                document.get("compatible_annotation_protocol_version"),
                "compatible_annotation_protocol_version",
            ),
            compatible_corpus_id=_string(
                document.get("compatible_corpus_id"), "compatible_corpus_id"
            ),
            compatible_corpus_version=_string(
                document.get("compatible_corpus_version"), "compatible_corpus_version"
            ),
            dimension_id=_string(document.get("dimension_id"), "dimension_id"),
            minimum_distinct_annotators_per_item=_int(
                coverage.get("minimum_distinct_annotators_per_item"),
                "minimum_distinct_annotators_per_item",
            ),
            below_threshold_status=_string(
                coverage.get("below_threshold_status"), "below_threshold_status"
            ),
            permitted_descriptive_measures=_strings(
                document.get("permitted_descriptive_measures"),
                "permitted_descriptive_measures",
            ),
            prohibited_measures=_strings(
                document.get("prohibited_measures"), "prohibited_measures"
            ),
            non_claims=_strings(document.get("non_claims"), "non_claims"),
            created_at=_string(document.get("created_at"), "created_at"),
            canonical_payload=payload,
            artifact_hash=f"sha256:{hashlib.sha256(payload).hexdigest()}",
        )


@dataclass(frozen=True, slots=True)
class SupersessionAncestry:
    """The exact append-only chain resolving one item's effective response."""

    item_id: str
    annotator_id: str
    original_response_ref: StoredArtifactRef
    superseding_response_refs: tuple[StoredArtifactRef, ...]
    effective_response_ref: StoredArtifactRef
    supersession_reasons: tuple[str, ...]
    chain_length: int
    chain_unbroken: bool

    def __post_init__(self) -> None:
        if not self.chain_unbroken:
            raise SynthesisError(
                f"item {self.item_id} has a broken or branching supersession chain"
            )
        if self.chain_length != len(self.superseding_response_refs) + 1:
            raise SynthesisError("supersession ancestry length is inconsistent")
        if len(self.supersession_reasons) != len(self.superseding_response_refs):
            raise SynthesisError("each supersession requires a preserved reason")


@dataclass(frozen=True, slots=True)
class IncludedCollection:
    """One verified, reverified collection receipt admitted to a synthesis."""

    annotator_id: str
    assignment_id: str
    completion_ref: StoredArtifactRef
    corpus_hash: str
    protocol_hash: str
    item_ids: tuple[str, ...]
    responses: Mapping[str, AnnotationResponse]
    ancestry: Mapping[str, SupersessionAncestry]

    def __post_init__(self) -> None:
        validate_annotator_id(self.annotator_id)
        if set(self.responses) != set(self.item_ids):
            raise SynthesisError(
                "an eligible collection requires one effective response per item"
            )


@dataclass(frozen=True, slots=True)
class ValenceDistribution:
    """Counts for every exact response option, including zero observations."""

    counts: Mapping[str, int]

    def __post_init__(self) -> None:
        expected = {label.value for label in ValenceLabel}
        if set(self.counts) != expected:
            raise SynthesisError(
                "the distribution must include every response option, including "
                "options with zero observations"
            )
        if any(value < 0 for value in self.counts.values()):
            raise SynthesisError("response counts must be non-negative")


@dataclass(frozen=True, slots=True)
class ConcordancePair:
    """One denominator-preserving pairwise concordance description."""

    label: str
    agreeing_pairs: int
    compared_pairs: int
    abstentions_included: bool

    def __post_init__(self) -> None:
        if self.compared_pairs < 0 or self.agreeing_pairs < 0:
            raise SynthesisError("concordance counts must be non-negative")
        if self.agreeing_pairs > self.compared_pairs:
            raise SynthesisError("agreeing pairs cannot exceed compared pairs")
        if "accuracy" in self.label.lower():
            raise SynthesisError("a concordance description may not be called accuracy")


@dataclass(frozen=True, slots=True)
class ItemSynthesis:
    """Descriptive record for one item. Never chooses a preferred response."""

    item_id: str
    content_hash: str
    text: str
    distinct_annotators: int
    coverage_status: str
    valence_distribution: ValenceDistribution
    abstention_count: int
    abstention_reason_counts: Mapping[str, int]
    unanswered_count: int
    context_sufficiency_counts: Mapping[str, int]
    ambiguity_counts: Mapping[str, int]
    certainty_counts: Mapping[str, int]
    rationale_present_count: int
    supporting_span_present_count: int
    concordance_including_abstention: ConcordancePair
    concordance_non_abstaining: ConcordancePair
    ordinal_distance_histogram: Mapping[str, int]
    response_refs: tuple[StoredArtifactRef, ...]

    def __post_init__(self) -> None:
        if self.coverage_status not in {INSUFFICIENT_COVERAGE, SUFFICIENT_COVERAGE}:
            raise SynthesisError("coverage status must be explicit")
        if set(self.ordinal_distance_histogram) != {
            str(bucket) for bucket in ORDINAL_DISTANCE_BUCKETS
        }:
            raise SynthesisError(
                "the ordinal distance histogram must carry exactly buckets 0 to 4"
            )
        if set(self.context_sufficiency_counts) != {
            item.value for item in ContextSufficiency
        }:
            raise SynthesisError("context sufficiency counts must cover every option")
        if set(self.ambiguity_counts) != {item.value for item in PerceivedAmbiguity}:
            raise SynthesisError("ambiguity counts must cover every option")
        expected_certainty = {item.value for item in SelfReportedCertainty} | {
            "not_provided"
        }
        if set(self.certainty_counts) != expected_certainty:
            raise SynthesisError("certainty counts must cover every option")
        total = sum(self.valence_distribution.counts.values())
        if total != self.distinct_annotators:
            raise SynthesisError(
                "the response distribution must account for every distinct annotator"
            )
        if self.abstention_count != self.valence_distribution.counts[
            ABSTENTION_LABEL.value
        ]:
            raise SynthesisError(
                "the abstention count must match its own response category"
            )


@dataclass(frozen=True, slots=True)
class CorpusLifecycleSummary:
    """Corpus-level lifecycle counts. Never a measure of annotation quality."""

    total_items: int
    items_meeting_minimum_coverage: int
    items_with_insufficient_coverage: int
    distinct_annotators: int
    total_effective_responses: int
    total_superseded_records: int
    total_abstentions: int
    total_unanswered: int
    notes: str = (
        "Lifecycle information only. These counts describe coverage and collection "
        "outcomes and are never a measure of annotation quality, correctness, or "
        "agreement."
    )

    def __post_init__(self) -> None:
        if (
            self.items_meeting_minimum_coverage
            + self.items_with_insufficient_coverage
            != self.total_items
        ):
            raise SynthesisError("coverage counts must partition the corpus")


@dataclass(frozen=True, slots=True)
class SynthesisPlan:
    """A frozen plan naming exactly which verified receipts are synthesized."""

    plan_id: str
    synthesis_version: str
    record_type: str
    synthesis_protocol_id: str
    synthesis_protocol_version: str
    synthesis_protocol_hash: str
    annotation_protocol_id: str
    annotation_protocol_version: str
    annotation_protocol_hash: str
    corpus_id: str
    corpus_version: str
    corpus_hash: str
    minimum_distinct_annotators_per_item: int
    annotator_ids: tuple[str, ...]
    completion_refs: tuple[StoredArtifactRef, ...]
    item_ids: tuple[str, ...]
    non_claims: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        if self.record_type != SYNTHESIS_RECORD_TYPE:
            raise SynthesisError("unsupported synthesis record type")
        if self.synthesis_version != SYNTHESIS_VERSION:
            raise SynthesisError("unsupported synthesis version")
        if len(self.annotator_ids) != len(set(self.annotator_ids)):
            raise SynthesisError("synthesis requires distinct annotator IDs")
        if len(self.annotator_ids) != len(self.completion_refs):
            raise SynthesisError("one completion reference is required per annotator")
        if self.annotator_ids != tuple(sorted(self.annotator_ids)):
            raise SynthesisError("receipts must be ordered deterministically")
        if self.non_claims != SYNTHESIS_NON_CLAIMS:
            raise SynthesisError("synthesis plan must preserve the declared non-claims")


@dataclass(frozen=True, slots=True)
class SynthesisCompletion:
    """Completion marker for one descriptive synthesis run."""

    completion_id: str
    synthesis_version: str
    record_type: str
    plan_id: str
    plan_ref: StoredArtifactRef
    receipt_manifest_ref: StoredArtifactRef
    resolution_refs: tuple[StoredArtifactRef, ...]
    item_synthesis_refs: tuple[StoredArtifactRef, ...]
    lifecycle_ref: StoredArtifactRef
    lifecycle: CorpusLifecycleSummary
    candidate_lifecycle_status: str
    non_claims: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.record_type != SYNTHESIS_RECORD_TYPE:
            raise SynthesisError("unsupported synthesis record type")
        if self.candidate_lifecycle_status != "eligible_for_evaluation":
            raise SynthesisError(
                "a human-reference synthesis may not advance the candidate lifecycle"
            )
        if self.non_claims != SYNTHESIS_NON_CLAIMS:
            raise SynthesisError("completion must preserve the declared non-claims")


@dataclass(frozen=True, slots=True)
class VerifiedSynthesisReceipt:
    """Returned only after every stored artifact re-verified on read."""

    synthesis_version: str
    artifact_directory: Path
    protocol: SynthesisProtocol
    plan: SynthesisPlan
    plan_ref: StoredArtifactRef
    completion: SynthesisCompletion
    completion_ref: StoredArtifactRef
    included: tuple[IncludedCollection, ...]
    items: tuple[ItemSynthesis, ...]
    lifecycle: CorpusLifecycleSummary

    def __post_init__(self) -> None:
        if self.synthesis_version != SYNTHESIS_VERSION:
            raise SynthesisError("unsupported synthesis version")


# --------------------------------------------------------------------------
# Test-fixture boundary
# --------------------------------------------------------------------------


def _fixture_marker_id(assignment_id: str) -> str:
    return f"{assignment_id}:{FIXTURE_MARKER_SUFFIX}"


def mark_test_fixture_collection(
    store: FileSystemArtifactStore,
    *,
    assignment_id: str,
) -> StoredArtifactRef:
    """Mark one collection as a synthetic test fixture, not human evidence.

    A production synthesis run refuses any collection carrying this marker.
    Only an explicit test-only entry point accepts it.
    """

    return store.append(
        serialize_artifact(
            _fixture_marker_id(assignment_id),
            {
                "synthetic_test_fixture": True,
                "not_human_research_evidence": True,
                "assignment_id": assignment_id,
                "notes": (
                    "These annotations were generated by an automated test through "
                    "the real collection path. They are not human research evidence "
                    "and must never be reported as empirical results."
                ),
            },
        )
    )


def is_test_fixture_collection(
    store: FileSystemArtifactStore,
    *,
    assignment_id: str,
) -> bool:
    """Return whether a stored collection is marked as a synthetic fixture."""

    try:
        store.get(_fixture_marker_id(assignment_id))
    except ArtifactNotFoundError:
        return False
    return True


# --------------------------------------------------------------------------
# Receipt loading and reverification
# --------------------------------------------------------------------------


def _completion_from_artifact_text(text: str) -> Mapping[str, object]:
    document = cast(dict[str, object], json.loads(text))
    return document


def _response_chain(
    store: FileSystemArtifactStore,
    *,
    assignment_id: str,
    item_id: str,
) -> tuple[tuple[AnnotationResponse, StoredArtifactRef], ...]:
    chain: list[tuple[AnnotationResponse, StoredArtifactRef]] = []
    sequence = 0
    while True:
        artifact_id = f"{assignment_id}:{item_id}:response:{sequence}"
        try:
            artifact = store.get(artifact_id)
        except ArtifactNotFoundError:
            return tuple(chain)
        chain.append(
            (
                _response_from_artifact_text(artifact.text),
                StoredArtifactRef(
                    artifact_id=artifact.artifact_id,
                    artifact_hash=artifact.artifact_hash,
                ),
            )
        )
        sequence += 1


def _resolve_ancestry(
    *,
    item_id: str,
    annotator_id: str,
    assignment_id: str,
    chain: tuple[tuple[AnnotationResponse, StoredArtifactRef], ...],
    effective_ref: StoredArtifactRef,
) -> SupersessionAncestry:
    """Resolve one effective response through an exact append-only chain."""

    if not chain:
        raise SynthesisError(f"item {item_id} has no stored response")
    unbroken = True
    reasons: list[str] = []
    for index, (response, _) in enumerate(chain):
        if response.item_id != item_id or response.assignment_id != assignment_id:
            raise SynthesisError(
                f"a stored response does not belong to assignment {assignment_id}"
            )
        if response.sequence != index:
            unbroken = False
            break
        if index == 0:
            if response.supersedes_response_id is not None:
                unbroken = False
                break
            continue
        if response.supersedes_response_id != chain[index - 1][0].response_id:
            unbroken = False
            break
        if response.supersession_reason is None:
            unbroken = False
            break
        reasons.append(response.supersession_reason)
    if unbroken and chain[-1][1].artifact_id != effective_ref.artifact_id:
        unbroken = False
    return SupersessionAncestry(
        item_id=item_id,
        annotator_id=annotator_id,
        original_response_ref=chain[0][1],
        superseding_response_refs=tuple(item[1] for item in chain[1:]),
        effective_response_ref=chain[-1][1],
        supersession_reasons=tuple(reasons),
        chain_length=len(chain),
        chain_unbroken=unbroken,
    )


def load_verified_collection(
    *,
    store: FileSystemArtifactStore,
    completion_id: str,
    corpus: EvaluationCorpus,
    annotation_protocol: AnnotationProtocol,
    allow_test_fixtures: bool = False,
) -> IncludedCollection:
    """Reload and reverify one collection receipt from canonical storage."""

    try:
        artifact = store.get(completion_id)
    except ArtifactNotFoundError as exc:
        raise SynthesisError(
            f"verified collection receipt {completion_id!r} is not in this store"
        ) from exc

    document = _completion_from_artifact_text(artifact.text)
    present = FORBIDDEN_CANDIDATE_KEYS & set(document)
    if present:
        raise SynthesisError(
            "a human-reference artifact must not carry candidate or analyzer fields: "
            + ", ".join(sorted(present))
        )
    if _string(document.get("collection_version"), "collection_version") != (
        COLLECTION_VERSION
    ):
        raise SynthesisError("incompatible collection version")

    assignment_id = _string(document.get("assignment_id"), "assignment_id")
    annotator_id = validate_annotator_id(
        _string(document.get("annotator_id"), "annotator_id")
    )
    if not allow_test_fixtures and is_test_fixture_collection(
        store, assignment_id=assignment_id
    ):
        raise SynthesisError(
            f"collection {assignment_id!r} is marked as a synthetic test fixture and "
            "may not be used as human research evidence"
        )

    if _string(document.get("corpus_hash"), "corpus_hash") != corpus.artifact_hash:
        raise SynthesisError("receipt corpus hash does not match the declared corpus")
    if _string(document.get("protocol_hash"), "protocol_hash") != (
        annotation_protocol.artifact_hash
    ):
        raise SynthesisError(
            "receipt protocol hash does not match the declared annotation protocol"
        )

    counts = _mapping(document.get("counts"), "counts")
    if _int(counts.get("unanswered"), "counts.unanswered") != 0:
        raise SynthesisError("an incomplete assignment receipt is not eligible")

    item_ids = _strings(document.get("item_ids"), "item_ids")
    if set(item_ids) != set(corpus.item_ids):
        raise SynthesisError("receipt corpus membership differs from the frozen corpus")

    raw_refs = document.get("response_refs")
    if not isinstance(raw_refs, list) or len(raw_refs) != len(item_ids):
        raise SynthesisError("one response reference is required per assigned item")

    responses: dict[str, AnnotationResponse] = {}
    ancestry: dict[str, SupersessionAncestry] = {}
    for item_id, raw_ref in zip(item_ids, raw_refs, strict=True):
        reference = _mapping(raw_ref, "response reference")
        effective_ref = StoredArtifactRef(
            artifact_id=_string(reference.get("artifact_id"), "artifact_id"),
            artifact_hash=_string(reference.get("artifact_hash"), "artifact_hash"),
        )
        store.get(effective_ref.artifact_id, expected_hash=effective_ref.artifact_hash)
        chain = _response_chain(store, assignment_id=assignment_id, item_id=item_id)
        resolved = _resolve_ancestry(
            item_id=item_id,
            annotator_id=annotator_id,
            assignment_id=assignment_id,
            chain=chain,
            effective_ref=effective_ref,
        )
        effective = chain[-1][0]
        if effective.item_content_hash != corpus.item(item_id).content_hash:
            raise SynthesisError(
                f"stored response for {item_id} references different item bytes"
            )
        if effective.protocol_hash != annotation_protocol.artifact_hash:
            raise SynthesisError(
                f"stored response for {item_id} used a different annotation protocol"
            )
        responses[item_id] = effective
        ancestry[item_id] = resolved

    return IncludedCollection(
        annotator_id=annotator_id,
        assignment_id=assignment_id,
        completion_ref=StoredArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_hash=artifact.artifact_hash,
        ),
        corpus_hash=corpus.artifact_hash,
        protocol_hash=annotation_protocol.artifact_hash,
        item_ids=item_ids,
        responses=responses,
        ancestry=ancestry,
    )


def find_collection_store(
    workspace: Path,
    completion_id: str,
) -> FileSystemArtifactStore:
    """Locate the annotator store holding one verified collection receipt."""

    candidates = sorted(
        path for path in workspace.glob("*/artifacts") if path.is_dir()
    )
    for directory in candidates:
        store = FileSystemArtifactStore(directory)
        try:
            store.get(completion_id)
        except ArtifactNotFoundError:
            continue
        return store
    raise SynthesisError(
        f"no annotator store under {workspace} holds receipt {completion_id!r}"
    )


# --------------------------------------------------------------------------
# Descriptive synthesis
# --------------------------------------------------------------------------


def _concordance(
    responses: Sequence[AnnotationResponse],
    *,
    include_abstentions: bool,
) -> ConcordancePair:
    """Return a denominator-preserving pairwise exact-category concordance."""

    if include_abstentions:
        considered = list(responses)
        label = "pairwise-exact-category-including-abstention"
    else:
        considered = [item for item in responses if not item.abstained]
        label = "pairwise-exact-category-non-abstaining"
    pairs = list(combinations(considered, 2))
    agreeing = sum(1 for left, right in pairs if left.valence_label is right.valence_label)
    return ConcordancePair(
        label=label,
        agreeing_pairs=agreeing,
        compared_pairs=len(pairs),
        abstentions_included=include_abstentions,
    )


def _ordinal_distance_histogram(
    responses: Sequence[AnnotationResponse],
) -> Mapping[str, int]:
    """Return exact pair counts per distance bucket for non-abstaining pairs.

    Ordinal positions are a serialization convenience used only to compute a
    distance between two categorical responses. They are not interval-scale
    truth, and no mean response label is derived from them anywhere.
    """

    histogram = {str(bucket): 0 for bucket in ORDINAL_DISTANCE_BUCKETS}
    scored = [item for item in responses if not item.abstained]
    for left, right in combinations(scored, 2):
        left_position = ORDINAL_POSITIONS[left.valence_label]
        right_position = ORDINAL_POSITIONS[right.valence_label]
        if left_position is None or right_position is None:  # pragma: no cover
            raise SynthesisError("a non-abstaining response must carry an ordinal")
        histogram[str(abs(left_position - right_position))] += 1
    return histogram


def _item_synthesis(
    *,
    item_id: str,
    corpus: EvaluationCorpus,
    included: Sequence[IncludedCollection],
    minimum_coverage: int,
) -> ItemSynthesis:
    item = corpus.item(item_id)
    responses = [entry.responses[item_id] for entry in included]
    refs = tuple(entry.ancestry[item_id].effective_response_ref for entry in included)

    distribution = {label.value: 0 for label in ValenceLabel}
    abstention_reasons: dict[str, int] = {}
    context = {value.value: 0 for value in ContextSufficiency}
    ambiguity = {value.value: 0 for value in PerceivedAmbiguity}
    certainty = {value.value: 0 for value in SelfReportedCertainty} | {
        "not_provided": 0
    }
    rationale_present = 0
    spans_present = 0

    for response in responses:
        distribution[response.valence_label.value] += 1
        context[response.context_sufficiency.value] += 1
        ambiguity[response.perceived_ambiguity.value] += 1
        if response.self_reported_certainty is None:
            certainty["not_provided"] += 1
        else:
            certainty[response.self_reported_certainty.value] += 1
        if response.rationale is not None:
            rationale_present += 1
        if response.supporting_spans:
            spans_present += 1
        if response.abstention_reason is not None:
            key = response.abstention_reason.value
            abstention_reasons[key] = abstention_reasons.get(key, 0) + 1

    distinct = len({entry.annotator_id for entry in included})
    return ItemSynthesis(
        item_id=item_id,
        content_hash=item.content_hash,
        text=item.text,
        distinct_annotators=distinct,
        coverage_status=(
            SUFFICIENT_COVERAGE if distinct >= minimum_coverage else INSUFFICIENT_COVERAGE
        ),
        valence_distribution=ValenceDistribution(counts=distribution),
        abstention_count=distribution[ABSTENTION_LABEL.value],
        abstention_reason_counts=abstention_reasons,
        unanswered_count=0,
        context_sufficiency_counts=context,
        ambiguity_counts=ambiguity,
        certainty_counts=certainty,
        rationale_present_count=rationale_present,
        supporting_span_present_count=spans_present,
        concordance_including_abstention=_concordance(
            responses, include_abstentions=True
        ),
        concordance_non_abstaining=_concordance(responses, include_abstentions=False),
        ordinal_distance_histogram=_ordinal_distance_histogram(responses),
        response_refs=refs,
    )


def run_human_reference_synthesis(
    *,
    workspace: Path,
    completion_ids: Sequence[str],
    output_directory: Path | None = None,
    synthesis_protocol_path: Path = DEFAULT_SYNTHESIS_PROTOCOL,
    annotation_protocol_path: Path = DEFAULT_ANNOTATION_PROTOCOL,
    corpus_path: Path = DEFAULT_CORPUS,
    created_at: datetime | None = None,
    allow_test_fixtures: bool = False,
) -> VerifiedSynthesisReceipt:
    """Synthesize verified collections descriptively, preserving every judgment."""

    protocol = SynthesisProtocol.from_document(
        _load_document(synthesis_protocol_path, "synthesis protocol")
    )
    annotation_protocol = load_annotation_protocol(
        _load_document(annotation_protocol_path, "annotation protocol")
    )
    corpus = load_evaluation_corpus(_load_document(corpus_path, "evaluation corpus"))

    if annotation_protocol.protocol_id != protocol.compatible_annotation_protocol_id:
        raise SynthesisError("annotation protocol is not compatible with this synthesis")
    if (
        annotation_protocol.protocol_version
        != protocol.compatible_annotation_protocol_version
    ):
        raise SynthesisError("annotation protocol version is not compatible")
    if corpus.corpus_id != protocol.compatible_corpus_id:
        raise SynthesisError("evaluation corpus is not compatible with this synthesis")
    if corpus.corpus_version != protocol.compatible_corpus_version:
        raise SynthesisError("evaluation corpus version is not compatible")

    if len(set(completion_ids)) != len(completion_ids):
        raise SynthesisError("the same receipt may not be supplied twice")

    loaded: list[IncludedCollection] = []
    for completion_id in completion_ids:
        store = find_collection_store(workspace, completion_id)
        loaded.append(
            load_verified_collection(
                store=store,
                completion_id=completion_id,
                corpus=corpus,
                annotation_protocol=annotation_protocol,
                allow_test_fixtures=allow_test_fixtures,
            )
        )

    annotator_ids = [entry.annotator_id for entry in loaded]
    if len(set(annotator_ids)) != len(annotator_ids):
        raise SynthesisError(
            "synthesis requires distinct annotators; a duplicate annotator ID was "
            "supplied"
        )
    included = tuple(sorted(loaded, key=lambda entry: entry.annotator_id))

    minimum = protocol.minimum_distinct_annotators_per_item
    if len(included) < minimum:
        raise SynthesisError(
            f"this protocol requires at least {minimum} distinct completed "
            f"assignments; {len(included)} were supplied"
        )

    directory = output_directory or (workspace / "synthesis" / "artifacts")
    store = FileSystemArtifactStore(directory)

    plan = SynthesisPlan(
        plan_id=(
            f"synthesis.{corpus.corpus_id}."
            + "-".join(entry.annotator_id for entry in included)
        ),
        synthesis_version=SYNTHESIS_VERSION,
        record_type=SYNTHESIS_RECORD_TYPE,
        synthesis_protocol_id=protocol.protocol_id,
        synthesis_protocol_version=protocol.protocol_version,
        synthesis_protocol_hash=protocol.artifact_hash,
        annotation_protocol_id=annotation_protocol.protocol_id,
        annotation_protocol_version=annotation_protocol.protocol_version,
        annotation_protocol_hash=annotation_protocol.artifact_hash,
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        corpus_hash=corpus.artifact_hash,
        minimum_distinct_annotators_per_item=minimum,
        annotator_ids=tuple(entry.annotator_id for entry in included),
        completion_refs=tuple(entry.completion_ref for entry in included),
        item_ids=corpus.item_ids,
        non_claims=SYNTHESIS_NON_CLAIMS,
        created_at=_iso(created_at or datetime.now(UTC)),
    )
    store.append(
        serialize_artifact(
            f"{protocol.protocol_id}:{protocol.protocol_version}",
            json.loads(protocol.canonical_payload.decode("utf-8")),
        )
    )
    plan_ref = store.append(serialize_artifact(plan.plan_id, plan))
    manifest_ref = store.append(
        serialize_artifact(
            f"{plan.plan_id}:receipt-manifest",
            {
                "plan_id": plan.plan_id,
                "ordered_annotator_ids": list(plan.annotator_ids),
                "completion_refs": [
                    {
                        "annotator_id": entry.annotator_id,
                        "assignment_id": entry.assignment_id,
                        "artifact_id": entry.completion_ref.artifact_id,
                        "artifact_hash": entry.completion_ref.artifact_hash,
                    }
                    for entry in included
                ],
            },
        )
    )

    resolution_refs: list[StoredArtifactRef] = []
    for entry in included:
        for item_id in corpus.item_ids:
            resolution_refs.append(
                store.append(
                    serialize_artifact(
                        f"{plan.plan_id}:{entry.annotator_id}:{item_id}:resolution",
                        entry.ancestry[item_id],
                    )
                )
            )

    items: list[ItemSynthesis] = []
    item_refs: list[StoredArtifactRef] = []
    for item_id in corpus.item_ids:
        synthesis = _item_synthesis(
            item_id=item_id,
            corpus=corpus,
            included=included,
            minimum_coverage=minimum,
        )
        items.append(synthesis)
        item_refs.append(
            store.append(
                serialize_artifact(f"{plan.plan_id}:{item_id}:synthesis", synthesis)
            )
        )

    lifecycle = CorpusLifecycleSummary(
        total_items=len(items),
        items_meeting_minimum_coverage=sum(
            1 for item in items if item.coverage_status == SUFFICIENT_COVERAGE
        ),
        items_with_insufficient_coverage=sum(
            1 for item in items if item.coverage_status == INSUFFICIENT_COVERAGE
        ),
        distinct_annotators=len(included),
        total_effective_responses=sum(item.distinct_annotators for item in items),
        total_superseded_records=sum(
            len(entry.ancestry[item_id].superseding_response_refs)
            for entry in included
            for item_id in corpus.item_ids
        ),
        total_abstentions=sum(item.abstention_count for item in items),
        total_unanswered=sum(item.unanswered_count for item in items),
    )
    lifecycle_ref = store.append(
        serialize_artifact(f"{plan.plan_id}:lifecycle", lifecycle)
    )

    completion = SynthesisCompletion(
        completion_id=f"{plan.plan_id}:completion",
        synthesis_version=SYNTHESIS_VERSION,
        record_type=SYNTHESIS_RECORD_TYPE,
        plan_id=plan.plan_id,
        plan_ref=plan_ref,
        receipt_manifest_ref=manifest_ref,
        resolution_refs=tuple(resolution_refs),
        item_synthesis_refs=tuple(item_refs),
        lifecycle_ref=lifecycle_ref,
        lifecycle=lifecycle,
        candidate_lifecycle_status="eligible_for_evaluation",
        non_claims=SYNTHESIS_NON_CLAIMS,
        # Derived from the same declared instant as the plan, so a synthesis over
        # identical inputs produces byte-identical artifacts and report.
        completed_at=plan.created_at,
    )
    completion_ref = store.append(
        serialize_artifact(completion.completion_id, completion)
    )

    _verify_stored_synthesis(
        store=store,
        completion=completion,
        completion_ref=completion_ref,
    )
    return VerifiedSynthesisReceipt(
        synthesis_version=SYNTHESIS_VERSION,
        artifact_directory=directory,
        protocol=protocol,
        plan=plan,
        plan_ref=plan_ref,
        completion=completion,
        completion_ref=completion_ref,
        included=included,
        items=tuple(items),
        lifecycle=lifecycle,
    )


def _verify_stored_synthesis(
    *,
    store: FileSystemArtifactStore,
    completion: SynthesisCompletion,
    completion_ref: StoredArtifactRef,
) -> None:
    """Re-read and rehash every stored synthesis artifact before it is trusted."""

    expected = serialize_artifact(completion.completion_id, completion)
    stored = store.get(
        completion_ref.artifact_id, expected_hash=completion_ref.artifact_hash
    )
    if stored.payload != expected.payload:
        raise ArtifactIntegrityError(
            "stored synthesis completion differs from the expected manifest"
        )
    for reference in (
        completion.plan_ref,
        completion.receipt_manifest_ref,
        completion.lifecycle_ref,
        *completion.resolution_refs,
        *completion.item_synthesis_refs,
    ):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def render_synthesis_report_markdown(receipt: VerifiedSynthesisReceipt) -> str:
    """Render one deterministic research report from reverified artifacts."""

    plan = receipt.plan
    lifecycle = receipt.lifecycle
    lines: list[str] = [
        "# Human-reference synthesis (research only)",
        "",
        "Human-reference synthesis describes the judgments collected under a "
        "declared protocol. It does not convert those judgments into truth.",
        "",
        "Disagreement is a result to preserve. It is not automatically a defect "
        "requiring majority rule or adjudication.",
        "",
        "This protocol permits descriptive human-human concordance. It does not "
        "establish correctness, population validity, or candidate fitness.",
        "",
        "## 1. Protocol, corpus, and plan identity",
        "",
        f"- Synthesis contract: `{receipt.synthesis_version}`",
        f"- Synthesis protocol: `{plan.synthesis_protocol_id}` @ "
        f"`{plan.synthesis_protocol_version}`",
        f"- Synthesis protocol hash: `{plan.synthesis_protocol_hash}`",
        f"- Annotation protocol: `{plan.annotation_protocol_id}` @ "
        f"`{plan.annotation_protocol_version}`",
        f"- Annotation protocol hash: `{plan.annotation_protocol_hash}`",
        f"- Corpus: `{plan.corpus_id}` @ `{plan.corpus_version}`",
        f"- Corpus hash: `{plan.corpus_hash}`",
        f"- Synthesis plan: `{plan.plan_id}`",
        f"- Declared minimum coverage: "
        f"{plan.minimum_distinct_annotators_per_item} distinct completed assignments "
        "per item",
        f"- Candidate lifecycle: `{receipt.completion.candidate_lifecycle_status}` "
        "(unchanged by this synthesis)",
        "",
        "## 2. Included pseudonymous assignments",
        "",
    ]
    for entry in receipt.included:
        lines.append(
            f"- `{entry.annotator_id}` → assignment `{entry.assignment_id}`, "
            f"receipt `{entry.completion_ref.artifact_id}` "
            f"(`{entry.completion_ref.artifact_hash}`)"
        )
    lines.extend(
        [
            "",
            "Annotator identities are locally chosen pseudonyms. No mapping from a "
            "pseudonym to a real person is created, requested, inferred, or stored.",
            "",
            "## 3. Coverage and completion lifecycle",
            "",
            f"- Total items: {lifecycle.total_items}",
            f"- Items meeting declared minimum coverage: "
            f"{lifecycle.items_meeting_minimum_coverage}",
            f"- Items with `{INSUFFICIENT_COVERAGE}`: "
            f"{lifecycle.items_with_insufficient_coverage}",
            f"- Distinct annotators: {lifecycle.distinct_annotators}",
            f"- Effective responses: {lifecycle.total_effective_responses}",
            f"- Superseded records preserved: {lifecycle.total_superseded_records}",
            f"- Abstentions: {lifecycle.total_abstentions}",
            f"- Unanswered: {lifecycle.total_unanswered}",
            "",
            lifecycle.notes,
            "",
            "## 4. Per-item descriptive synthesis",
            "",
            "No section below chooses, marks, or implies a preferred human response.",
            "",
        ]
    )

    for item in receipt.items:
        lines.extend(
            [
                f"### {item.item_id}",
                "",
                f"- Content hash: `{item.content_hash}`",
                f"- Distinct annotators: {item.distinct_annotators}",
                f"- Coverage status: `{item.coverage_status}`",
                "",
                "Exact text:",
                "",
                f"> {item.text}",
                "",
                "Response distribution (every option, including zero observations):",
                "",
                "| Response option | Count |",
                "| --- | --- |",
            ]
        )
        lines.extend(
            f"| `{label.value}` | {item.valence_distribution.counts[label.value]} |"
            for label in ValenceLabel
        )
        lines.extend(
            [
                "",
                f"- Abstentions: {item.abstention_count} "
                "(a separate response category, never numerically encoded)",
            ]
        )
        if item.abstention_reason_counts:
            lines.extend(
                f"  - `{reason}`: {count}"
                for reason, count in sorted(item.abstention_reason_counts.items())
            )
        else:
            lines.append("  - no abstention reasons recorded")
        lines.extend(
            [
                f"- Unanswered: {item.unanswered_count}",
                "",
                "Context sufficiency, ambiguity, and certainty are recorded "
                "separately and none is derived from another:",
                "",
            ]
        )
        lines.extend(
            f"- Context sufficiency `{key}`: {value}"
            for key, value in sorted(item.context_sufficiency_counts.items())
        )
        lines.extend(
            f"- Perceived ambiguity `{key}`: {value}"
            for key, value in sorted(item.ambiguity_counts.items())
        )
        lines.extend(
            f"- Self-reported certainty `{key}`: {value}"
            for key, value in sorted(item.certainty_counts.items())
        )
        lines.extend(
            [
                f"- Rationale provided: {item.rationale_present_count}",
                f"- Supporting spans provided: {item.supporting_span_present_count}",
                "",
                "Pairwise concordance, numerator and denominator preserved:",
                "",
                f"- `{item.concordance_including_abstention.label}`: "
                f"{item.concordance_including_abstention.agreeing_pairs} of "
                f"{item.concordance_including_abstention.compared_pairs} pairs",
                f"- `{item.concordance_non_abstaining.label}`: "
                f"{item.concordance_non_abstaining.agreeing_pairs} of "
                f"{item.concordance_non_abstaining.compared_pairs} pairs",
                "",
                "Ordinal-distance histogram for non-abstaining pairs. Ordinal "
                "positions are a serialization convenience for computing a distance "
                "between two categorical responses; they are not interval-scale "
                "truth, and no mean response label is derived from them:",
                "",
                "| Distance | Pairs |",
                "| --- | --- |",
            ]
        )
        lines.extend(
            f"| {bucket} | {item.ordinal_distance_histogram[str(bucket)]} |"
            for bucket in ORDINAL_DISTANCE_BUCKETS
        )
        lines.append("")
        lines.extend(
            f"- Source response: `{reference.artifact_id}` "
            f"(`{reference.artifact_hash}`)"
            for reference in item.response_refs
        )
        lines.append("")

    lines.extend(["## 5. Supersession ancestry", ""])
    any_supersession = False
    for entry in receipt.included:
        for item_id in plan.item_ids:
            ancestry = entry.ancestry[item_id]
            if not ancestry.superseding_response_refs:
                continue
            any_supersession = True
            lines.extend(
                [
                    f"- `{entry.annotator_id}` / `{item_id}`: original "
                    f"`{ancestry.original_response_ref.artifact_id}` preserved; "
                    f"effective `{ancestry.effective_response_ref.artifact_id}`",
                ]
            )
            lines.extend(
                f"  - superseded by `{reference.artifact_id}` because: {reason}"
                for reference, reason in zip(
                    ancestry.superseding_response_refs,
                    ancestry.supersession_reasons,
                    strict=True,
                )
            )
    if not any_supersession:
        lines.append("- No response was superseded in any included collection.")

    lines.extend(
        [
            "",
            "Every superseded record remains stored and readable. None is deleted "
            "or hidden.",
            "",
            "## 6. Immutable references",
            "",
            f"- `synthesis-plan` → `{receipt.plan_ref.artifact_id}` "
            f"(`{receipt.plan_ref.artifact_hash}`)",
            f"- `receipt-manifest` → "
            f"`{receipt.completion.receipt_manifest_ref.artifact_id}` "
            f"(`{receipt.completion.receipt_manifest_ref.artifact_hash}`)",
            f"- `corpus-lifecycle` → `{receipt.completion.lifecycle_ref.artifact_id}` "
            f"(`{receipt.completion.lifecycle_ref.artifact_hash}`)",
            f"- `synthesis-completion` → `{receipt.completion_ref.artifact_id}` "
            f"(`{receipt.completion_ref.artifact_hash}`)",
            f"- Effective-response resolution records: "
            f"{len(receipt.completion.resolution_refs)}",
            f"- Per-item synthesis records: "
            f"{len(receipt.completion.item_synthesis_refs)}",
            "",
            "## 7. Interpretation boundary and non-claims",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in receipt.completion.non_claims)
    lines.extend(
        [
            "",
            "This report is derived presentation. The canonical stored artifacts "
            "remain controlling. Binding human-reference synthesis to a blinded "
            "analyzer evaluation requires a separate, later, explicitly accepted "
            "protocol that does not exist yet.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.human_reference_synthesis",
        description=(
            "RESEARCH ONLY. Descriptively synthesize verified human-reference "
            "collections while preserving every independent judgment. No consensus, "
            "gold label, adjudication, ranking, or analyzer comparison is produced."
        ),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".ctrt") / "human-reference",
        help="Directory containing one append-only store per annotator.",
    )
    parser.add_argument(
        "--receipt",
        action="append",
        default=[],
        dest="receipts",
        required=True,
        help="Verified collection receipt ID. Repeat once per annotator.",
    )
    parser.add_argument("--output", type=Path, help="Optional Markdown output path.")
    parser.add_argument(
        "--synthesis-protocol", type=Path, default=DEFAULT_SYNTHESIS_PROTOCOL
    )
    parser.add_argument(
        "--annotation-protocol", type=Path, default=DEFAULT_ANNOTATION_PROTOCOL
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the research-only descriptive synthesis."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        receipt = run_human_reference_synthesis(
            workspace=arguments.workspace,
            completion_ids=tuple(arguments.receipts),
            synthesis_protocol_path=arguments.synthesis_protocol,
            annotation_protocol_path=arguments.annotation_protocol,
            corpus_path=arguments.corpus,
        )
    except (SynthesisError, HumanReferenceError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"human-reference synthesis failed: {exc}\n")
        return 2
    markdown = render_synthesis_report_markdown(receipt)
    if arguments.output is None:
        sys.stdout.write(markdown)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(markdown, encoding="utf-8")
        sys.stdout.write(f"Wrote synthesis report to {arguments.output}\n")
    sys.stderr.write(f"Artifact store: {receipt.artifact_directory}\n")
    sys.stderr.write(
        "Research only. Descriptive synthesis does not convert judgments into "
        "truth.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_ANNOTATION_PROTOCOL",
    "DEFAULT_CORPUS",
    "DEFAULT_SYNTHESIS_PROTOCOL",
    "INSUFFICIENT_COVERAGE",
    "ORDINAL_DISTANCE_BUCKETS",
    "SUFFICIENT_COVERAGE",
    "SYNTHESIS_NON_CLAIMS",
    "SYNTHESIS_RECORD_TYPE",
    "SYNTHESIS_VERSION",
    "ConcordancePair",
    "CorpusLifecycleSummary",
    "IncludedCollection",
    "ItemSynthesis",
    "SupersessionAncestry",
    "SynthesisCompletion",
    "SynthesisError",
    "SynthesisPlan",
    "SynthesisProtocol",
    "ValenceDistribution",
    "VerifiedSynthesisReceipt",
    "find_collection_store",
    "is_test_fixture_collection",
    "load_verified_collection",
    "main",
    "mark_test_fixture_collection",
    "render_synthesis_report_markdown",
    "run_human_reference_synthesis",
]
