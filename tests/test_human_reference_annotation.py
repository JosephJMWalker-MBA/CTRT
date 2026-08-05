from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    FileSystemArtifactStore,
)
from ctrt.human_reference_annotation import (
    ASSIGNMENT_METHOD,
    COLLECTION_NON_CLAIMS,
    COLLECTION_VERSION,
    DEFAULT_CORPUS,
    DEFAULT_PROTOCOL,
    AnnotationSession,
    AnnotatorAssignment,
    assignment_order,
    main,
    open_assignment,
    persist_collection_inputs,
    render_collection_report_markdown,
    run_collection_session,
    verify_collection,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    FORBIDDEN_CANDIDATE_KEYS,
    ORDINAL_POSITIONS,
    AbstentionReason,
    ContextSufficiency,
    HumanReferenceError,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    SupportingSpan,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
    validate_annotator_id,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _corpus_document() -> Mapping[str, object]:
    return cast(dict[str, Any], json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8")))


def _protocol_document() -> Mapping[str, object]:
    return cast(dict[str, Any], json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8")))


def _answer_all(
    session: AnnotationSession,
    *,
    abstain_first: bool = True,
) -> None:
    """Record one response per assigned item, exercising both response kinds."""

    for index, item_id in enumerate(session.assignment.item_ids):
        if abstain_first and index == 0:
            session.record(
                item_id=item_id,
                valence_label=ABSTENTION_LABEL,
                context_sufficiency=ContextSufficiency.INSUFFICIENT,
                perceived_ambiguity=PerceivedAmbiguity.HIGH,
                abstention_reason=AbstentionReason.INSUFFICIENT_CONTEXT,
                recorded_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
            )
            continue
        session.record(
            item_id=item_id,
            valence_label=ValenceLabel.NEITHER,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.SOME,
            recorded_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
        )


@pytest.fixture
def session_and_store(tmp_path: Path) -> Iterator[tuple[AnnotationSession, Any]]:
    session, store = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-001",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    yield session, store


# --------------------------------------------------------------------------
# Frozen corpus
# --------------------------------------------------------------------------


def test_corpus_is_frozen_repository_authored_and_answer_free() -> None:
    document = _corpus_document()
    corpus = load_evaluation_corpus(document)

    assert document["status"] == "frozen"
    provenance = cast(dict[str, Any], document["provenance"])
    for flag in (
        "external_dataset",
        "scraped_content",
        "network_retrieval",
        "personal_information",
    ):
        assert provenance[flag] is False
    assert provenance["authorship"] == "repository_authored"
    assert cast(dict[str, Any], document["expected_responses"])[
        "expected_labels_present"
    ] is False
    assert cast(dict[str, Any], document["population_claim"])[
        "represents_population"
    ] is False

    assert corpus.dimension_id == "sentiment_valence"
    assert 40 <= len(corpus.items) <= 60
    assert len(corpus.items) == 48


def test_corpus_ordering_is_deterministic_and_hashes_match_text() -> None:
    first = load_evaluation_corpus(_corpus_document())
    second = load_evaluation_corpus(_corpus_document())

    assert first.artifact_hash == second.artifact_hash
    assert first.item_ids == second.item_ids
    assert first.item_ids == tuple(sorted(first.item_ids))
    assert tuple(item.position for item in first.items) == tuple(range(48))
    from ctrt.human_reference_protocol import content_hash

    for item in first.items:
        assert item.content_hash == content_hash(item.text)


def test_no_expected_sentiment_answer_is_encoded_anywhere_in_the_corpus() -> None:
    corpus = load_evaluation_corpus(_corpus_document())
    scale_values = {label.value for label in ValenceLabel}

    # No design category may name a response option.
    for category in corpus.categories:
        assert category not in scale_values

    # No item field may carry a response value, and each declares it is not one.
    for raw in cast(list[dict[str, Any]], _corpus_document()["items"]):
        assert raw["not_an_expected_response"] is True
        for value in raw.values():
            if isinstance(value, str):
                assert value not in scale_values
            elif isinstance(value, list):
                assert not set(value) & scale_values
        for banned in ("label", "gold", "ground_truth", "expected_label", "answer"):
            assert banned not in raw


def test_corpus_parser_rejects_answer_keys_and_unsafe_provenance() -> None:
    def _mutate(**changes: Any) -> dict[str, Any]:
        document = cast(dict[str, Any], _corpus_document())
        for path, value in changes.items():
            parts = path.split(".")
            target = document
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        return document

    with pytest.raises(HumanReferenceError, match="frozen"):
        load_evaluation_corpus(_mutate(status="draft"))
    with pytest.raises(HumanReferenceError, match="expected responses"):
        load_evaluation_corpus(
            _mutate(**{"expected_responses.expected_labels_present": True})
        )
    with pytest.raises(HumanReferenceError, match="represent a population"):
        load_evaluation_corpus(
            _mutate(**{"population_claim.represents_population": True})
        )
    with pytest.raises(HumanReferenceError, match="scraped_content"):
        load_evaluation_corpus(_mutate(**{"provenance.scraped_content": True}))
    with pytest.raises(HumanReferenceError, match="personal_information"):
        load_evaluation_corpus(_mutate(**{"provenance.personal_information": True}))

    document = cast(dict[str, Any], _corpus_document())
    document["items"][0]["gold_label"] = "somewhat_favorable"
    with pytest.raises(HumanReferenceError, match="answer-shaped fields"):
        load_evaluation_corpus(document)


def test_corpus_covers_the_required_short_form_phenomena() -> None:
    corpus = load_evaluation_corpus(_corpus_document())
    exercised = {value for item in corpus.items for value in item.categories}

    for required in (
        "conventionally_favorable_vocabulary",
        "conventionally_unfavorable_vocabulary",
        "primarily_factual_wording",
        "mixed_valence_vocabulary",
        "contrastive_construction",
        "negation_construction",
        "intensifier_present",
        "diminisher_present",
        "capitalization_emphasis",
        "punctuation_emphasis",
        "slang_or_informal",
        "emoticon_or_emoji",
        "context_dependent_reference",
        "irony_or_sarcasm_risk",
        "underspecified_reference",
        "plausible_abstention",
    ):
        assert required in exercised, required


# --------------------------------------------------------------------------
# Protocol
# --------------------------------------------------------------------------


def test_protocol_declares_the_exact_versioned_scale() -> None:
    protocol = load_annotation_protocol(_protocol_document())

    assert protocol.protocol_id == "protocol.human-reference-sentiment-valence"
    assert protocol.protocol_version == "0.1.0"
    assert protocol.dimension_id == "sentiment_valence"
    assert protocol.valence_options == (
        ValenceLabel.STRONGLY_UNFAVORABLE,
        ValenceLabel.SOMEWHAT_UNFAVORABLE,
        ValenceLabel.NEITHER,
        ValenceLabel.SOMEWHAT_FAVORABLE,
        ValenceLabel.STRONGLY_FAVORABLE,
        ValenceLabel.CANNOT_DETERMINE,
    )
    assert ABSTENTION_LABEL in protocol.valence_options
    assert ORDINAL_POSITIONS[ABSTENTION_LABEL] is None


def test_numeric_encoding_is_declared_as_a_serialization_convenience_only() -> None:
    scale = cast(dict[str, Any], _protocol_document()["valence_scale"])
    note = cast(str, scale["numeric_encoding_note"]).lower()

    assert "not an interval" in note
    assert "never be averaged" in note
    assert scale["scale_type"] == "ordered_categorical_with_abstention"


def test_protocol_forbids_aggregation_in_this_version() -> None:
    document = cast(dict[str, Any], _protocol_document())
    assert document["aggregation_policy"]["aggregation_permitted"] is False

    document["aggregation_policy"]["aggregation_permitted"] = True
    with pytest.raises(HumanReferenceError, match="forbid aggregation"):
        load_annotation_protocol(document)


# --------------------------------------------------------------------------
# Annotator identity and privacy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["rater-001", "abc", "annotator-7", "r2d2"])
def test_safe_pseudonymous_annotator_ids_are_accepted(value: str) -> None:
    assert validate_annotator_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "person@example.com",
        "Jane Doe",
        "+15555550123",
        "../escape",
        "rater_001",
        "ab",
        "R1",
        "",
        "a" * 33,
        "user.name",
        "1rater",
    ],
)
def test_unsafe_or_identifying_annotator_ids_are_rejected(value: str) -> None:
    with pytest.raises(HumanReferenceError, match="annotator_id"):
        validate_annotator_id(value)


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------


def test_assignment_order_is_deterministic_and_a_true_permutation() -> None:
    corpus = load_evaluation_corpus(_corpus_document())
    first = assignment_order(
        item_ids=corpus.item_ids,
        corpus_hash=corpus.artifact_hash,
        annotator_id="rater-001",
    )
    again = assignment_order(
        item_ids=corpus.item_ids,
        corpus_hash=corpus.artifact_hash,
        annotator_id="rater-001",
    )

    assert first == again
    assert sorted(first) == sorted(corpus.item_ids)
    assert len(set(first)) == len(corpus.item_ids)


def test_different_annotators_receive_different_deterministic_orders() -> None:
    corpus = load_evaluation_corpus(_corpus_document())
    orders = {
        annotator: assignment_order(
            item_ids=corpus.item_ids,
            corpus_hash=corpus.artifact_hash,
            annotator_id=annotator,
        )
        for annotator in ("rater-001", "rater-002", "rater-003", "rater-004")
    }

    assert len({tuple(value) for value in orders.values()}) == len(orders)
    for order in orders.values():
        assert sorted(order) == sorted(corpus.item_ids)
    # Corpus identity is unchanged by reordering.
    assert load_evaluation_corpus(_corpus_document()).artifact_hash == (
        corpus.artifact_hash
    )


def test_assignment_binds_corpus_protocol_and_method_identity(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    assignment = session.assignment
    corpus = load_evaluation_corpus(_corpus_document())
    protocol = load_annotation_protocol(_protocol_document())

    assert assignment.collection_version == COLLECTION_VERSION
    assert assignment.corpus_hash == corpus.artifact_hash
    assert assignment.protocol_hash == protocol.artifact_hash
    assert assignment.assignment_method == ASSIGNMENT_METHOD
    assert set(assignment.item_ids) == set(corpus.item_ids)
    assignment.verify_against(corpus=corpus, protocol=protocol)


def test_assignment_rejects_reordering_and_hash_drift(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    from dataclasses import replace

    session, _ = session_and_store
    corpus = load_evaluation_corpus(_corpus_document())
    protocol = load_annotation_protocol(_protocol_document())
    assignment = session.assignment

    reordered = replace(
        assignment, item_ids=tuple(reversed(assignment.item_ids))
    )
    with pytest.raises(HumanReferenceError, match="order differs"):
        reordered.verify_against(corpus=corpus, protocol=protocol)

    wrong_corpus = replace(assignment, corpus_hash="sha256:" + ("0" * 64))
    with pytest.raises(HumanReferenceError, match="corpus hash"):
        wrong_corpus.verify_against(corpus=corpus, protocol=protocol)

    wrong_protocol = replace(assignment, protocol_hash="sha256:" + ("0" * 64))
    with pytest.raises(HumanReferenceError, match="protocol hash"):
        wrong_protocol.verify_against(corpus=corpus, protocol=protocol)


def test_assignment_rejects_an_unsafe_annotator_id() -> None:
    with pytest.raises(HumanReferenceError, match="annotator_id"):
        AnnotatorAssignment(
            assignment_id="assignment.x",
            collection_version=COLLECTION_VERSION,
            annotator_id="person@example.com",
            corpus_id="c",
            corpus_version="0.1.0",
            corpus_hash="sha256:" + ("0" * 64),
            protocol_id="p",
            protocol_version="0.1.0",
            protocol_hash="sha256:" + ("0" * 64),
            item_ids=("hr-001",),
            assignment_method=ASSIGNMENT_METHOD,
            assignment_method_version="0.1.0",
            created_at="2026-08-05T22:00:00Z",
        )


# --------------------------------------------------------------------------
# Blinding
# --------------------------------------------------------------------------


def test_annotation_packets_are_behaviorally_blinded(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    from dataclasses import fields

    packet = session.next_packet()
    assert packet is not None

    # The packet structure has no field capable of carrying candidate identity.
    field_names = {item.name for item in fields(packet)}
    assert not field_names & FORBIDDEN_CANDIDATE_KEYS

    from ctrt.serialization import canonical_json_text

    rendered = canonical_json_text(packet).lower()
    for banned in (
        "vader",
        "analyzer",
        "candidate",
        "compound",
        "characterization",
        "eligible_for_evaluation",
        "expectation",
        "registry",
        "model",
    ):
        assert banned not in rendered, banned


def test_every_packet_in_the_assignment_is_blinded(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    from ctrt.serialization import canonical_json_text

    for item_id in session.assignment.item_ids:
        rendered = canonical_json_text(session.packet_for(item_id)).lower()
        assert "vader" not in rendered
        assert "analyzer" not in rendered


def test_stored_annotation_artifacts_carry_no_candidate_fields(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, store = session_and_store
    _answer_all(session)

    stored = b"\n".join(
        path.read_bytes() for path in store.root.rglob("*") if path.is_file()
    )
    lowered = stored.lower()
    for banned in (b"vader", b"analyzer", b"candidate", b'"compound"'):
        assert banned not in lowered, banned
    keys = set(re.findall(rb'"([a-z_]+)":', stored))
    assert not {key.decode() for key in keys} & FORBIDDEN_CANDIDATE_KEYS


def test_no_vader_or_characterization_import_exists_in_the_collection_path() -> None:
    for name in ("human_reference_annotation.py", "human_reference_protocol.py"):
        source = (REPO_ROOT / "src" / "ctrt" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            cast(str, node.module)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        for banned in ("vader", "characterization", "creator_preflight", "synthetic"):
            assert not any(banned in item.lower() for item in imported), (name, banned)
        assert "vaderSentiment" not in source


# --------------------------------------------------------------------------
# Append-only collection
# --------------------------------------------------------------------------


def test_responses_persist_append_only_and_resume_exactly(tmp_path: Path) -> None:
    session, _ = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-001",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    first_three = session.assignment.item_ids[:3]
    for item_id in first_three:
        session.record(
            item_id=item_id,
            valence_label=ValenceLabel.SOMEWHAT_FAVORABLE,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
        )

    # A fresh session over the same workspace resumes from stored artifacts.
    resumed, _ = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-001",
        created_at=datetime(2026, 8, 5, 23, 0, tzinfo=UTC),
    )
    assert resumed.answered_item_ids() == first_three
    assert resumed.unanswered_item_ids() == session.assignment.item_ids[3:]
    next_packet = resumed.next_packet()
    assert next_packet is not None
    assert next_packet.item_id == session.assignment.item_ids[3]


def test_recording_twice_is_refused_rather_than_overwriting(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    item_id = session.assignment.item_ids[0]
    session.record(
        item_id=item_id,
        valence_label=ValenceLabel.SOMEWHAT_FAVORABLE,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.NONE,
    )

    with pytest.raises(HumanReferenceError, match="already has a preserved response"):
        session.record(
            item_id=item_id,
            valence_label=ValenceLabel.STRONGLY_UNFAVORABLE,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
        )
    current = session.current_response(item_id)
    assert current is not None
    assert current.valence_label is ValenceLabel.SOMEWHAT_FAVORABLE


def test_unanswered_is_distinct_from_abstention(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    abstained_item = session.assignment.item_ids[0]
    untouched_item = session.assignment.item_ids[1]

    session.record(
        item_id=abstained_item,
        valence_label=ABSTENTION_LABEL,
        context_sufficiency=ContextSufficiency.INSUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.HIGH,
        abstention_reason=AbstentionReason.INSUFFICIENT_CONTEXT,
    )

    assert abstained_item in session.answered_item_ids()
    assert abstained_item not in session.unanswered_item_ids()
    assert untouched_item in session.unanswered_item_ids()
    assert session.current_response(untouched_item) is None
    counts = session.counts()
    assert counts.abstained == 1
    assert counts.answered_with_valence == 0
    assert counts.unanswered == len(session.assignment.item_ids) - 1


def test_abstention_requires_a_reason_and_a_judgment_forbids_one(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    items = session.assignment.item_ids

    with pytest.raises(HumanReferenceError, match="abstention requires a recorded"):
        session.record(
            item_id=items[0],
            valence_label=ABSTENTION_LABEL,
            context_sufficiency=ContextSufficiency.INSUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.HIGH,
        )

    with pytest.raises(HumanReferenceError, match="may not carry an abstention reason"):
        session.record(
            item_id=items[1],
            valence_label=ValenceLabel.SOMEWHAT_FAVORABLE,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
            abstention_reason=AbstentionReason.INSUFFICIENT_CONTEXT,
        )


def test_context_ambiguity_and_certainty_stay_separate_fields(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    item_id = session.assignment.item_ids[0]
    response, _ = session.record(
        item_id=item_id,
        valence_label=ValenceLabel.STRONGLY_FAVORABLE,
        context_sufficiency=ContextSufficiency.INSUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.HIGH,
        self_reported_certainty=SelfReportedCertainty.LOW,
    )

    # A confident-looking valence can coexist with low context and high ambiguity;
    # none of these fields is derived from another.
    assert response.valence_label is ValenceLabel.STRONGLY_FAVORABLE
    assert response.context_sufficiency is ContextSufficiency.INSUFFICIENT
    assert response.perceived_ambiguity is PerceivedAmbiguity.HIGH
    assert response.self_reported_certainty is SelfReportedCertainty.LOW
    assert response.abstained is False


def test_self_reported_certainty_never_reaches_instrument_confidence(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    from dataclasses import fields

    session, store = session_and_store
    item_id = session.assignment.item_ids[0]
    session.record(
        item_id=item_id,
        valence_label=ValenceLabel.NEITHER,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.NONE,
        self_reported_certainty=SelfReportedCertainty.HIGH,
    )
    response = session.current_response(item_id)
    assert response is not None

    names = {item.name for item in fields(response)}
    for banned in (
        "instrument_probability",
        "confidence",
        "confidence_vector",
        "calibration",
        "applicability",
    ):
        assert banned not in names

    stored = b"\n".join(
        path.read_bytes() for path in store.root.rglob("*") if path.is_file()
    )
    assert b"instrument_probability" not in stored
    assert b"confidence" not in stored.replace(b"self_reported_certainty", b"")


def test_optional_rationale_and_valid_spans_are_preserved(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    item_id = session.assignment.item_ids[0]
    packet = session.packet_for(item_id)
    span = SupportingSpan(start=0, end=min(4, len(packet.text)))

    response, _ = session.record(
        item_id=item_id,
        valence_label=ValenceLabel.SOMEWHAT_UNFAVORABLE,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.SOME,
        rationale="The hedging qualifier carried most of the weight.",
        supporting_spans=(span,),
    )
    assert response.rationale is not None
    assert response.supporting_spans == (span,)


def test_spans_outside_the_exact_text_are_rejected(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    item_id = session.assignment.item_ids[0]
    text_length = len(session.packet_for(item_id).text)

    with pytest.raises(HumanReferenceError, match="falls outside the exact"):
        session.record(
            item_id=item_id,
            valence_label=ValenceLabel.NEITHER,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
            supporting_spans=(SupportingSpan(start=0, end=text_length + 5),),
        )
    with pytest.raises(HumanReferenceError, match="greater than start"):
        SupportingSpan(start=5, end=5)
    assert session.current_response(item_id) is None


def test_an_item_outside_the_assignment_is_rejected(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    with pytest.raises(HumanReferenceError, match="not in this assignment"):
        session.record(
            item_id="hr-999",
            valence_label=ValenceLabel.NEITHER,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
        )


# --------------------------------------------------------------------------
# Supersession
# --------------------------------------------------------------------------


def test_supersession_preserves_the_original_and_records_ancestry(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, store = session_and_store
    item_id = session.assignment.item_ids[0]
    original, original_ref = session.record(
        item_id=item_id,
        valence_label=ValenceLabel.STRONGLY_FAVORABLE,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.NONE,
    )
    corrected, _ = session.supersede(
        item_id=item_id,
        reason="Misread the negation on a second pass.",
        valence_label=ValenceLabel.SOMEWHAT_UNFAVORABLE,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.SOME,
    )

    chain = session.responses_for(item_id)
    assert len(chain) == 2
    assert chain[0].response_id == original.response_id
    assert chain[0].valence_label is ValenceLabel.STRONGLY_FAVORABLE
    assert chain[1].supersedes_response_id == original.response_id
    assert chain[1].supersession_reason is not None
    assert session.current_response(item_id) == corrected

    # The original artifact is still stored, unchanged.
    stored = store.get(original.response_id, expected_hash=original_ref.artifact_hash)
    assert b"strongly_favorable" in stored.payload
    assert session.counts().superseded_records == 1


def test_supersession_without_a_predecessor_is_rejected(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    with pytest.raises(HumanReferenceError, match="no predecessor response"):
        session.supersede(
            item_id=session.assignment.item_ids[0],
            reason="No prior record exists.",
            valence_label=ValenceLabel.NEITHER,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
        )


def test_supersession_requires_a_reason(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    item_id = session.assignment.item_ids[0]
    session.record(
        item_id=item_id,
        valence_label=ValenceLabel.NEITHER,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.NONE,
    )
    with pytest.raises(HumanReferenceError, match="requires a recorded reason"):
        session.supersede(
            item_id=item_id,
            reason="   ",
            valence_label=ValenceLabel.SOMEWHAT_FAVORABLE,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
        )


# --------------------------------------------------------------------------
# Completion, verification, and report
# --------------------------------------------------------------------------


def test_completion_requires_every_item_to_be_answered_or_abstained(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, _ = session_and_store
    session.record(
        item_id=session.assignment.item_ids[0],
        valence_label=ValenceLabel.NEITHER,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.NONE,
    )
    with pytest.raises(HumanReferenceError, match="still unanswered"):
        session.complete()

    _answer_all_remaining(session)
    completion, _ = session.complete(completed_at=datetime(2026, 8, 5, 23, tzinfo=UTC))
    assert completion.counts.unanswered == 0
    assert len(completion.response_refs) == len(session.assignment.item_ids)


def _answer_all_remaining(session: AnnotationSession) -> None:
    for item_id in session.unanswered_item_ids():
        session.record(
            item_id=item_id,
            valence_label=ValenceLabel.NEITHER,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.SOME,
            recorded_at=datetime(2026, 8, 5, 22, 30, tzinfo=UTC),
        )


def _complete_receipt(tmp_path: Path, annotator: str = "rater-001") -> Any:
    session, store = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id=annotator,
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    corpus = load_evaluation_corpus(_corpus_document())
    protocol = load_annotation_protocol(_protocol_document())
    protocol_ref, corpus_ref, assignment_ref = persist_collection_inputs(
        store, corpus=corpus, protocol=protocol, assignment=session.assignment
    )
    _answer_all(session)
    completion, completion_ref = session.complete(
        completed_at=datetime(2026, 8, 5, 23, 0, tzinfo=UTC)
    )
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
    return receipt, corpus, protocol, session, store


def test_verified_receipt_binds_every_artifact(tmp_path: Path) -> None:
    receipt, corpus, protocol, _, _ = _complete_receipt(tmp_path)

    assert receipt.collection_version == COLLECTION_VERSION
    assert len(receipt.responses) == len(corpus.items)
    assert len(receipt.response_refs) == len(corpus.items)
    assert receipt.completion.corpus_hash == corpus.artifact_hash
    assert receipt.completion.protocol_hash == protocol.artifact_hash
    for response in receipt.responses:
        assert response.protocol_hash == protocol.artifact_hash
        assert response.item_content_hash == corpus.item(response.item_id).content_hash


def test_read_time_tampering_fails_before_report_rendering(tmp_path: Path) -> None:
    receipt, corpus, protocol, session, store = _complete_receipt(tmp_path)
    reference = receipt.response_refs[0]
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = store.root / "blobs" / "sha256" / digest
    assert blob.is_file()
    blob.write_bytes(b"{}")

    with pytest.raises(ArtifactIntegrityError, match="failed SHA-256"):
        verify_collection(
            store=FileSystemArtifactStore(store.root),
            session=session,
            corpus=corpus,
            protocol=protocol,
            completion=receipt.completion,
            completion_ref=receipt.completion_ref,
            protocol_ref=receipt.protocol_ref,
            corpus_ref=receipt.corpus_ref,
            assignment_ref=receipt.assignment_ref,
        )


def test_report_shows_preserved_responses_without_any_aggregation(
    tmp_path: Path,
) -> None:
    receipt, corpus, protocol, session, _ = _complete_receipt(tmp_path)
    report = render_collection_report_markdown(
        receipt=receipt, corpus=corpus, protocol=protocol, session=session
    )

    for section in (
        "## 1. Protocol and corpus identity",
        "## 2. Assignment identity",
        "## 3. Completion lifecycle",
        "## 4. Preserved responses",
        "## 5. Immutable references",
        "## 6. Interpretation boundary and non-claims",
    ):
        assert section in report

    for item in corpus.items:
        assert item.text in report
    for notice in COLLECTION_NON_CLAIMS:
        assert notice in report
    assert "do not become ground truth" in report
    assert "evidence to preserve, not errors to erase" in report

    # The report legitimately *denies* several of these terms, so each pattern
    # below matches only an affirmative form that would report a computed value.
    lowered = report.lower()
    for banned in (
        r"majority\s*[:=]",
        r"consensus\s*(label|answer|value)?\s*[:=]",
        r"gold\s*(label|answer)\s*[:=]",
        r"adjudicated\s*label\s*[:=]",
        r"agreement\s*[:=]",
        r"\baverage\s*[:=]",
        r"\bmedian\s*[:=]",
        r"accuracy\s*[:=]",
        r"\bkappa\b",
        r"\balpha\s*[:=]",
    ):
        assert re.search(banned, lowered) is None, banned

    # Candidate identity and analyzer output may never appear in any form.
    for banned in ("vader", "compound", "sentimentintensityanalyzer", "polarity_scores"):
        assert banned not in lowered, banned

    # And the denials themselves are present.
    assert "no majority, average, median, consensus" in lowered
    assert "never analyzer confidence" in lowered


def test_report_shows_supersession_ancestry(tmp_path: Path) -> None:
    session, store = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-002",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    corpus = load_evaluation_corpus(_corpus_document())
    protocol = load_annotation_protocol(_protocol_document())
    refs = persist_collection_inputs(
        store, corpus=corpus, protocol=protocol, assignment=session.assignment
    )
    _answer_all(session)
    item_id = session.assignment.item_ids[5]
    session.supersede(
        item_id=item_id,
        reason="Reread the contrastive clause.",
        valence_label=ValenceLabel.SOMEWHAT_UNFAVORABLE,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.SOME,
        recorded_at=datetime(2026, 8, 5, 22, 45, tzinfo=UTC),
    )
    completion, completion_ref = session.complete(
        completed_at=datetime(2026, 8, 5, 23, 0, tzinfo=UTC)
    )
    receipt = verify_collection(
        store=store,
        session=session,
        corpus=corpus,
        protocol=protocol,
        completion=completion,
        completion_ref=completion_ref,
        protocol_ref=refs[0],
        corpus_ref=refs[1],
        assignment_ref=refs[2],
    )
    report = render_collection_report_markdown(
        receipt=receipt, corpus=corpus, protocol=protocol, session=session
    )

    assert "Supersession ancestry" in report
    assert "Reread the contrastive clause." in report
    assert "(original)" in report
    assert receipt.completion.counts.superseded_records == 1


def test_no_aggregate_or_consensus_api_exists() -> None:
    import ctrt.human_reference_annotation as module
    import ctrt.human_reference_protocol as protocol_module

    for name in dir(module) + dir(protocol_module):
        lowered = name.lower()
        for banned in (
            "majority",
            "consensus",
            "average",
            "median",
            "adjudicat",
            "agreement",
            "gold",
            "merge",
        ):
            assert banned not in lowered, name


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_terminal_session_collects_and_confirms(tmp_path: Path) -> None:
    session, _ = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-001",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    scripted = iter(
        [
            "4",  # somewhat_favorable
            "1",  # context sufficient
            "1",  # ambiguity none
            "",  # no rationale
            "y",  # confirm
        ]
    )
    written: list[str] = []

    def _prompt(text: str) -> str:
        written.append(text)
        return next(scripted)

    counts = run_collection_session(
        session=session,
        prompt=_prompt,
        write=written.append,
        limit=1,
    )

    assert counts.answered_with_valence == 1
    output = "".join(written).lower()
    # No candidate identity, package name, or analyzer output may be shown. The
    # word "analyzer" appears only in the interface's own denial that one exists.
    for banned in ("vader", "compound", "sentimentintensityanalyzer", "candidate"):
        assert banned not in output, banned
    assert "no analyzer, model, or expected answer is involved" in output
    assert "cannot be edited" in output
    assert "abstaining is a valid response" in output
    # Every scale option is offered, including abstention.
    for option in ValenceLabel:
        assert option.value in output


def test_declining_confirmation_leaves_the_item_unanswered(tmp_path: Path) -> None:
    session, _ = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-001",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    scripted = iter(["4", "1", "1", "", "n"])
    written: list[str] = []
    counts = run_collection_session(
        session=session,
        prompt=lambda _: next(scripted),
        write=written.append,
        limit=1,
    )

    assert counts.answered_with_valence == 0
    assert counts.unanswered == len(session.assignment.item_ids)
    assert "remains unanswered" in "".join(written)


def test_cli_rejects_an_unsafe_annotator_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--annotator-id",
                "person@example.com",
                "--workspace",
                str(tmp_path / "hr"),
            ]
        )
    assert excinfo.value.code == 2
    assert "annotator_id" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_candidate_lifecycle_and_characterization_are_untouched() -> None:
    from ctrt.candidate_eligibility import (
        CandidateDisposition,
        CandidateRegistrySnapshot,
    )

    registry = REPO_ROOT / "docs" / "candidates" / "real-registry.v0.1.0.json"
    snapshot = CandidateRegistrySnapshot.from_document(
        cast(dict[str, Any], json.loads(registry.read_text(encoding="utf-8")))
    )
    record = snapshot.candidate("vader.sentiment")
    assert record is not None
    assert record.status is CandidateDisposition.ELIGIBLE_FOR_EVALUATION

    # The registry must record nothing about this collection. It legitimately
    # mentions human annotation as *required later work*, so this checks for
    # identifiers this PR introduces rather than for the bare word.
    text = registry.read_text(encoding="utf-8")
    for banned in (
        COLLECTION_VERSION,
        "protocol.human-reference-sentiment-valence",
        "corpus.human-reference-sentiment",
        "assignment.",
        "rater-",
    ):
        assert banned not in text, banned


def test_creator_facing_and_characterization_modules_do_not_import_collection() -> None:
    for name in (
        "creator_preflight.py",
        "creator_preflight_local.py",
        "creator_preflight_web.py",
        "vader_characterization.py",
        "vader_adapter.py",
        "synthetic.py",
        "workbench.py",
        "__init__.py",
        "_public_api_base.py",
    ):
        source = (REPO_ROOT / "src" / "ctrt" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            cast(str, node.module)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any("human_reference" in item for item in imported), name


def test_collection_works_without_the_optional_vader_dependency(
    tmp_path: Path,
) -> None:
    """Behaviour must be identical in both dependency states."""

    import sys

    session, _ = open_assignment(
        workspace=tmp_path / "hr",
        annotator_id="rater-009",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    packet = session.next_packet()
    assert packet is not None
    session.record(
        item_id=packet.item_id,
        valence_label=ValenceLabel.NEITHER,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        perceived_ambiguity=PerceivedAmbiguity.NONE,
    )
    assert session.counts().answered_with_valence == 1
    # Importing and running the collection path must not pull in the optional
    # candidate dependency, whether or not it happens to be installed.
    assert "vaderSentiment" not in sys.modules


def test_missing_response_artifact_reads_as_unanswered(
    session_and_store: tuple[AnnotationSession, Any],
) -> None:
    session, store = session_and_store
    item_id = session.assignment.item_ids[0]
    with pytest.raises(ArtifactNotFoundError):
        store.get(f"{session.assignment.assignment_id}:{item_id}:response:0")
    assert session.current_response(item_id) is None


def test_public_exports_remain_bounded() -> None:
    import ctrt
    import ctrt.human_reference_annotation as collection
    import ctrt.human_reference_protocol as contracts

    assert collection.__all__ == [
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
    assert contracts.__all__ == [
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
    assert not [
        name
        for name in ctrt.__all__
        if "annotation" in name.lower() or "human_reference" in name.lower()
    ]
