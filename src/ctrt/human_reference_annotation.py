"""Blinded, append-only collection of independent human-reference annotations.

Human-reference annotations preserve independent judgments under a declared
protocol. They do not become ground truth merely because humans supplied them.

Disagreement, ambiguity, insufficient context, and abstention are evidence to
preserve, not errors to erase.

This module collects annotations only. It computes no majority, average,
median, consensus, adjudicated label, agreement statistic, merged human score,
or gold answer, and it never runs, names, or references an analyzer candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import gcd
from pathlib import Path
from typing import cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    AbstentionReason,
    AnnotationProtocol,
    ContextSufficiency,
    EvaluationCorpus,
    HumanReferenceError,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    SupportingSpan,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
    validate_annotator_id,
    validate_spans,
)
from ctrt.serialization import serialize_artifact

COLLECTION_VERSION = "ctrt-human-reference-collection@0.1.0"
ASSIGNMENT_METHOD = "deterministic-rotation-stride"
ASSIGNMENT_METHOD_VERSION = "0.1.0"

COLLECTION_NON_CLAIMS = (
    "Human-reference annotations preserve independent judgments under a declared "
    "protocol. They do not become ground truth merely because humans supplied them.",
    "Disagreement, ambiguity, insufficient context, and abstention are evidence to "
    "preserve, not errors to erase.",
    "This collection computes no majority, average, median, consensus, adjudicated "
    "label, inter-annotator agreement statistic, merged human score, or gold answer.",
    "This collection does not run, name, compare against, evaluate, or select any "
    "analyzer candidate, and the candidate lifecycle is unchanged.",
    "The evaluation corpus is a small repository-authored pilot. It does not "
    "represent any population of content, authors, or platforms.",
    "Self-reported annotator certainty is a statement about a person. It is never "
    "analyzer confidence and never populates any instrument-confidence field.",
    "Lifecycle counts describe collection progress only. They are not a measure of "
    "annotation quality, correctness, or agreement.",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_CORPUS = (
    _repo_root() / "docs" / "corpora" / "human-reference-sentiment.v0.1.0.json"
)
DEFAULT_PROTOCOL = (
    _repo_root()
    / "docs"
    / "protocols"
    / "human-reference-sentiment-valence.v0.1.0.json"
)


def _load_document(path: Path, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HumanReferenceError(f"unable to read {field_name} from {path}") from exc
    if not isinstance(value, Mapping):
        raise HumanReferenceError(f"{field_name} must be a JSON object")
    return cast(Mapping[str, object], value)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise HumanReferenceError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def assignment_order(
    *,
    item_ids: tuple[str, ...],
    corpus_hash: str,
    annotator_id: str,
) -> tuple[str, ...]:
    """Return a deterministic per-annotator permutation of the frozen items.

    The offset and stride are derived with SHA-256 rather than Python's
    process-randomized ``hash()``, so the same annotator always receives the
    same order and different annotators generally receive different orders.
    The corpus identity itself is unchanged by this reordering.
    """

    count = len(item_ids)
    if count == 0:
        raise HumanReferenceError("assignment requires a non-empty corpus")
    seed = hashlib.sha256(
        "|".join(
            (ASSIGNMENT_METHOD, ASSIGNMENT_METHOD_VERSION, corpus_hash, annotator_id)
        ).encode("utf-8")
    ).digest()
    value = int.from_bytes(seed, "big")
    offset = value % count
    # A stride co-prime with the item count guarantees a full permutation.
    stride = (value // count) % count + 1
    while gcd(stride, count) != 1:
        stride += 1
        if stride > count:
            stride = 1
    return tuple(item_ids[(offset + index * stride) % count] for index in range(count))


@dataclass(frozen=True, slots=True)
class AnnotationPacket:
    """Exactly what an annotator is shown for one item.

    This structure deliberately has no field for a candidate, an analyzer, an
    analyzer output, a characterization outcome, or a registry status, so a
    packet cannot carry them.
    """

    assignment_id: str
    protocol_id: str
    protocol_version: str
    task_statement: str
    instructions: tuple[str, ...]
    valence_options: tuple[ValenceLabel, ...]
    position: int
    total_items: int
    item_id: str
    text: str
    language: str

    def __post_init__(self) -> None:
        if self.position < 0 or self.position >= self.total_items:
            raise HumanReferenceError("packet position must fall inside the assignment")
        if not self.text.strip():
            raise HumanReferenceError("packet text must not be empty")
        if self.valence_options != tuple(ValenceLabel):
            raise HumanReferenceError("packet must offer the exact versioned scale")


@dataclass(frozen=True, slots=True)
class AnnotatorAssignment:
    """One deterministic, immutable assignment of frozen items to one annotator."""

    assignment_id: str
    collection_version: str
    annotator_id: str
    corpus_id: str
    corpus_version: str
    corpus_hash: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    item_ids: tuple[str, ...]
    assignment_method: str
    assignment_method_version: str
    created_at: str

    def __post_init__(self) -> None:
        validate_annotator_id(self.annotator_id)
        if self.collection_version != COLLECTION_VERSION:
            raise HumanReferenceError("unsupported collection version")
        if not self.item_ids:
            raise HumanReferenceError("assignment requires at least one item")
        if len(self.item_ids) != len(set(self.item_ids)):
            raise HumanReferenceError("assignment item IDs must be unique")

    def verify_against(
        self,
        *,
        corpus: EvaluationCorpus,
        protocol: AnnotationProtocol,
    ) -> None:
        """Fail closed when the assignment drifts from its frozen inputs."""

        if self.corpus_hash != corpus.artifact_hash:
            raise HumanReferenceError("assignment corpus hash does not match the corpus")
        if self.protocol_hash != protocol.artifact_hash:
            raise HumanReferenceError(
                "assignment protocol hash does not match the protocol"
            )
        if set(self.item_ids) != set(corpus.item_ids):
            raise HumanReferenceError(
                "assignment items differ from the frozen corpus items"
            )
        expected = assignment_order(
            item_ids=corpus.item_ids,
            corpus_hash=corpus.artifact_hash,
            annotator_id=self.annotator_id,
        )
        if self.item_ids != expected:
            raise HumanReferenceError(
                "assignment item order differs from its deterministic generation"
            )


@dataclass(frozen=True, slots=True)
class AnnotationResponse:
    """One preserved independent judgment. Never mutated, never replaced."""

    response_id: str
    collection_version: str
    assignment_id: str
    annotator_id: str
    item_id: str
    item_content_hash: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    sequence: int
    valence_label: ValenceLabel
    abstained: bool
    abstention_reason: AbstentionReason | None
    context_sufficiency: ContextSufficiency
    perceived_ambiguity: PerceivedAmbiguity
    self_reported_certainty: SelfReportedCertainty | None
    rationale: str | None
    supporting_spans: tuple[SupportingSpan, ...]
    supersedes_response_id: str | None
    supersession_reason: str | None
    recorded_at: str

    def __post_init__(self) -> None:
        validate_annotator_id(self.annotator_id)
        if self.collection_version != COLLECTION_VERSION:
            raise HumanReferenceError("unsupported collection version")
        if self.sequence < 0:
            raise HumanReferenceError("response sequence must be non-negative")
        is_abstention = self.valence_label is ABSTENTION_LABEL
        if self.abstained != is_abstention:
            raise HumanReferenceError(
                "abstained must be true exactly when the valence label is the "
                "abstention option"
            )
        if is_abstention and self.abstention_reason is None:
            raise HumanReferenceError("an abstention requires a recorded reason")
        if not is_abstention and self.abstention_reason is not None:
            raise HumanReferenceError(
                "a valence judgment may not carry an abstention reason"
            )
        if self.rationale is not None and not self.rationale.strip():
            raise HumanReferenceError("rationale must be non-empty when provided")
        if (self.supersedes_response_id is None) != (self.supersession_reason is None):
            raise HumanReferenceError(
                "a supersession requires both a predecessor and a reason"
            )
        if self.sequence == 0 and self.supersedes_response_id is not None:
            raise HumanReferenceError("an original response may not supersede anything")
        if self.sequence > 0 and self.supersedes_response_id is None:
            raise HumanReferenceError(
                "a later response must name the exact record it supersedes"
            )


@dataclass(frozen=True, slots=True)
class CollectionCounts:
    """Collection progress only. Never a measure of annotation quality."""

    total_items: int
    answered_with_valence: int
    abstained: int
    unanswered: int
    superseded_records: int
    notes: str = (
        "Lifecycle information only. These counts describe collection progress and "
        "are not a measure of annotation quality, correctness, or agreement."
    )

    def __post_init__(self) -> None:
        values = (
            self.total_items,
            self.answered_with_valence,
            self.abstained,
            self.unanswered,
            self.superseded_records,
        )
        if any(value < 0 for value in values):
            raise HumanReferenceError("collection counts must be non-negative")
        if self.answered_with_valence + self.abstained + self.unanswered != (
            self.total_items
        ):
            raise HumanReferenceError("collection counts must partition the assignment")


@dataclass(frozen=True, slots=True)
class AssignmentCompletion:
    """Marker written only when every assigned item has a preserved response."""

    completion_id: str
    collection_version: str
    assignment_id: str
    annotator_id: str
    corpus_hash: str
    protocol_hash: str
    item_ids: tuple[str, ...]
    response_refs: tuple[StoredArtifactRef, ...]
    counts: CollectionCounts
    non_claims: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if self.counts.unanswered != 0:
            raise HumanReferenceError(
                "completion requires every assigned item to be answered or "
                "explicitly abstained"
            )
        if len(self.response_refs) != len(self.item_ids):
            raise HumanReferenceError(
                "completion requires one current response per assigned item"
            )
        if self.non_claims != COLLECTION_NON_CLAIMS:
            raise HumanReferenceError("completion must preserve the declared non-claims")


@dataclass(frozen=True, slots=True)
class VerifiedCollectionReceipt:
    """Returned only after every stored artifact re-verified on read."""

    collection_version: str
    workspace: Path
    artifact_directory: Path
    assignment: AnnotatorAssignment
    assignment_ref: StoredArtifactRef
    protocol_ref: StoredArtifactRef
    corpus_ref: StoredArtifactRef
    completion: AssignmentCompletion
    completion_ref: StoredArtifactRef
    responses: tuple[AnnotationResponse, ...]
    response_refs: tuple[StoredArtifactRef, ...]

    def __post_init__(self) -> None:
        if self.collection_version != COLLECTION_VERSION:
            raise HumanReferenceError("unsupported collection version")


def _response_artifact_id(assignment_id: str, item_id: str, sequence: int) -> str:
    return f"{assignment_id}:{item_id}:response:{sequence}"


class AnnotationSession:
    """Append-only collection session for one annotator and one assignment.

    Nothing here mutates or deletes a stored response. A correction is recorded
    as a new superseding record naming its exact predecessor.
    """

    def __init__(
        self,
        *,
        store: FileSystemArtifactStore,
        corpus: EvaluationCorpus,
        protocol: AnnotationProtocol,
        assignment: AnnotatorAssignment,
    ) -> None:
        assignment.verify_against(corpus=corpus, protocol=protocol)
        self._store = store
        self._corpus = corpus
        self._protocol = protocol
        self._assignment = assignment

    @property
    def assignment(self) -> AnnotatorAssignment:
        """Return the immutable assignment this session collects for."""

        return self._assignment

    def _stored_chain(self, item_id: str) -> tuple[AnnotationResponse, ...]:
        """Reconstruct one item's append-only response chain from storage."""

        chain: list[AnnotationResponse] = []
        sequence = 0
        while True:
            artifact_id = _response_artifact_id(
                self._assignment.assignment_id, item_id, sequence
            )
            try:
                artifact = self._store.get(artifact_id)
            except ArtifactNotFoundError:
                return tuple(chain)
            chain.append(_response_from_artifact_text(artifact.text))
            sequence += 1

    def responses_for(self, item_id: str) -> tuple[AnnotationResponse, ...]:
        """Return every preserved record for one item, oldest first."""

        return self._stored_chain(item_id)

    def current_response(self, item_id: str) -> AnnotationResponse | None:
        """Return the latest record for an item, or None when never answered."""

        chain = self._stored_chain(item_id)
        return chain[-1] if chain else None

    def answered_item_ids(self) -> tuple[str, ...]:
        """Return assigned items that already carry a preserved response."""

        return tuple(
            item_id
            for item_id in self._assignment.item_ids
            if self.current_response(item_id) is not None
        )

    def unanswered_item_ids(self) -> tuple[str, ...]:
        """Return assigned items with no preserved response yet.

        Never answered is a distinct state from a recorded abstention.
        """

        answered = set(self.answered_item_ids())
        return tuple(
            item_id for item_id in self._assignment.item_ids if item_id not in answered
        )

    def next_packet(self) -> AnnotationPacket | None:
        """Return the next unanswered item's packet, resuming exactly."""

        remaining = self.unanswered_item_ids()
        if not remaining:
            return None
        return self.packet_for(remaining[0])

    def packet_for(self, item_id: str) -> AnnotationPacket:
        """Return the blinded packet for one assigned item."""

        if item_id not in self._assignment.item_ids:
            raise HumanReferenceError(f"item {item_id!r} is not in this assignment")
        item = self._corpus.item(item_id)
        return AnnotationPacket(
            assignment_id=self._assignment.assignment_id,
            protocol_id=self._protocol.protocol_id,
            protocol_version=self._protocol.protocol_version,
            task_statement=self._protocol.task_statement,
            instructions=self._protocol.instructions,
            valence_options=tuple(ValenceLabel),
            position=self._assignment.item_ids.index(item_id),
            total_items=len(self._assignment.item_ids),
            item_id=item.item_id,
            text=item.text,
            language=item.language,
        )

    def record(
        self,
        *,
        item_id: str,
        valence_label: ValenceLabel,
        context_sufficiency: ContextSufficiency,
        perceived_ambiguity: PerceivedAmbiguity,
        abstention_reason: AbstentionReason | None = None,
        self_reported_certainty: SelfReportedCertainty | None = None,
        rationale: str | None = None,
        supporting_spans: tuple[SupportingSpan, ...] = (),
        recorded_at: datetime | None = None,
    ) -> tuple[AnnotationResponse, StoredArtifactRef]:
        """Append one original response. Refuses to overwrite an existing one."""

        if self.current_response(item_id) is not None:
            raise HumanReferenceError(
                f"item {item_id!r} already has a preserved response; record a "
                "superseding response instead of overwriting it"
            )
        return self._append(
            item_id=item_id,
            sequence=0,
            valence_label=valence_label,
            context_sufficiency=context_sufficiency,
            perceived_ambiguity=perceived_ambiguity,
            abstention_reason=abstention_reason,
            self_reported_certainty=self_reported_certainty,
            rationale=rationale,
            supporting_spans=supporting_spans,
            supersedes=None,
            supersession_reason=None,
            recorded_at=recorded_at,
        )

    def supersede(
        self,
        *,
        item_id: str,
        reason: str,
        valence_label: ValenceLabel,
        context_sufficiency: ContextSufficiency,
        perceived_ambiguity: PerceivedAmbiguity,
        abstention_reason: AbstentionReason | None = None,
        self_reported_certainty: SelfReportedCertainty | None = None,
        rationale: str | None = None,
        supporting_spans: tuple[SupportingSpan, ...] = (),
        recorded_at: datetime | None = None,
    ) -> tuple[AnnotationResponse, StoredArtifactRef]:
        """Append a correction that preserves the original and names it."""

        if not reason.strip():
            raise HumanReferenceError("a supersession requires a recorded reason")
        chain = self._stored_chain(item_id)
        if not chain:
            raise HumanReferenceError(
                f"item {item_id!r} has no predecessor response to supersede"
            )
        predecessor = chain[-1]
        return self._append(
            item_id=item_id,
            sequence=len(chain),
            valence_label=valence_label,
            context_sufficiency=context_sufficiency,
            perceived_ambiguity=perceived_ambiguity,
            abstention_reason=abstention_reason,
            self_reported_certainty=self_reported_certainty,
            rationale=rationale,
            supporting_spans=supporting_spans,
            supersedes=predecessor.response_id,
            supersession_reason=reason,
            recorded_at=recorded_at,
        )

    def _append(
        self,
        *,
        item_id: str,
        sequence: int,
        valence_label: ValenceLabel,
        context_sufficiency: ContextSufficiency,
        perceived_ambiguity: PerceivedAmbiguity,
        abstention_reason: AbstentionReason | None,
        self_reported_certainty: SelfReportedCertainty | None,
        rationale: str | None,
        supporting_spans: tuple[SupportingSpan, ...],
        supersedes: str | None,
        supersession_reason: str | None,
        recorded_at: datetime | None,
    ) -> tuple[AnnotationResponse, StoredArtifactRef]:
        if item_id not in self._assignment.item_ids:
            raise HumanReferenceError(f"item {item_id!r} is not in this assignment")
        item = self._corpus.item(item_id)
        validate_spans(supporting_spans, item.text)
        response = AnnotationResponse(
            response_id=_response_artifact_id(
                self._assignment.assignment_id, item_id, sequence
            ),
            collection_version=COLLECTION_VERSION,
            assignment_id=self._assignment.assignment_id,
            annotator_id=self._assignment.annotator_id,
            item_id=item_id,
            item_content_hash=item.content_hash,
            protocol_id=self._protocol.protocol_id,
            protocol_version=self._protocol.protocol_version,
            protocol_hash=self._protocol.artifact_hash,
            sequence=sequence,
            valence_label=valence_label,
            abstained=valence_label is ABSTENTION_LABEL,
            abstention_reason=abstention_reason,
            context_sufficiency=context_sufficiency,
            perceived_ambiguity=perceived_ambiguity,
            self_reported_certainty=self_reported_certainty,
            rationale=rationale,
            supporting_spans=supporting_spans,
            supersedes_response_id=supersedes,
            supersession_reason=supersession_reason,
            recorded_at=_iso(recorded_at or datetime.now(UTC)),
        )
        artifact = serialize_artifact(response.response_id, response)
        reference = self._store.append(artifact)
        stored = self._store.get(reference.artifact_id, expected_hash=reference.artifact_hash)
        if stored.payload != artifact.payload:
            raise ArtifactIntegrityError(
                "stored annotation differs from the recorded response"
            )
        return response, reference

    def counts(self) -> CollectionCounts:
        """Return collection progress only."""

        answered_with_valence = 0
        abstained = 0
        unanswered = 0
        superseded = 0
        for item_id in self._assignment.item_ids:
            chain = self._stored_chain(item_id)
            if not chain:
                unanswered += 1
                continue
            superseded += len(chain) - 1
            if chain[-1].abstained:
                abstained += 1
            else:
                answered_with_valence += 1
        return CollectionCounts(
            total_items=len(self._assignment.item_ids),
            answered_with_valence=answered_with_valence,
            abstained=abstained,
            unanswered=unanswered,
            superseded_records=superseded,
        )

    def complete(
        self,
        *,
        completed_at: datetime | None = None,
    ) -> tuple[AssignmentCompletion, StoredArtifactRef]:
        """Write the completion marker only when nothing remains unanswered."""

        counts = self.counts()
        if counts.unanswered:
            raise HumanReferenceError(
                f"{counts.unanswered} assigned items are still unanswered; every item "
                "must carry a valence judgment or an explicit abstention"
            )
        references: list[StoredArtifactRef] = []
        for item_id in self._assignment.item_ids:
            current = self.current_response(item_id)
            if current is None:  # pragma: no cover - counts already guarantee this
                raise HumanReferenceError(f"item {item_id!r} lost its response")
            artifact = self._store.get(current.response_id)
            references.append(
                StoredArtifactRef(
                    artifact_id=artifact.artifact_id,
                    artifact_hash=artifact.artifact_hash,
                )
            )
        completion = AssignmentCompletion(
            completion_id=f"{self._assignment.assignment_id}:completion",
            collection_version=COLLECTION_VERSION,
            assignment_id=self._assignment.assignment_id,
            annotator_id=self._assignment.annotator_id,
            corpus_hash=self._corpus.artifact_hash,
            protocol_hash=self._protocol.artifact_hash,
            item_ids=self._assignment.item_ids,
            response_refs=tuple(references),
            counts=counts,
            non_claims=COLLECTION_NON_CLAIMS,
            completed_at=_iso(completed_at or datetime.now(UTC)),
        )
        reference = self._store.append(
            serialize_artifact(completion.completion_id, completion)
        )
        return completion, reference


def _response_from_artifact_text(text: str) -> AnnotationResponse:
    document = cast(dict[str, object], json.loads(text))
    spans = cast(list[dict[str, int]], document.get("supporting_spans", []))
    reason = document.get("abstention_reason")
    certainty = document.get("self_reported_certainty")
    supersedes = document.get("supersedes_response_id")
    supersession_reason = document.get("supersession_reason")
    rationale = document.get("rationale")
    return AnnotationResponse(
        response_id=cast(str, document["response_id"]),
        collection_version=cast(str, document["collection_version"]),
        assignment_id=cast(str, document["assignment_id"]),
        annotator_id=cast(str, document["annotator_id"]),
        item_id=cast(str, document["item_id"]),
        item_content_hash=cast(str, document["item_content_hash"]),
        protocol_id=cast(str, document["protocol_id"]),
        protocol_version=cast(str, document["protocol_version"]),
        protocol_hash=cast(str, document["protocol_hash"]),
        sequence=cast(int, document["sequence"]),
        valence_label=ValenceLabel(cast(str, document["valence_label"])),
        abstained=cast(bool, document["abstained"]),
        abstention_reason=(
            AbstentionReason(cast(str, reason)) if reason is not None else None
        ),
        context_sufficiency=ContextSufficiency(
            cast(str, document["context_sufficiency"])
        ),
        perceived_ambiguity=PerceivedAmbiguity(
            cast(str, document["perceived_ambiguity"])
        ),
        self_reported_certainty=(
            SelfReportedCertainty(cast(str, certainty)) if certainty is not None else None
        ),
        rationale=cast(str, rationale) if rationale is not None else None,
        supporting_spans=tuple(
            SupportingSpan(start=item["start"], end=item["end"]) for item in spans
        ),
        supersedes_response_id=cast(str, supersedes) if supersedes is not None else None,
        supersession_reason=(
            cast(str, supersession_reason) if supersession_reason is not None else None
        ),
        recorded_at=cast(str, document["recorded_at"]),
    )


def open_assignment(
    *,
    workspace: Path,
    annotator_id: str,
    corpus_path: Path = DEFAULT_CORPUS,
    protocol_path: Path = DEFAULT_PROTOCOL,
    created_at: datetime | None = None,
) -> tuple[AnnotationSession, FileSystemArtifactStore]:
    """Create or resume one annotator's deterministic, immutable assignment."""

    validate_annotator_id(annotator_id)
    corpus = load_evaluation_corpus(_load_document(corpus_path, "evaluation corpus"))
    protocol = load_annotation_protocol(
        _load_document(protocol_path, "annotation protocol")
    )
    if corpus.dimension_id != protocol.dimension_id:
        raise HumanReferenceError("corpus and protocol declare different dimensions")

    artifact_directory = workspace / annotator_id / "artifacts"
    store = FileSystemArtifactStore(artifact_directory)
    assignment = AnnotatorAssignment(
        assignment_id=f"assignment.{corpus.corpus_id}.{annotator_id}",
        collection_version=COLLECTION_VERSION,
        annotator_id=annotator_id,
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        corpus_hash=corpus.artifact_hash,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_hash=protocol.artifact_hash,
        item_ids=assignment_order(
            item_ids=corpus.item_ids,
            corpus_hash=corpus.artifact_hash,
            annotator_id=annotator_id,
        ),
        assignment_method=ASSIGNMENT_METHOD,
        assignment_method_version=ASSIGNMENT_METHOD_VERSION,
        created_at=_iso(created_at or datetime.now(UTC)),
    )
    return (
        AnnotationSession(
            store=store,
            corpus=corpus,
            protocol=protocol,
            assignment=assignment,
        ),
        store,
    )


def persist_collection_inputs(
    store: FileSystemArtifactStore,
    *,
    corpus: EvaluationCorpus,
    protocol: AnnotationProtocol,
    assignment: AnnotatorAssignment,
) -> tuple[StoredArtifactRef, StoredArtifactRef, StoredArtifactRef]:
    """Persist protocol, corpus, and assignment as separate canonical artifacts."""

    protocol_ref = store.append(
        serialize_artifact(
            f"{protocol.protocol_id}:{protocol.protocol_version}",
            json.loads(protocol.canonical_payload.decode("utf-8")),
        )
    )
    corpus_ref = store.append(
        serialize_artifact(
            f"{corpus.corpus_id}:{corpus.corpus_version}",
            json.loads(corpus.canonical_payload.decode("utf-8")),
        )
    )
    assignment_ref = store.append(
        serialize_artifact(assignment.assignment_id, assignment)
    )
    return protocol_ref, corpus_ref, assignment_ref


def verify_collection(
    *,
    store: FileSystemArtifactStore,
    session: AnnotationSession,
    corpus: EvaluationCorpus,
    protocol: AnnotationProtocol,
    completion: AssignmentCompletion,
    completion_ref: StoredArtifactRef,
    protocol_ref: StoredArtifactRef,
    corpus_ref: StoredArtifactRef,
    assignment_ref: StoredArtifactRef,
) -> VerifiedCollectionReceipt:
    """Re-read and rehash every stored artifact before anything is trusted."""

    for reference in (protocol_ref, corpus_ref, assignment_ref, completion_ref):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)

    expected = serialize_artifact(completion.completion_id, completion)
    stored = store.get(
        completion_ref.artifact_id, expected_hash=completion_ref.artifact_hash
    )
    if stored.payload != expected.payload:
        raise ArtifactIntegrityError(
            "stored assignment completion differs from the expected manifest"
        )

    responses: list[AnnotationResponse] = []
    references: list[StoredArtifactRef] = []
    for item_id, reference in zip(
        completion.item_ids, completion.response_refs, strict=True
    ):
        artifact = store.get(
            reference.artifact_id, expected_hash=reference.artifact_hash
        )
        response = _response_from_artifact_text(artifact.text)
        if response.item_id != item_id:
            raise ArtifactIntegrityError(
                "stored response item identity differs from the completion order"
            )
        if response.item_content_hash != corpus.item(item_id).content_hash:
            raise ArtifactIntegrityError(
                "stored response references different item bytes than the corpus"
            )
        if response.protocol_hash != protocol.artifact_hash:
            raise ArtifactIntegrityError(
                "stored response was recorded under a different protocol"
            )
        responses.append(response)
        references.append(reference)

    return VerifiedCollectionReceipt(
        collection_version=COLLECTION_VERSION,
        workspace=store.root.parent.parent,
        artifact_directory=store.root,
        assignment=session.assignment,
        assignment_ref=assignment_ref,
        protocol_ref=protocol_ref,
        corpus_ref=corpus_ref,
        completion=completion,
        completion_ref=completion_ref,
        responses=tuple(responses),
        response_refs=tuple(references),
    )


def _optional(value: object) -> str:
    return "not provided" if value is None else str(value)


def render_collection_report_markdown(
    *,
    receipt: VerifiedCollectionReceipt,
    corpus: EvaluationCorpus,
    protocol: AnnotationProtocol,
    session: AnnotationSession,
) -> str:
    """Render one deterministic research report from reverified stored evidence."""

    assignment = receipt.assignment
    counts = receipt.completion.counts
    lines: list[str] = [
        "# Human-reference annotation collection (research only)",
        "",
        "Human-reference annotations preserve independent judgments under a declared "
        "protocol. They do not become ground truth merely because humans supplied "
        "them.",
        "",
        "Disagreement, ambiguity, insufficient context, and abstention are evidence "
        "to preserve, not errors to erase.",
        "",
        "## 1. Protocol and corpus identity",
        "",
        f"- Collection contract: `{receipt.collection_version}`",
        f"- Protocol: `{protocol.protocol_id}` @ `{protocol.protocol_version}`",
        f"- Protocol hash: `{protocol.artifact_hash}`",
        f"- Response scale: `{protocol.scale_id}` @ `{protocol.scale_version}`",
        f"- Dimension: `{protocol.dimension_id}` @ `{protocol.dimension_version}`",
        f"- Corpus: `{corpus.corpus_id}` @ `{corpus.corpus_version}`",
        f"- Corpus hash: `{corpus.artifact_hash}`",
        f"- Corpus items: {len(corpus.items)}",
        "- Corpus authorship: repository authored; no external dataset, no scraped "
        "content, no network retrieval, no personal information.",
        "",
        "## 2. Assignment identity",
        "",
        f"- Assignment: `{assignment.assignment_id}`",
        f"- Pseudonymous annotator: `{assignment.annotator_id}`",
        f"- Assignment method: `{assignment.assignment_method}` @ "
        f"`{assignment.assignment_method_version}`",
        f"- Assigned items: {len(assignment.item_ids)}",
        f"- Created: `{assignment.created_at}`",
        "",
        "## 3. Completion lifecycle",
        "",
        f"- Answered with a valence judgment: {counts.answered_with_valence}",
        f"- Explicitly abstained: {counts.abstained}",
        f"- Unanswered: {counts.unanswered}",
        f"- Superseded records preserved: {counts.superseded_records}",
        "",
        counts.notes,
        "",
        "## 4. Preserved responses",
        "",
        "Each response below is one annotator's independent judgment. No majority, "
        "average, median, consensus, adjudicated label, agreement statistic, or gold "
        "answer is computed anywhere in this report.",
        "",
    ]

    for response in receipt.responses:
        item = corpus.item(response.item_id)
        chain = session.responses_for(response.item_id)
        reason = response.abstention_reason
        certainty = response.self_reported_certainty
        lines.extend(
            [
                f"### {item.item_id}",
                "",
                "- Design categories: "
                + ", ".join(f"`{value}`" for value in item.categories),
                f"- Includes condition: {item.includes_condition}",
                "- The condition description states what the item includes. It is "
                "not an expected response.",
                "",
                "Exact text:",
                "",
                f"> {item.text}",
                "",
                f"- Valence judgment: `{response.valence_label.value}`",
                f"- Abstained: {'yes' if response.abstained else 'no'}",
                f"- Abstention reason: {_optional(reason.value if reason else None)}",
                f"- Context sufficiency: `{response.context_sufficiency.value}`",
                f"- Perceived ambiguity: `{response.perceived_ambiguity.value}`",
                "- Self-reported certainty: "
                f"{_optional(certainty.value if certainty else None)}"
                " (a statement about the annotator, never analyzer confidence)",
                f"- Rationale: {_optional(response.rationale)}",
            ]
        )
        if response.supporting_spans:
            lines.extend(
                f"- Supporting span `[{span.start}:{span.end}]`: "
                f"{item.text[span.start : span.end]!r}"
                for span in response.supporting_spans
            )
        else:
            lines.append("- Supporting spans: none provided")
        if len(chain) > 1:
            lines.extend(["", "Supersession ancestry (originals are preserved):", ""])
            lines.extend(
                f"  - `{record.response_id}` recorded `{record.valence_label.value}` at "
                f"`{record.recorded_at}`"
                + (
                    f", superseding `{record.supersedes_response_id}` because: "
                    f"{record.supersession_reason}"
                    if record.supersedes_response_id
                    else " (original)"
                )
                for record in chain
            )
        lines.append("")

    lines.extend(
        [
            "## 5. Immutable references",
            "",
            f"- `annotation-protocol` → `{receipt.protocol_ref.artifact_id}` "
            f"(`{receipt.protocol_ref.artifact_hash}`)",
            f"- `evaluation-corpus` → `{receipt.corpus_ref.artifact_id}` "
            f"(`{receipt.corpus_ref.artifact_hash}`)",
            f"- `annotator-assignment` → `{receipt.assignment_ref.artifact_id}` "
            f"(`{receipt.assignment_ref.artifact_hash}`)",
            f"- `assignment-completion` → `{receipt.completion_ref.artifact_id}` "
            f"(`{receipt.completion_ref.artifact_hash}`)",
            "",
        ]
    )
    lines.extend(
        f"- `annotation-response` → `{reference.artifact_id}` "
        f"(`{reference.artifact_hash}`)"
        for reference in receipt.response_refs
    )
    lines.extend(["", "## 6. Interpretation boundary and non-claims", ""])
    lines.extend(f"- {item}" for item in receipt.completion.non_claims)
    lines.extend(
        [
            "",
            "Aggregation, adjudication, and any empirical comparison require a "
            "separate, later, explicitly accepted protocol that does not exist yet.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _prompt_choice(
    prompt: Callable[[str], str],
    write: Callable[[str], None],
    label: str,
    options: Sequence[str],
) -> str:
    while True:
        write(f"\n{label}\n")
        for index, option in enumerate(options, start=1):
            write(f"  {index}. {option}\n")
        raw = prompt("Choose a number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        write("Please enter one of the listed numbers.\n")


def _collect_one(
    *,
    session: AnnotationSession,
    packet: AnnotationPacket,
    prompt: Callable[[str], str],
    write: Callable[[str], None],
) -> bool:
    write("\n" + "=" * 68 + "\n")
    write(f"Item {packet.position + 1} of {packet.total_items}\n")
    write("=" * 68 + "\n\n")
    write(f"{packet.text}\n\n")
    write(f"{packet.task_statement}\n")

    valence = _prompt_choice(
        prompt,
        write,
        "How favorable or unfavorable is the language in this passage?",
        [option.value for option in packet.valence_options],
    )
    label = ValenceLabel(valence)
    reason: AbstentionReason | None = None
    if label is ABSTENTION_LABEL:
        reason = AbstentionReason(
            _prompt_choice(
                prompt,
                write,
                "Why can you not determine this responsibly?",
                [item.value for item in AbstentionReason],
            )
        )
    sufficiency = ContextSufficiency(
        _prompt_choice(
            prompt,
            write,
            "Was the shown text enough context to answer responsibly?",
            [item.value for item in ContextSufficiency],
        )
    )
    ambiguity = PerceivedAmbiguity(
        _prompt_choice(
            prompt,
            write,
            "How open to more than one reading did this passage seem?",
            [item.value for item in PerceivedAmbiguity],
        )
    )
    rationale = prompt("\nOptional rationale (press Enter to skip): ").strip() or None

    write("\nAbout to record:\n")
    write(f"  valence            {label.value}\n")
    write(f"  abstention reason  {reason.value if reason else 'not applicable'}\n")
    write(f"  context            {sufficiency.value}\n")
    write(f"  ambiguity          {ambiguity.value}\n")
    write(f"  rationale          {rationale or 'not provided'}\n")
    confirmation = prompt("Record this response? It cannot be edited [y/N]: ").strip()
    if confirmation.lower() not in {"y", "yes"}:
        write("Not recorded. This item remains unanswered.\n")
        return False

    session.record(
        item_id=packet.item_id,
        valence_label=label,
        context_sufficiency=sufficiency,
        perceived_ambiguity=ambiguity,
        abstention_reason=reason,
        rationale=rationale,
    )
    write("Recorded.\n")
    return True


def run_collection_session(
    *,
    session: AnnotationSession,
    prompt: Callable[[str], str],
    write: Callable[[str], None],
    limit: int | None = None,
) -> CollectionCounts:
    """Collect responses one item at a time until the annotator stops."""

    write("\nHuman-reference annotation (research only)\n")
    write(
        "No analyzer, model, or expected answer is involved. Abstaining is a valid "
        "response.\n"
    )
    collected = 0
    while limit is None or collected < limit:
        packet = session.next_packet()
        if packet is None:
            write("\nEvery assigned item has a preserved response.\n")
            break
        if not _collect_one(
            session=session, packet=packet, prompt=prompt, write=write
        ):
            break
        collected += 1
    counts = session.counts()
    write(
        f"\nProgress: {counts.answered_with_valence} judged, {counts.abstained} "
        f"abstained, {counts.unanswered} remaining.\n"
    )
    write(f"{counts.notes}\n")
    return counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.human_reference_annotation",
        description=(
            "RESEARCH ONLY. Collect blinded, independent human-reference annotations "
            "for one declared dimension. No analyzer is run, named, or compared, and "
            "no aggregation, consensus, or agreement statistic is produced."
        ),
    )
    parser.add_argument("--annotator-id", required=True, help="Pseudonymous ID only.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(".ctrt") / "human-reference",
        help="Directory containing one append-only artifact store per annotator.",
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of items to collect in this sitting.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Render the collection report for a completed assignment and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the research-only collection workflow."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        session, store = open_assignment(
            workspace=arguments.workspace,
            annotator_id=arguments.annotator_id,
            corpus_path=arguments.corpus,
            protocol_path=arguments.protocol,
        )
        corpus = load_evaluation_corpus(_load_document(arguments.corpus, "corpus"))
        protocol = load_annotation_protocol(
            _load_document(arguments.protocol, "protocol")
        )
        protocol_ref, corpus_ref, assignment_ref = persist_collection_inputs(
            store,
            corpus=corpus,
            protocol=protocol,
            assignment=session.assignment,
        )
        if arguments.report is not None:
            completion, completion_ref = session.complete()
            receipt = verify_collection(
                store=store,
                session=session,
                corpus=corpus,
                protocol=protocol,
                completion=completion,
                completion_ref=completion_ref,
                protocol_ref=protocol_ref,
                corpus_ref=corpus_ref,
                assignment_ref=assignment_ref,
            )
            markdown = render_collection_report_markdown(
                receipt=receipt,
                corpus=corpus,
                protocol=protocol,
                session=session,
            )
            arguments.report.parent.mkdir(parents=True, exist_ok=True)
            arguments.report.write_text(markdown, encoding="utf-8")
            sys.stdout.write(f"Wrote collection report to {arguments.report}\n")
            return 0
        def _write(text: str) -> None:
            sys.stdout.write(text)

        run_collection_session(
            session=session,
            prompt=input,
            write=_write,
            limit=arguments.limit,
        )
    except (HumanReferenceError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"human-reference collection failed: {exc}\n")
        return 2
    sys.stderr.write(f"Artifact store: {store.root}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ASSIGNMENT_METHOD",
    "ASSIGNMENT_METHOD_VERSION",
    "COLLECTION_NON_CLAIMS",
    "COLLECTION_VERSION",
    "DEFAULT_CORPUS",
    "DEFAULT_PROTOCOL",
    "AnnotationPacket",
    "AnnotationResponse",
    "AnnotationSession",
    "AnnotatorAssignment",
    "AssignmentCompletion",
    "CollectionCounts",
    "VerifiedCollectionReceipt",
    "assignment_order",
    "main",
    "open_assignment",
    "persist_collection_inputs",
    "render_collection_report_markdown",
    "run_collection_session",
    "verify_collection",
]
