"""Canonical segmentation contracts for CTRT content analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class SegmentationKind(StrEnum):
    """Declared strategy used to derive segments from canonical content."""

    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    WINDOW = "window"
    DOCUMENT_STRUCTURE = "document_structure"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class SegmentationMethod:
    """Versioned identity and configuration for one segmentation strategy."""

    method_id: str
    method_version: str
    kind: SegmentationKind
    configuration: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.method_id.strip():
            raise ValueError("method_id must not be empty")
        if not self.method_version.strip():
            raise ValueError("method_version must not be empty")


@dataclass(frozen=True, slots=True)
class ContentSegment:
    """A zero-based half-open span derived from one canonical content item."""

    segment_id: str
    sequence_index: int
    start: int
    end: int
    text_hash: str
    label: str | None = None
    parent_segment_id: str | None = None

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id must not be empty")
        if self.sequence_index < 0:
            raise ValueError("sequence_index must be non-negative")
        if self.start < 0:
            raise ValueError("segment start must be non-negative")
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        if not self.text_hash.strip():
            raise ValueError("segment text_hash must not be empty")
        if self.parent_segment_id == self.segment_id:
            raise ValueError("segment may not be its own parent")


@dataclass(frozen=True, slots=True)
class SegmentationManifest:
    """Reproducible mapping from canonical content to analysis segments."""

    segmentation_id: str
    content_id: str
    content_length: int
    method: SegmentationMethod
    allow_overlap: bool
    complete_coverage: bool
    segments: tuple[ContentSegment, ...]
    warnings: tuple[str, ...] = ()
    coordinate_system: str = "unicode_codepoint_half_open"

    def __post_init__(self) -> None:
        if not self.segmentation_id.strip():
            raise ValueError("segmentation_id must not be empty")
        if not self.content_id.strip():
            raise ValueError("content_id must not be empty")
        if self.content_length <= 0:
            raise ValueError("content_length must be positive")
        if self.coordinate_system != "unicode_codepoint_half_open":
            raise ValueError("unsupported canonical coordinate system")

        ids = [segment.segment_id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("segment IDs must be unique")

        indices = [segment.sequence_index for segment in self.segments]
        if sorted(indices) != list(range(len(self.segments))):
            raise ValueError("sequence indices must be contiguous from zero")

        id_set = set(ids)
        for segment in self.segments:
            if segment.end > self.content_length:
                raise ValueError("segment end exceeds canonical content length")
            if (
                segment.parent_segment_id is not None
                and segment.parent_segment_id not in id_set
            ):
                raise ValueError("parent_segment_id must reference this manifest")

        ordered = sorted(self.segments, key=lambda segment: (segment.start, segment.end))
        previous_end = 0
        for segment in ordered:
            if not self.allow_overlap and segment.start < previous_end:
                raise ValueError("overlapping segments require allow_overlap=True")
            previous_end = max(previous_end, segment.end)

        if self.complete_coverage:
            if not ordered:
                raise ValueError("complete coverage requires at least one segment")
            coverage_end = 0
            for segment in ordered:
                if segment.start > coverage_end:
                    raise ValueError("complete coverage manifest contains a gap")
                coverage_end = max(coverage_end, segment.end)
            if coverage_end != self.content_length:
                raise ValueError("segments do not cover the complete content item")
