"""CTRT constitutional domain contracts.

This package intentionally contains no machine-learning implementation during Phase 0.
"""

from ctrt.contracts import (
    Analyzer,
    AnalyzerIdentity,
    ContentItem,
    EvidenceSpan,
    ModelResult,
    NormalizedScore,
    ResultStatus,
    SourceType,
)
from ctrt.eligibility import (
    DimensionStatus,
    EligibilityDecision,
    ReportEligibility,
    evaluate_dimension_eligibility,
)

__all__ = [
    "Analyzer",
    "AnalyzerIdentity",
    "ContentItem",
    "DimensionStatus",
    "EligibilityDecision",
    "EvidenceSpan",
    "ModelResult",
    "NormalizedScore",
    "ReportEligibility",
    "ResultStatus",
    "SourceType",
    "evaluate_dimension_eligibility",
]
