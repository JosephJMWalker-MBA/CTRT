"""Provider-neutral, dependency-free contracts for CTRT Phase 0."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ctrt.confidence import ConfidenceVector
from ctrt.measurement import AnalysisTarget, EvidenceSupport, EvidenceSupportStatus


class SourceType(StrEnum):
    """How a canonical content item entered CTRT."""

    RAW_TEXT = "raw_text"
    WEBPAGE = "webpage"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class ResultStatus(StrEnum):
    """Outcome of one analyzer attempt."""

    SUCCESS = "success"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ContentItem:
    """Canonical bounded content presented to analyzers."""

    content_id: str
    text: str
    source_type: SourceType
    content_hash: str
    source_uri: str | None = None
    language: str | None = None
    extraction_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.content_id.strip():
            raise ValueError("content_id must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if not self.content_hash.strip():
            raise ValueError("content_hash must not be empty")
        if self.extraction_ref is not None and not self.extraction_ref.strip():
            raise ValueError("extraction_ref must not be empty when provided")

    @property
    def canonical_extraction_ref(self) -> str:
        """Return the exact extraction identity used by downstream targets."""

        return self.extraction_ref or f"content-item:{self.content_id}"


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """A zero-based half-open canonical text span supporting an analyzer output."""

    start: int
    end: int
    label: str | None = None
    score: float | None = None

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("evidence span start must be non-negative")
        if self.end <= self.start:
            raise ValueError("evidence span end must be greater than start")
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError("evidence span score must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class AnalyzerIdentity:
    """Identity and version information required for reproducibility."""

    analyzer_id: str
    provider: str
    model_id: str
    model_version: str
    adapter_version: str
    taxonomy_id: str
    taxonomy_version: str

    def __post_init__(self) -> None:
        values = (
            self.analyzer_id,
            self.provider,
            self.model_id,
            self.model_version,
            self.adapter_version,
            self.taxonomy_id,
            self.taxonomy_version,
        )
        if any(not value.strip() for value in values):
            raise ValueError("analyzer identity fields must not be empty")


@dataclass(frozen=True, slots=True)
class NormalizedScore:
    """A declared normalized score without discarding the raw output."""

    key: str
    value: float
    lower_bound: float
    upper_bound: float

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("score key must not be empty")
        if self.lower_bound >= self.upper_bound:
            raise ValueError("lower_bound must be less than upper_bound")
        if not self.lower_bound <= self.value <= self.upper_bound:
            raise ValueError("score value must fall within declared bounds")


@dataclass(frozen=True, slots=True)
class ModelResult:
    """Canonical result returned by one analyzer for one dimension."""

    result_id: str
    content_id: str
    dimension_id: str
    dimension_version: str
    status: ResultStatus
    analyzer: AnalyzerIdentity
    analysis_target: AnalysisTarget
    evidence_support: EvidenceSupport
    confidence: ConfidenceVector
    raw_output: Mapping[str, object]
    normalized_scores: tuple[NormalizedScore, ...] = ()
    evidence_spans: tuple[EvidenceSpan, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    duration_ms: float | None = None
    configuration: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = (
            self.result_id,
            self.content_id,
            self.dimension_id,
            self.dimension_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("result identity fields must not be empty")
        if self.content_id != self.analysis_target.content_id:
            raise ValueError("result content_id must match analysis target content_id")
        if (
            self.confidence.extraction_quality.evidence_ref
            != self.analysis_target.extraction_ref
        ):
            raise ValueError(
                "confidence extraction evidence_ref must match analysis target extraction_ref"
            )
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if self.status is ResultStatus.SUCCESS and self.errors:
            raise ValueError("successful results may not contain errors")
        if self.status is ResultStatus.FAILED and not self.errors:
            raise ValueError("failed results must contain at least one error")
        if (
            self.status in {ResultStatus.ABSTAINED, ResultStatus.FAILED}
            and self.normalized_scores
        ):
            raise ValueError("abstained or failed results may not contain normalized scores")
        if (
            self.status is ResultStatus.ABSTAINED
            and not self.confidence.system_abstention.triggered
        ):
            raise ValueError("abstained result requires triggered system abstention")
        if (
            self.confidence.system_abstention.triggered
            and self.status not in {ResultStatus.ABSTAINED, ResultStatus.FAILED}
        ):
            raise ValueError("triggered system abstention requires abstained or failed result")

        if self.evidence_support.status is EvidenceSupportStatus.UNAVAILABLE:
            if self.evidence_spans:
                raise ValueError("unavailable evidence may not contain evidence spans")
        elif not self.evidence_spans:
            raise ValueError("provided evidence support requires at least one evidence span")

        for span in self.evidence_spans:
            if span.start < self.analysis_target.start or span.end > self.analysis_target.end:
                raise ValueError("evidence span must fall within the analysis target")


@runtime_checkable
class Analyzer(Protocol):
    """Replaceable instrument that measures one declared CTRT dimension."""

    @property
    def dimension_id(self) -> str:
        """Stable identifier for the construct this analyzer attempts to measure."""
        ...

    @property
    def implementation_revision(self) -> str:
        """Immutable implementation revision loaded for execution."""
        ...

    @property
    def execution_configuration(self) -> Mapping[str, object]:
        """Complete configuration hashed by the frozen experiment plan."""
        ...

    @property
    def identity(self) -> AnalyzerIdentity:
        """Complete analyzer and taxonomy identity."""
        ...

    def analyze(self, content: ContentItem) -> ModelResult:
        """Analyze one canonical content item without changing it."""
        ...
