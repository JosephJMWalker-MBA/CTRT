import pytest

from ctrt.measurement import (
    AnalysisTarget,
    AnalysisTargetKind,
    EvidenceSupport,
    EvidenceSupportStatus,
)


def test_content_item_target_forbids_segment_identity() -> None:
    with pytest.raises(ValueError, match="may not identify"):
        AnalysisTarget(
            kind=AnalysisTargetKind.CONTENT_ITEM,
            content_id="content-001",
            start=0,
            end=20,
            extraction_ref="content-item:content-001",
            segmentation_id="segmentation-001",
            segment_id="segment-001",
        )


def test_segment_target_requires_manifest_and_segment() -> None:
    with pytest.raises(ValueError, match="segmentation_id"):
        AnalysisTarget(
            kind=AnalysisTargetKind.SEGMENT,
            content_id="content-001",
            start=5,
            end=15,
            extraction_ref="extraction:001",
            segment_id="segment-001",
        )


def test_segment_target_preserves_canonical_coordinates() -> None:
    target = AnalysisTarget(
        kind=AnalysisTargetKind.SEGMENT,
        content_id="content-001",
        start=5,
        end=15,
        extraction_ref="extraction:001",
        segmentation_id="segmentation-001",
        segment_id="segment-001",
    )

    assert target.coordinate_system == "unicode_codepoint_half_open"
    assert target.end - target.start == 10


def test_post_hoc_evidence_requires_method_identity() -> None:
    with pytest.raises(ValueError, match="requires method identity"):
        EvidenceSupport(status=EvidenceSupportStatus.PROVIDED_POST_HOC)


def test_unavailable_evidence_cannot_name_method() -> None:
    with pytest.raises(ValueError, match="may not name"):
        EvidenceSupport(
            status=EvidenceSupportStatus.UNAVAILABLE,
            method_id="attribution.example",
            method_version="1.0.0",
        )
