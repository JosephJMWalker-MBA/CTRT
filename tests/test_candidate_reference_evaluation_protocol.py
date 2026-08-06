from __future__ import annotations

import copy
import importlib.metadata
import json
import math
from collections.abc import Mapping
from pathlib import Path

import pytest

from ctrt.candidate_reference_evaluation_protocol import (
    CANDIDATE_BUCKETS,
    DEFAULT_ANNOTATION_PROTOCOL,
    DEFAULT_CORPUS,
    DEFAULT_EVALUATION_PROTOCOL,
    DEFAULT_REAL_CANDIDATE_REGISTRY,
    DEFAULT_SYNTHESIS_PROTOCOL,
    EVALUATION_PROTOCOL_VERSION,
    EXPECTED_HUMAN_MAPPING,
    REQUIRED_CANDIDATE_STATUS,
    REQUIRED_HUMAN_COVERAGE_STATUS,
    CandidateReferenceProtocolError,
    DirectionBucket,
    DirectionalCorrespondence,
    HumanDirectionalDistribution,
    load_candidate_reference_evaluation_protocol,
    load_default_evaluation_protocol,
    validate_repository_bindings,
)
from ctrt.human_reference_protocol import ValenceLabel
from ctrt.vader_adapter import (
    PRESERVED_OUTPUT_KEYS,
    VADER_ADAPTER_REVISION,
    VADER_ANALYZER_ID,
    VADER_CANDIDATE_ID,
    VADER_PINNED_VERSION,
    vader_configuration_hash,
)


def _document(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_document(tmp_path: Path, name: str, document: Mapping[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def _full_distribution() -> dict[str, int]:
    return {
        ValenceLabel.STRONGLY_UNFAVORABLE.value: 2,
        ValenceLabel.SOMEWHAT_UNFAVORABLE.value: 3,
        ValenceLabel.NEITHER.value: 4,
        ValenceLabel.SOMEWHAT_FAVORABLE.value: 5,
        ValenceLabel.STRONGLY_FAVORABLE.value: 6,
        ValenceLabel.CANNOT_DETERMINE.value: 7,
    }


def test_default_protocol_is_frozen_and_exactly_bound() -> None:
    protocol = load_default_evaluation_protocol()

    assert protocol.protocol_id == "protocol.vader-human-reference-evaluation"
    assert protocol.protocol_version == "0.1.0"
    assert protocol.candidate_id == VADER_CANDIDATE_ID
    assert protocol.analyzer_id == VADER_ANALYZER_ID
    assert protocol.adapter_revision == VADER_ADAPTER_REVISION
    assert protocol.distribution_version == VADER_PINNED_VERSION
    assert protocol.configuration_hash == vader_configuration_hash()
    assert protocol.preserved_output_keys == PRESERVED_OUTPUT_KEYS
    assert protocol.required_candidate_status == REQUIRED_CANDIDATE_STATUS
    assert protocol.required_item_coverage_status == REQUIRED_HUMAN_COVERAGE_STATUS
    assert tuple(item.bucket for item in protocol.thresholds) == CANDIDATE_BUCKETS
    assert dict(protocol.human_bucket_mapping) == dict(EXPECTED_HUMAN_MAPPING)
    assert protocol.artifact_hash.startswith("sha256:")
    assert len(protocol.artifact_hash) == 71


def test_repository_bindings_verify_without_loading_optional_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(distribution: str) -> str:
        raise AssertionError(f"optional distribution lookup attempted: {distribution}")

    monkeypatch.setattr(importlib.metadata, "version", fail_if_called)
    protocol = load_default_evaluation_protocol()
    bindings = validate_repository_bindings(protocol)

    assert bindings.registry_hash.startswith("sha256:")
    assert bindings.candidate.candidate_id == VADER_CANDIDATE_ID
    assert bindings.candidate.package.version == VADER_PINNED_VERSION
    assert bindings.annotation_protocol.protocol_id == protocol.annotation_protocol_id
    assert bindings.synthesis_protocol.protocol_id == protocol.synthesis_protocol_id
    assert bindings.corpus.corpus_id == protocol.corpus_id
    assert len(bindings.corpus.items) == 48


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (-1.0, DirectionBucket.UNFAVORABLE),
        (-0.05, DirectionBucket.UNFAVORABLE),
        (-0.049999, DirectionBucket.NEUTRAL),
        (0.0, DirectionBucket.NEUTRAL),
        (0.049999, DirectionBucket.NEUTRAL),
        (0.05, DirectionBucket.FAVORABLE),
        (1.0, DirectionBucket.FAVORABLE),
    ),
)
def test_compound_threshold_boundaries_are_frozen(
    value: float,
    expected: DirectionBucket,
) -> None:
    assert load_default_evaluation_protocol().classify_compound(value) is expected


@pytest.mark.parametrize("value", (-1.01, 1.01, math.inf, -math.inf, math.nan, True))
def test_compound_classification_fails_closed(value: float) -> None:
    with pytest.raises(CandidateReferenceProtocolError):
        load_default_evaluation_protocol().classify_compound(value)


def test_human_distribution_collapse_retains_original_categories_and_abstention() -> None:
    protocol = load_default_evaluation_protocol()
    original = _full_distribution()
    before = dict(original)

    collapsed = protocol.collapse_human_distribution(original)

    assert collapsed == HumanDirectionalDistribution(
        unfavorable=5,
        neutral=4,
        favorable=11,
        abstention=7,
    )
    assert collapsed.directional_denominator == 20
    assert collapsed.total_responses == 27
    assert original == before


def test_item_correspondence_preserves_counts_and_denominator() -> None:
    protocol = load_default_evaluation_protocol()
    human = protocol.collapse_human_distribution(_full_distribution())

    description = protocol.describe_correspondence(DirectionBucket.FAVORABLE, human)

    assert description == DirectionalCorrespondence(
        candidate_bucket=DirectionBucket.FAVORABLE,
        same_direction_count=11,
        unfavorable_count=5,
        neutral_count=4,
        favorable_count=11,
        directional_denominator=20,
        human_abstention_count=7,
    )
    assert not hasattr(description, "accuracy")
    assert not hasattr(description, "rate")


def test_candidate_abstention_cannot_be_forced_into_directional_correspondence() -> None:
    protocol = load_default_evaluation_protocol()
    human = protocol.collapse_human_distribution(_full_distribution())

    with pytest.raises(CandidateReferenceProtocolError):
        protocol.describe_correspondence(DirectionBucket.ABSTENTION, human)


@pytest.mark.parametrize(
    "counts",
    (
        {},
        {ValenceLabel.NEITHER.value: 1},
        {**_full_distribution(), "unexpected": 1},
        {**_full_distribution(), ValenceLabel.NEITHER.value: -1},
        {**_full_distribution(), ValenceLabel.NEITHER.value: True},
    ),
)
def test_human_distribution_requires_all_exact_nonnegative_integer_counts(
    counts: Mapping[str, int],
) -> None:
    with pytest.raises(CandidateReferenceProtocolError):
        load_default_evaluation_protocol().collapse_human_distribution(counts)


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (
            lambda document: document.__setitem__("status", "draft"),
            "must be frozen",
        ),
        (
            lambda document: _candidate(document).__setitem__(
                "compound_is_confidence", True
            ),
            "never be confidence",
        ),
        (
            lambda document: _preregistration(document).__setitem__(
                "threshold_tuning_after_observing_results_permitted", True
            ),
            "must be false",
        ),
        (
            lambda document: _lifecycle(document).__setitem__(
                "candidate_status_after", "selected_for_domain"
            ),
            "lifecycle unchanged",
        ),
        (
            lambda document: _mapping_block(document).__setitem__(
                "human_bucket_mapping",
                {
                    **_human_mapping(document),
                    ValenceLabel.STRONGLY_UNFAVORABLE.value: "favorable",
                },
            ),
            "preregistered collapse",
        ),
        (
            lambda document: _first_bucket(document).__setitem__(
                "upper_bound", -0.04
            ),
            "frozen upstream",
        ),
    ),
)
def test_protocol_tampering_fails_closed(
    mutator: object,
    message: str,
) -> None:
    document = copy.deepcopy(_document(DEFAULT_EVALUATION_PROTOCOL))
    assert callable(mutator)
    mutator(document)

    with pytest.raises(CandidateReferenceProtocolError, match=message):
        load_candidate_reference_evaluation_protocol(document)


def _candidate(document: dict[str, object]) -> dict[str, object]:
    value = document["candidate_binding"]
    assert isinstance(value, dict)
    return value


def _preregistration(document: dict[str, object]) -> dict[str, object]:
    value = document["preregistration_and_blinding"]
    assert isinstance(value, dict)
    return value


def _lifecycle(document: dict[str, object]) -> dict[str, object]:
    value = document["lifecycle_boundary"]
    assert isinstance(value, dict)
    return value


def _mapping_block(document: dict[str, object]) -> dict[str, object]:
    value = document["directional_mapping"]
    assert isinstance(value, dict)
    return value


def _human_mapping(document: dict[str, object]) -> dict[str, object]:
    value = _mapping_block(document)["human_bucket_mapping"]
    assert isinstance(value, dict)
    return value


def _first_bucket(document: dict[str, object]) -> dict[str, object]:
    buckets = _mapping_block(document)["candidate_buckets"]
    assert isinstance(buckets, list)
    first = buckets[0]
    assert isinstance(first, dict)
    return first


def test_registry_status_and_configuration_drift_fail_repository_validation(
    tmp_path: Path,
) -> None:
    protocol = load_default_evaluation_protocol()
    for field_name, value in (
        ("status", "selected_for_domain"),
        ("configuration_hash", "sha256:" + "0" * 64),
    ):
        registry = copy.deepcopy(_document(DEFAULT_REAL_CANDIDATE_REGISTRY))
        candidates = registry["candidates"]
        assert isinstance(candidates, list)
        candidate = candidates[0]
        assert isinstance(candidate, dict)
        candidate[field_name] = value
        path = _write_document(tmp_path, f"registry-{field_name}.json", registry)
        with pytest.raises(CandidateReferenceProtocolError):
            validate_repository_bindings(protocol, registry_path=path)


def test_human_protocol_and_corpus_drift_fail_repository_validation(
    tmp_path: Path,
) -> None:
    protocol = load_default_evaluation_protocol()

    annotation = copy.deepcopy(_document(DEFAULT_ANNOTATION_PROTOCOL))
    annotation["protocol_version"] = "9.9.9"
    annotation_path = _write_document(tmp_path, "annotation.json", annotation)
    with pytest.raises(CandidateReferenceProtocolError, match="annotation protocol"):
        validate_repository_bindings(
            protocol,
            annotation_protocol_path=annotation_path,
        )

    synthesis = copy.deepcopy(_document(DEFAULT_SYNTHESIS_PROTOCOL))
    synthesis["compatible_corpus_version"] = "9.9.9"
    synthesis_path = _write_document(tmp_path, "synthesis.json", synthesis)
    with pytest.raises(CandidateReferenceProtocolError):
        validate_repository_bindings(
            protocol,
            synthesis_protocol_path=synthesis_path,
        )

    corpus = copy.deepcopy(_document(DEFAULT_CORPUS))
    corpus["corpus_version"] = "9.9.9"
    corpus_path = _write_document(tmp_path, "corpus.json", corpus)
    with pytest.raises(CandidateReferenceProtocolError, match="corpus"):
        validate_repository_bindings(protocol, corpus_path=corpus_path)


def test_protocol_declares_descriptions_not_selection_or_product_authorization() -> None:
    protocol = load_default_evaluation_protocol()

    assert "accuracy" in protocol.prohibited_measures
    assert "candidate selection" in protocol.prohibited_measures
    assert "candidate lifecycle advancement" in protocol.prohibited_measures
    assert "creator-facing authorization" in protocol.prohibited_measures
    assert "threshold tuning" in protocol.prohibited_measures
    assert all("ground truth" not in item.lower() for item in protocol.purpose)
    assert any("not accuracy" in item for item in protocol.non_claims)
    assert any("does not advance" in item for item in protocol.non_claims)


def test_module_exports_only_the_bounded_protocol_surface() -> None:
    import ctrt.candidate_reference_evaluation_protocol as module

    assert module.__all__ == [
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
    assert EVALUATION_PROTOCOL_VERSION.endswith("@0.1.0")
