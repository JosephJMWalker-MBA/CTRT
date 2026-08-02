import pytest

from ctrt.taxonomy import (
    TaxonomyComparison,
    TaxonomyDisplayMode,
    TaxonomyRef,
    TaxonomyRelation,
)


def taxonomy(taxonomy_id: str, version: str = "1.0.0") -> TaxonomyRef:
    return TaxonomyRef(taxonomy_id=taxonomy_id, taxonomy_version=version)


def test_identical_relation_requires_same_taxonomy() -> None:
    with pytest.raises(ValueError, match="matching taxonomy identities"):
        TaxonomyComparison(
            comparison_id="comparison-001",
            comparison_version="1.0.0",
            left=taxonomy("sentiment.binary"),
            right=taxonomy("sentiment.three-class"),
            relation=TaxonomyRelation.IDENTICAL,
            display_mode=TaxonomyDisplayMode.MAPPED_COMPARISON,
        )


def test_partial_overlap_requires_information_loss() -> None:
    with pytest.raises(ValueError, match="information_loss"):
        TaxonomyComparison(
            comparison_id="comparison-001",
            comparison_version="1.0.0",
            left=taxonomy("sentiment.binary"),
            right=taxonomy("sentiment.three-class"),
            relation=TaxonomyRelation.PARTIAL_OVERLAP,
            display_mode=TaxonomyDisplayMode.SIDE_BY_SIDE,
            mapping_method_id="mapping.sentiment",
            mapping_method_version="0.1.0",
        )


def test_incompatible_taxonomies_require_side_by_side_display() -> None:
    with pytest.raises(ValueError, match="side-by-side"):
        TaxonomyComparison(
            comparison_id="comparison-001",
            comparison_version="1.0.0",
            left=taxonomy("emotion.seven-class"),
            right=taxonomy("toxicity.multi-label"),
            relation=TaxonomyRelation.INCOMPATIBLE,
            display_mode=TaxonomyDisplayMode.MAPPED_COMPARISON,
        )


def test_phase_zero_never_permits_score_combination() -> None:
    with pytest.raises(ValueError, match="may not combine scores"):
        TaxonomyComparison(
            comparison_id="comparison-001",
            comparison_version="1.0.0",
            left=taxonomy("sentiment.binary"),
            right=taxonomy("sentiment.three-class"),
            relation=TaxonomyRelation.COMPATIBLE_MAPPING,
            display_mode=TaxonomyDisplayMode.MAPPED_COMPARISON,
            score_combination_permitted=True,
            mapping_method_id="mapping.sentiment",
            mapping_method_version="0.1.0",
        )


def test_compatible_mapping_records_method_without_claiming_identity() -> None:
    comparison = TaxonomyComparison(
        comparison_id="comparison-001",
        comparison_version="1.0.0",
        left=taxonomy("sentiment.binary"),
        right=taxonomy("sentiment.three-class"),
        relation=TaxonomyRelation.COMPATIBLE_MAPPING,
        display_mode=TaxonomyDisplayMode.MAPPED_COMPARISON,
        mapping_method_id="mapping.sentiment",
        mapping_method_version="0.1.0",
        evidence_ref="protocol:sentiment-mapping-study",
    )

    assert comparison.relation is TaxonomyRelation.COMPATIBLE_MAPPING
    assert comparison.score_combination_permitted is False
