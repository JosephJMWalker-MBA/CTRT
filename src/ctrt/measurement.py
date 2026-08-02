"""Analysis-target and evidence-provenance contracts for CTRT measurements."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AnalysisTargetKind(StrEnum):
    """Canonical unit presented to an analyzer."""

    CONTENT_ITEM = "content-item"
    SEGMENT = "segment"


class EvidenceSupportStatus(StrEnum):
    """Origin and availability of local evidence for a result."""

    PROVIDED_NATIVE = "provided-native"
    PROVIDED_POST_HOC = "provided-post-hoc"
    PROVIDED_DETERMINISTIC = "provided-deterministic"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AnalysisTarget:
    """Exact canonical content coordinates analyzed by one instrument."""

    kind: AnalysisTargetKind
    content_id: str
    start: int
    end: int
    extraction_ref: str
    segmentation_id: str | None = None
    segment_id: str | None = None
    coordinate_system: str = "unicode_codepoint_half_open"

    def __post_init__(self) -> None:
        if not self.content_id.strip():
            raise ValueError("analysis target content_id must not be empty")
        if self.start < 0:
            raise ValueError("analysis target start must be non-negative")
        if self.end <= self.start:
            raise ValueError("analysis target end must be greater than start")
        if not self.extraction_ref.strip():
            raise ValueError("analysis target extraction_ref must not be empty")
        if self.coordinate_system != "unicode_codepoint_half_open":
            raise ValueError("unsupported analysis target coordinate system")
        if self.kind is AnalysisTargetKind.CONTENT_ITEM:
            if self.segmentation_id is not None or self.segment_id is not None:
                raise ValueError("content-item target may not identify a segmentation or segment")
            return
        if self.segmentation_id is None or not self.segmentation_id.strip():
            raise ValueError("segment target requires segmentation_id")
        if self.segment_id is None or not self.segment_id.strip():
            raise ValueError("segment target requires segment_id")

    @classmethod
    def for_content_item(
        cls,
        *,
        content_id: str,
        content_length: int,
        extraction_ref: str,
    ) -> AnalysisTarget:
        """Construct a target covering one complete canonical content item."""

        return cls(
            kind=AnalysisTargetKind.CONTENT_ITEM,
            content_id=content_id,
            start=0,
            end=content_length,
            extraction_ref=extraction_ref,
        )


@dataclass(frozen=True, slots=True)
class EvidenceSupport:
    """Declares whether evidence is native, attributed later, or unavailable."""

    status: EvidenceSupportStatus
    method_id: str | None = None
    method_version: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.method_id is not None and not self.method_id.strip():
            raise ValueError("evidence method_id must be non-empty when provided")
        if self.method_version is not None and not self.method_version.strip():
            raise ValueError("evidence method_version must be non-empty when provided")
        requires_method = self.status in {
            EvidenceSupportStatus.PROVIDED_POST_HOC,
            EvidenceSupportStatus.PROVIDED_DETERMINISTIC,
        }
        if requires_method and (self.method_id is None or self.method_version is None):
            raise ValueError("post-hoc or deterministic evidence requires method identity")
        if not requires_method and (
            self.method_id is not None or self.method_version is not None
        ):
            raise ValueError("native or unavailable evidence may not name a separate method")
