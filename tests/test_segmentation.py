import pytest

from ctrt.segmentation import (
    ContentSegment,
    SegmentationKind,
    SegmentationManifest,
    SegmentationMethod,
)


def method() -> SegmentationMethod:
    return SegmentationMethod(
        method_id="synthetic.paragraphs",
        method_version="1.0.0",
        kind=SegmentationKind.PARAGRAPH,
    )


def segment(
    segment_id: str,
    sequence_index: int,
    start: int,
    end: int,
) -> ContentSegment:
    return ContentSegment(
        segment_id=segment_id,
        sequence_index=sequence_index,
        start=start,
        end=end,
        text_hash=f"sha256:{segment_id}",
    )


def test_complete_non_overlapping_manifest_is_valid() -> None:
    manifest = SegmentationManifest(
        segmentation_id="segmentation-001",
        content_id="content-001",
        content_length=20,
        method=method(),
        allow_overlap=False,
        complete_coverage=True,
        segments=(
            segment("segment-001", 0, 0, 10),
            segment("segment-002", 1, 10, 20),
        ),
    )

    assert manifest.complete_coverage


def test_overlap_must_be_declared() -> None:
    with pytest.raises(ValueError, match="overlapping segments"):
        SegmentationManifest(
            segmentation_id="segmentation-001",
            content_id="content-001",
            content_length=20,
            method=method(),
            allow_overlap=False,
            complete_coverage=True,
            segments=(
                segment("segment-001", 0, 0, 12),
                segment("segment-002", 1, 10, 20),
            ),
        )


def test_complete_coverage_may_not_hide_a_gap() -> None:
    with pytest.raises(ValueError, match="contains a gap"):
        SegmentationManifest(
            segmentation_id="segmentation-001",
            content_id="content-001",
            content_length=20,
            method=method(),
            allow_overlap=False,
            complete_coverage=True,
            segments=(
                segment("segment-001", 0, 0, 8),
                segment("segment-002", 1, 10, 20),
            ),
        )


def test_sequence_indices_must_be_contiguous() -> None:
    with pytest.raises(ValueError, match="contiguous from zero"):
        SegmentationManifest(
            segmentation_id="segmentation-001",
            content_id="content-001",
            content_length=20,
            method=method(),
            allow_overlap=False,
            complete_coverage=True,
            segments=(
                segment("segment-001", 0, 0, 10),
                segment("segment-002", 2, 10, 20),
            ),
        )


def test_segment_cannot_extend_past_canonical_content() -> None:
    with pytest.raises(ValueError, match="exceeds canonical content length"):
        SegmentationManifest(
            segmentation_id="segmentation-001",
            content_id="content-001",
            content_length=20,
            method=method(),
            allow_overlap=False,
            complete_coverage=False,
            segments=(segment("segment-001", 0, 0, 21),),
        )
