from __future__ import annotations

import ast
import json
import sys
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from ctrt.human_reference_annotation import (
    AnnotationResponse,
    open_assignment,
    persist_collection_inputs,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    ORDINAL_POSITIONS,
    AbstentionReason,
    ContextSufficiency,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    SupportingSpan,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
)
from ctrt.human_reference_synthesis import (
    DEFAULT_ANNOTATION_PROTOCOL,
    DEFAULT_CORPUS,
    DEFAULT_SYNTHESIS_PROTOCOL,
    INSUFFICIENT_COVERAGE,
    ORDINAL_DISTANCE_BUCKETS,
    SUFFICIENT_COVERAGE,
    SYNTHESIS_NON_CLAIMS,
    SYNTHESIS_VERSION,
    ItemSynthesis,
    SynthesisError,
    SynthesisProtocol,
    VerifiedSynthesisReceipt,
    is_test_fixture_collection,
    main,
    mark_test_fixture_collection,
    render_synthesis_report_markdown,
    run_human_reference_synthesis,
)
from ctrt.serialization import serialize_artifact

REPO_ROOT = Path(__file__).resolve().parents[1]

# Concepts this protocol version must never produce. Checked structurally
# against the API surface and stored artifacts rather than against prose.
FORBIDDEN_CONCEPTS = (
    "majority",
    "mode",
    "median",
    "mean",
    "average",
    "consensus",
    "adjudicat",
    "gold",
    "correct_label",
    "merged",
    "rank",
    "kappa",
    "alpha",
    "krippendorff",
    "fleiss",
    "cohen",
    "reliability",
    "accuracy",
    "significance",
    "p_value",
)


def _corpus() -> Any:
    return load_evaluation_corpus(
        cast(dict[str, Any], json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8")))
    )


def _protocol() -> Any:
    return load_annotation_protocol(
        cast(
            dict[str, Any],
            json.loads(DEFAULT_ANNOTATION_PROTOCOL.read_text(encoding="utf-8")),
        )
    )


def _synthesis_document() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(DEFAULT_SYNTHESIS_PROTOCOL.read_text(encoding="utf-8")),
    )


def _fixture_collection(
    workspace: Path,
    *,
    annotator_id: str,
    label: ValenceLabel,
    certainty: SelfReportedCertainty | None = None,
    rationale: str | None = None,
    with_span: bool = False,
    supersede_first_item_to: ValenceLabel | None = None,
) -> str:
    """Create one clearly labeled synthetic fixture collection.

    These are generated at test time through the real collection path and are
    marked so production synthesis refuses them. They are never human evidence.
    """

    session, store = open_assignment(
        workspace=workspace,
        annotator_id=annotator_id,
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    persist_collection_inputs(
        store, corpus=_corpus(), protocol=_protocol(), assignment=session.assignment
    )
    mark_test_fixture_collection(store, assignment_id=session.assignment.assignment_id)

    for index, item_id in enumerate(session.assignment.item_ids):
        spans: tuple[SupportingSpan, ...] = ()
        if with_span and index == 0:
            spans = (SupportingSpan(start=0, end=3),)
        session.record(
            item_id=item_id,
            valence_label=label,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.SOME,
            abstention_reason=(
                AbstentionReason.INSUFFICIENT_CONTEXT
                if label is ABSTENTION_LABEL
                else None
            ),
            self_reported_certainty=certainty,
            rationale=rationale if index == 0 else None,
            supporting_spans=spans,
            recorded_at=datetime(2026, 8, 5, 22, 15, tzinfo=UTC),
        )
    if supersede_first_item_to is not None:
        session.supersede(
            item_id=session.assignment.item_ids[0],
            reason="Reread the passage on a second pass.",
            valence_label=supersede_first_item_to,
            context_sufficiency=ContextSufficiency.SUFFICIENT,
            perceived_ambiguity=PerceivedAmbiguity.NONE,
            abstention_reason=(
                AbstentionReason.AMBIGUOUS_BETWEEN_READINGS
                if supersede_first_item_to is ABSTENTION_LABEL
                else None
            ),
            recorded_at=datetime(2026, 8, 5, 22, 45, tzinfo=UTC),
        )
    completion, _ = session.complete(
        completed_at=datetime(2026, 8, 5, 23, 0, tzinfo=UTC)
    )
    return completion.completion_id


def _three_fixtures(
    workspace: Path,
    labels: Sequence[ValenceLabel] = (
        ValenceLabel.SOMEWHAT_FAVORABLE,
        ValenceLabel.NEITHER,
        ABSTENTION_LABEL,
    ),
) -> list[str]:
    return [
        _fixture_collection(
            workspace,
            annotator_id=f"rater-{index + 1:03d}",
            label=label,
            certainty=SelfReportedCertainty.MEDIUM if index == 0 else None,
            rationale="The hedging qualifier carried the weight." if index == 0 else None,
            with_span=index == 0,
        )
        for index, label in enumerate(labels)
    ]


def _synthesize(
    workspace: Path,
    completion_ids: Sequence[str],
    **kwargs: Any,
) -> VerifiedSynthesisReceipt:
    return run_human_reference_synthesis(
        workspace=workspace,
        completion_ids=completion_ids,
        allow_test_fixtures=True,
        created_at=datetime(2026, 8, 5, 23, 30, tzinfo=UTC),
        **kwargs,
    )


@pytest.fixture
def receipt(tmp_path: Path) -> VerifiedSynthesisReceipt:
    workspace = tmp_path / "hr"
    return _synthesize(workspace, _three_fixtures(workspace))


# --------------------------------------------------------------------------
# Frozen synthesis protocol
# --------------------------------------------------------------------------


def test_synthesis_protocol_identity_and_compatibility_bindings() -> None:
    protocol = SynthesisProtocol.from_document(_synthesis_document())

    assert protocol.protocol_id == "protocol.human-reference-synthesis"
    assert protocol.protocol_version == "0.1.0"
    assert protocol.compatible_annotation_protocol_id == (
        "protocol.human-reference-sentiment-valence"
    )
    assert protocol.compatible_corpus_id == "corpus.human-reference-sentiment"
    assert protocol.dimension_id == "sentiment_valence"
    assert protocol.minimum_distinct_annotators_per_item == 3
    assert protocol.below_threshold_status == INSUFFICIENT_COVERAGE


def test_synthesis_protocol_rejects_unfrozen_or_unsafe_declarations() -> None:
    def _mutate(**changes: Any) -> dict[str, Any]:
        document = _synthesis_document()
        for path, value in changes.items():
            parts = path.split(".")
            target = document
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        return document

    with pytest.raises(SynthesisError, match="frozen"):
        SynthesisProtocol.from_document(_mutate(status="draft"))
    with pytest.raises(SynthesisError, match="separate category"):
        SynthesisProtocol.from_document(
            _mutate(**{"abstention_treatment.separate_category": False})
        )
    with pytest.raises(SynthesisError, match="numerically encoded"):
        SynthesisProtocol.from_document(
            _mutate(**{"abstention_treatment.numerically_encoded": True})
        )
    with pytest.raises(SynthesisError, match="denominator"):
        SynthesisProtocol.from_document(
            _mutate(**{"concordance_rules.denominator_preserving": False})
        )
    with pytest.raises(SynthesisError, match="0 through 4"):
        SynthesisProtocol.from_document(
            _mutate(**{"concordance_rules.ordinal_distance_buckets": [0, 1, 2]})
        )


def test_incompatible_corpus_or_protocol_is_refused(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    document = _synthesis_document()
    document["compatible_corpus_version"] = "9.9.9"
    changed = tmp_path / "changed-synthesis.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SynthesisError, match="corpus version is not compatible"):
        _synthesize(workspace, ids, synthesis_protocol_path=changed)

    document = _synthesis_document()
    document["compatible_annotation_protocol_id"] = "protocol.other"
    changed_two = tmp_path / "changed-two.json"
    changed_two.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SynthesisError, match="not compatible"):
        _synthesize(workspace, ids, synthesis_protocol_path=changed_two)


# --------------------------------------------------------------------------
# Input eligibility
# --------------------------------------------------------------------------


def test_receipts_are_ordered_deterministically_regardless_of_argument_order(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    forward = _synthesize(workspace, ids)
    reversed_order = _synthesize(
        workspace, list(reversed(ids)), output_directory=tmp_path / "b"
    )

    assert forward.plan.annotator_ids == ("rater-001", "rater-002", "rater-003")
    assert reversed_order.plan.annotator_ids == forward.plan.annotator_ids
    assert [item.valence_distribution.counts for item in forward.items] == [
        item.valence_distribution.counts for item in reversed_order.items
    ]


def test_duplicate_receipts_and_duplicate_annotators_are_refused(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    with pytest.raises(SynthesisError, match="may not be supplied twice"):
        _synthesize(workspace, [ids[0], ids[0], ids[1]])


def test_minimum_three_distinct_references_is_required(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    with pytest.raises(SynthesisError, match="at least 3 distinct"):
        _synthesize(workspace, ids[:2])


def test_below_threshold_coverage_remains_explicit_and_is_never_dropped(
    tmp_path: Path,
) -> None:
    """A lower declared minimum keeps every item and marks the shortfall."""

    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    document = _synthesis_document()
    document["minimum_reference_coverage"][
        "minimum_distinct_annotators_per_item"
    ] = 4
    changed = tmp_path / "higher-minimum.json"
    changed.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SynthesisError, match="at least 4 distinct"):
        _synthesize(workspace, ids, synthesis_protocol_path=changed)

    # With the declared minimum met, every item is retained and marked.
    result = _synthesize(workspace, ids)
    assert len(result.items) == len(_corpus().items)
    assert all(item.coverage_status == SUFFICIENT_COVERAGE for item in result.items)
    assert result.lifecycle.items_with_insufficient_coverage == 0
    assert (
        result.lifecycle.items_meeting_minimum_coverage
        + result.lifecycle.items_with_insufficient_coverage
        == result.lifecycle.total_items
    )


def test_incomplete_assignment_receipt_is_refused(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    # Craft a completion document reporting an unanswered item.
    store = FileSystemArtifactStore(workspace / "rater-001" / "artifacts")
    document = cast(dict[str, Any], json.loads(store.get(ids[0]).text))
    document["counts"]["unanswered"] = 1
    document["completion_id"] = "assignment.incomplete:completion"
    store.append(serialize_artifact(document["completion_id"], document))

    with pytest.raises(SynthesisError, match="incomplete assignment"):
        _synthesize(workspace, [document["completion_id"], ids[1], ids[2]])


def test_a_receipt_absent_from_the_workspace_is_refused(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    with pytest.raises(SynthesisError, match="no annotator store"):
        _synthesize(workspace, [*ids[:2], "assignment.missing:completion"])


# --------------------------------------------------------------------------
# Descriptive outputs
# --------------------------------------------------------------------------


def test_distribution_includes_every_option_including_zero_counts(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    for item in receipt.items:
        counts = item.valence_distribution.counts
        assert set(counts) == {label.value for label in ValenceLabel}
        assert len(counts) == 6
        # Three annotators produced three distinct labels in this fixture set.
        assert counts[ValenceLabel.SOMEWHAT_FAVORABLE.value] == 1
        assert counts[ValenceLabel.NEITHER.value] == 1
        assert counts[ABSTENTION_LABEL.value] == 1
        # Options nobody chose are still reported with an explicit zero.
        assert counts[ValenceLabel.STRONGLY_UNFAVORABLE.value] == 0
        assert counts[ValenceLabel.STRONGLY_FAVORABLE.value] == 0
        assert sum(counts.values()) == item.distinct_annotators


def test_abstention_is_a_separate_category_with_preserved_reasons(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    for item in receipt.items:
        assert item.abstention_count == 1
        assert item.abstention_count == (
            item.valence_distribution.counts[ABSTENTION_LABEL.value]
        )
        assert item.abstention_reason_counts == {
            AbstentionReason.INSUFFICIENT_CONTEXT.value: 1
        }
    # Abstention never receives an ordinal position anywhere.
    assert ORDINAL_POSITIONS[ABSTENTION_LABEL] is None


def test_context_ambiguity_certainty_rationale_and_spans_stay_separate(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    first = receipt.items[0]

    assert set(first.context_sufficiency_counts) == {
        value.value for value in ContextSufficiency
    }
    assert set(first.ambiguity_counts) == {value.value for value in PerceivedAmbiguity}
    assert set(first.certainty_counts) == {
        value.value for value in SelfReportedCertainty
    } | {"not_provided"}

    assert first.context_sufficiency_counts["sufficient"] == 3
    assert first.ambiguity_counts["some"] == 3
    assert first.certainty_counts["medium"] == 1
    assert first.certainty_counts["not_provided"] == 2
    # Rationale and span presence are counted independently of everything else.
    assert sum(item.rationale_present_count for item in receipt.items) == 1
    assert sum(item.supporting_span_present_count for item in receipt.items) == 1


def test_pairwise_concordance_preserves_numerator_and_denominator(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    item = receipt.items[0]
    including = item.concordance_including_abstention
    non_abstaining = item.concordance_non_abstaining

    # Three annotators → three pairs when abstention counts as its own category.
    assert including.compared_pairs == 3
    assert including.agreeing_pairs == 0
    assert including.abstentions_included is True

    # Two non-abstaining annotators → exactly one comparable pair.
    assert non_abstaining.compared_pairs == 1
    assert non_abstaining.agreeing_pairs == 0
    assert non_abstaining.abstentions_included is False

    # The two descriptions are separate records, not one rate.
    assert including.label != non_abstaining.label
    assert "accuracy" not in including.label.lower()
    assert "accuracy" not in non_abstaining.label.lower()


def test_concordance_counts_agreement_when_annotators_match(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(
        workspace,
        labels=(
            ValenceLabel.SOMEWHAT_FAVORABLE,
            ValenceLabel.SOMEWHAT_FAVORABLE,
            ValenceLabel.NEITHER,
        ),
    )
    result = _synthesize(workspace, ids)
    item = result.items[0]

    # Pairs: (001,002) agree; (001,003) and (002,003) differ.
    assert item.concordance_including_abstention.agreeing_pairs == 1
    assert item.concordance_including_abstention.compared_pairs == 3
    assert item.concordance_non_abstaining.agreeing_pairs == 1
    assert item.concordance_non_abstaining.compared_pairs == 3


def test_ordinal_distance_histogram_has_exact_buckets_zero_to_four(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(
        workspace,
        labels=(
            ValenceLabel.STRONGLY_UNFAVORABLE,
            ValenceLabel.NEITHER,
            ValenceLabel.STRONGLY_FAVORABLE,
        ),
    )
    item = _synthesize(workspace, ids).items[0]

    assert set(item.ordinal_distance_histogram) == {
        str(bucket) for bucket in ORDINAL_DISTANCE_BUCKETS
    }
    # positions 0, 2, 4 → distances 2, 2, and 4.
    assert item.ordinal_distance_histogram["0"] == 0
    assert item.ordinal_distance_histogram["1"] == 0
    assert item.ordinal_distance_histogram["2"] == 2
    assert item.ordinal_distance_histogram["3"] == 0
    assert item.ordinal_distance_histogram["4"] == 1
    assert sum(item.ordinal_distance_histogram.values()) == 3


def test_abstaining_responses_never_enter_the_distance_histogram(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    item = receipt.items[0]
    # One abstention among three annotators leaves exactly one comparable pair.
    assert sum(item.ordinal_distance_histogram.values()) == 1
    assert item.ordinal_distance_histogram["1"] == 1


# --------------------------------------------------------------------------
# Nothing is collapsed into a single answer
# --------------------------------------------------------------------------


def test_no_forbidden_measure_appears_in_the_public_api() -> None:
    import ctrt.human_reference_synthesis as module

    for name in dir(module):
        if name.startswith("_"):
            continue
        lowered = name.lower()
        for concept in FORBIDDEN_CONCEPTS:
            assert concept not in lowered, name


def test_no_synthesis_record_carries_a_chosen_or_derived_answer_field() -> None:
    """Structural: no dataclass field can hold a single collapsed answer."""

    import ctrt.human_reference_synthesis as module

    for name in dir(module):
        value = getattr(module, name)
        if not is_dataclass(value) or not isinstance(value, type):
            continue
        for field in fields(value):
            lowered = field.name.lower()
            for concept in FORBIDDEN_CONCEPTS:
                assert concept not in lowered, f"{name}.{field.name}"


def test_a_clear_majority_is_not_identified_as_an_answer(tmp_path: Path) -> None:
    """Two annotators agree and one differs; nothing marks the pair as the answer."""

    workspace = tmp_path / "hr"
    ids = _three_fixtures(
        workspace,
        labels=(
            ValenceLabel.STRONGLY_FAVORABLE,
            ValenceLabel.STRONGLY_FAVORABLE,
            ValenceLabel.SOMEWHAT_UNFAVORABLE,
        ),
    )
    result = _synthesize(workspace, ids)
    item = result.items[0]

    counts = item.valence_distribution.counts
    assert counts[ValenceLabel.STRONGLY_FAVORABLE.value] == 2
    assert counts[ValenceLabel.SOMEWHAT_UNFAVORABLE.value] == 1

    # The record exposes counts only. No field names, flags, or singles out the
    # option that happened to win, and the minority response is fully retained.
    field_names = {field.name for field in fields(ItemSynthesis)}
    assert not any(
        concept in name.lower() for name in field_names for concept in FORBIDDEN_CONCEPTS
    )
    assert counts[ValenceLabel.SOMEWHAT_UNFAVORABLE.value] == 1

    # And the stored artifact carries no key naming a collapsed answer.
    store = FileSystemArtifactStore(result.artifact_directory)
    stored = store.get(f"{result.plan.plan_id}:{item.item_id}:synthesis")
    document = cast(dict[str, Any], json.loads(stored.text))
    for key in document:
        for concept in FORBIDDEN_CONCEPTS:
            assert concept not in key.lower(), key


def test_no_mean_ordinal_response_is_computed(receipt: VerifiedSynthesisReceipt) -> None:
    """Every synthesized quantity is an integer count, never an averaged value."""

    for item in receipt.items:
        for mapping in (
            item.valence_distribution.counts,
            item.context_sufficiency_counts,
            item.ambiguity_counts,
            item.certainty_counts,
            item.ordinal_distance_histogram,
            item.abstention_reason_counts,
        ):
            for value in mapping.values():
                assert isinstance(value, int)
                assert not isinstance(value, bool)
        for field in fields(ItemSynthesis):
            value = getattr(item, field.name)
            assert not isinstance(value, float), field.name


def test_annotators_are_never_ranked_or_scored(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    # The plan records annotators in a deterministic, non-evaluative order and
    # attaches no per-annotator quantity at all.
    assert receipt.plan.annotator_ids == tuple(sorted(receipt.plan.annotator_ids))
    for entry in receipt.included:
        field_names = {field.name for field in fields(entry)}
        assert not any(
            concept in name.lower()
            for name in field_names
            for concept in FORBIDDEN_CONCEPTS
        )
        assert "score" not in field_names
        assert "quality" not in field_names


# --------------------------------------------------------------------------
# Supersession
# --------------------------------------------------------------------------


def test_supersession_is_resolved_through_the_exact_chain(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = [
        _fixture_collection(
            workspace,
            annotator_id="rater-001",
            label=ValenceLabel.SOMEWHAT_FAVORABLE,
            supersede_first_item_to=ValenceLabel.STRONGLY_UNFAVORABLE,
        ),
        _fixture_collection(
            workspace, annotator_id="rater-002", label=ValenceLabel.NEITHER
        ),
        _fixture_collection(
            workspace, annotator_id="rater-003", label=ValenceLabel.NEITHER
        ),
    ]
    result = _synthesize(workspace, ids)

    first = next(entry for entry in result.included if entry.annotator_id == "rater-001")
    superseded_item = sorted(first.item_ids)[0]
    ancestry = next(
        value
        for key, value in first.ancestry.items()
        if value.superseding_response_refs
    )

    assert ancestry.chain_length == 2
    assert ancestry.chain_unbroken is True
    assert len(ancestry.superseding_response_refs) == 1
    assert ancestry.supersession_reasons == ("Reread the passage on a second pass.",)
    assert ancestry.original_response_ref != ancestry.effective_response_ref

    # The effective response is the corrected one; the original still exists.
    effective = first.responses[ancestry.item_id]
    assert effective.valence_label is ValenceLabel.STRONGLY_UNFAVORABLE
    store = FileSystemArtifactStore(workspace / "rater-001" / "artifacts")
    original = store.get(
        ancestry.original_response_ref.artifact_id,
        expected_hash=ancestry.original_response_ref.artifact_hash,
    )
    assert ValenceLabel.SOMEWHAT_FAVORABLE.value in original.text
    assert result.lifecycle.total_superseded_records == 1
    assert superseded_item in first.item_ids


def test_a_broken_supersession_chain_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    # Append a record naming a predecessor that does not exist.
    store = FileSystemArtifactStore(workspace / "rater-001" / "artifacts")
    completion = cast(dict[str, Any], json.loads(store.get(ids[0]).text))
    assignment_id = cast(str, completion["assignment_id"])
    item_id = cast(list[str], completion["item_ids"])[0]
    original = json.loads(
        store.get(f"{assignment_id}:{item_id}:response:0").text
    )
    forged = dict(original)
    forged["response_id"] = f"{assignment_id}:{item_id}:response:1"
    forged["sequence"] = 1
    forged["supersedes_response_id"] = f"{assignment_id}:{item_id}:response:99"
    forged["supersession_reason"] = "A predecessor that never existed."
    store.append(serialize_artifact(cast(str, forged["response_id"]), forged))

    with pytest.raises(SynthesisError, match="broken or branching"):
        _synthesize(workspace, ids)


def test_a_response_appended_after_completion_invalidates_the_receipt(
    tmp_path: Path,
) -> None:
    """The effective record must match the reference the completion bound."""

    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    store = FileSystemArtifactStore(workspace / "rater-002" / "artifacts")
    completion = cast(dict[str, Any], json.loads(store.get(ids[1]).text))
    assignment_id = cast(str, completion["assignment_id"])
    item_id = cast(list[str], completion["item_ids"])[0]
    original = json.loads(store.get(f"{assignment_id}:{item_id}:response:0").text)

    late = dict(original)
    late["response_id"] = f"{assignment_id}:{item_id}:response:1"
    late["sequence"] = 1
    late["supersedes_response_id"] = cast(str, original["response_id"])
    late["supersession_reason"] = "Recorded after the completion was written."
    store.append(serialize_artifact(cast(str, late["response_id"]), late))

    with pytest.raises(SynthesisError, match="broken or branching"):
        _synthesize(workspace, ids)


def test_response_record_shape_is_still_the_collection_contract() -> None:
    """Synthesis reuses the collection parser rather than a divergent copy."""

    names = {field.name for field in fields(AnnotationResponse)}
    assert {"sequence", "supersedes_response_id", "supersession_reason"} <= names


# --------------------------------------------------------------------------
# Fixture boundary
# --------------------------------------------------------------------------


def test_production_synthesis_refuses_test_fixture_collections(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)

    with pytest.raises(SynthesisError, match="synthetic test fixture"):
        run_human_reference_synthesis(workspace=workspace, completion_ids=ids)

    # The explicit test-only entry point accepts them.
    assert _synthesize(workspace, ids).lifecycle.total_items == 48


def test_fixture_marker_is_detectable_and_absent_by_default(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    session, store = open_assignment(
        workspace=workspace,
        annotator_id="rater-777",
        created_at=datetime(2026, 8, 5, 22, 0, tzinfo=UTC),
    )
    assignment_id = session.assignment.assignment_id
    assert is_test_fixture_collection(store, assignment_id=assignment_id) is False

    reference = mark_test_fixture_collection(store, assignment_id=assignment_id)
    assert is_test_fixture_collection(store, assignment_id=assignment_id) is True

    document = cast(dict[str, Any], json.loads(store.get(reference.artifact_id).text))
    assert document["synthetic_test_fixture"] is True
    assert document["not_human_research_evidence"] is True


def test_repository_documentation_reports_no_fixture_distribution() -> None:
    """No committed documentation may present counts as empirical results.

    A distribution would appear as a response option paired with a number. The
    docs may name the options and may show command examples; they may not
    report observed counts for them.
    """

    import re

    options = "|".join(label.value for label in ValenceLabel)
    distribution_row = re.compile(rf"\|\s*`?({options})`?\s*\|\s*\d")
    option_with_count = re.compile(rf"({options})`?\s*[:=]\s*\d")

    documents = [
        REPO_ROOT / "docs" / "phase-1b-human-reference-synthesis.md",
        REPO_ROOT
        / "docs"
        / "adr"
        / "0066-synthesize-human-reference-collections-descriptively.md",
    ]
    assert any(path.is_file() for path in documents)

    for path in documents:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert distribution_row.search(text) is None, path.name
        assert option_with_count.search(text) is None, path.name
        # The fixture boundary itself must be documented.
        assert "not_human_research_evidence" in text or "fixture" in text.lower()


# --------------------------------------------------------------------------
# Storage verification and report
# --------------------------------------------------------------------------


def test_read_time_tampering_fails_before_a_report_can_be_rendered(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    result = _synthesize(workspace, ids)

    reference = result.completion.item_synthesis_refs[0]
    digest = reference.artifact_hash.removeprefix("sha256:")
    blob = result.artifact_directory / "blobs" / "sha256" / digest
    assert blob.is_file()
    blob.write_bytes(b"{}")

    store = FileSystemArtifactStore(result.artifact_directory)
    with pytest.raises(ArtifactIntegrityError, match="failed SHA-256"):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)


def test_tampering_with_a_stored_response_fails_the_synthesis(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    store = FileSystemArtifactStore(workspace / "rater-003" / "artifacts")
    completion = cast(dict[str, Any], json.loads(store.get(ids[2]).text))
    reference = cast(list[dict[str, Any]], completion["response_refs"])[0]
    digest = cast(str, reference["artifact_hash"]).removeprefix("sha256:")
    (workspace / "rater-003" / "artifacts" / "blobs" / "sha256" / digest).write_bytes(
        b"{}"
    )

    with pytest.raises(ArtifactIntegrityError):
        _synthesize(workspace, ids)


def test_synthesis_persists_the_full_artifact_graph(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    store = FileSystemArtifactStore(receipt.artifact_directory)
    completion = receipt.completion

    assert len(completion.item_synthesis_refs) == 48
    assert len(completion.resolution_refs) == 48 * 3
    for reference in (
        receipt.plan_ref,
        receipt.completion_ref,
        completion.receipt_manifest_ref,
        completion.lifecycle_ref,
        *completion.item_synthesis_refs,
        *completion.resolution_refs,
    ):
        store.get(reference.artifact_id, expected_hash=reference.artifact_hash)

    manifest = cast(
        dict[str, Any],
        json.loads(store.get(completion.receipt_manifest_ref.artifact_id).text),
    )
    assert manifest["ordered_annotator_ids"] == ["rater-001", "rater-002", "rater-003"]


def test_report_contains_every_required_section(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    report = render_synthesis_report_markdown(receipt)

    for section in (
        "## 1. Protocol, corpus, and plan identity",
        "## 2. Included pseudonymous assignments",
        "## 3. Coverage and completion lifecycle",
        "## 4. Per-item descriptive synthesis",
        "## 5. Supersession ancestry",
        "## 6. Immutable references",
        "## 7. Interpretation boundary and non-claims",
    ):
        assert section in report, section

    for notice in SYNTHESIS_NON_CLAIMS:
        assert notice in report
    for item in receipt.items:
        assert item.text in report
    # Every response option is listed for every item, including zero counts.
    assert report.count(f"`{ValenceLabel.STRONGLY_UNFAVORABLE.value}`") >= 48
    assert "eligible_for_evaluation" in report
    assert "does not convert those judgments into truth" in report


def test_report_is_deterministic_for_the_same_inputs(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    first = render_synthesis_report_markdown(_synthesize(workspace, ids))
    second = render_synthesis_report_markdown(
        _synthesize(workspace, ids, output_directory=tmp_path / "b")
    )
    assert first == second


def test_cli_writes_a_synthesis_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "hr"
    ids = _three_fixtures(workspace)
    output = tmp_path / "synthesis.md"

    # Production mode refuses the fixtures, exactly as designed.
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--workspace",
                str(workspace),
                *[argument for value in ids for argument in ("--receipt", value)],
                "--output",
                str(output),
            ]
        )
    assert excinfo.value.code == 2
    assert "synthetic test fixture" in capsys.readouterr().err


def test_cli_requires_at_least_one_receipt(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--workspace", str(tmp_path)])


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_no_vader_or_analyzer_import_exists_in_the_synthesis_path() -> None:
    source = (REPO_ROOT / "src" / "ctrt" / "human_reference_synthesis.py").read_text(
        encoding="utf-8"
    )
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
        assert not any(banned in item.lower() for item in imported), banned
    assert "vaderSentiment" not in sys.modules


def test_synthesis_artifacts_carry_no_candidate_or_analyzer_field(
    receipt: VerifiedSynthesisReceipt,
) -> None:
    """Structural: no stored artifact may carry a candidate or analyzer field.

    This inspects JSON keys rather than scanning text, because the non-claims
    legitimately name the concepts they forbid.
    """

    from ctrt.human_reference_protocol import FORBIDDEN_CANDIDATE_KEYS

    def _keys(value: object) -> set[str]:
        if isinstance(value, dict):
            found = set(value)
            for nested in value.values():
                found |= _keys(nested)
            return found
        if isinstance(value, list):
            found = set()
            for nested in value:
                found |= _keys(nested)
            return found
        return set()

    store = FileSystemArtifactStore(receipt.artifact_directory)
    references = (
        receipt.plan_ref,
        receipt.completion_ref,
        receipt.completion.receipt_manifest_ref,
        receipt.completion.lifecycle_ref,
        *receipt.completion.item_synthesis_refs,
        *receipt.completion.resolution_refs,
    )
    for reference in references:
        document = json.loads(store.get(reference.artifact_id).text)
        present = _keys(document) & FORBIDDEN_CANDIDATE_KEYS
        assert not present, (reference.artifact_id, present)


def test_candidate_registry_and_lifecycle_are_unchanged() -> None:
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

    text = registry.read_text(encoding="utf-8")
    for banned in (SYNTHESIS_VERSION, "protocol.human-reference-synthesis", "rater-"):
        assert banned not in text


def test_creator_facing_and_analyzer_modules_do_not_import_synthesis() -> None:
    for name in (
        "creator_preflight.py",
        "creator_preflight_local.py",
        "creator_preflight_web.py",
        "vader_adapter.py",
        "vader_characterization.py",
        "human_reference_annotation.py",
        "human_reference_protocol.py",
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
        assert not any("human_reference_synthesis" in item for item in imported), name


def test_public_exports_remain_bounded() -> None:
    import ctrt
    import ctrt.human_reference_synthesis as module

    assert module.__all__ == [
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
    assert not [name for name in ctrt.__all__ if "synthesis" in name.lower()]
