"""CTRT constitutional domain contracts.

This package intentionally contains no machine-learning implementation during Phase 0.
"""

from ctrt.confidence import (
    AggregationPolicy,
    AgreementStatus,
    AmbiguityBudget,
    AmbiguityBudgetStatus,
    Applicability,
    ApplicabilityStatus,
    Calibration,
    CalibrationStatus,
    ConfidenceSignal,
    ConfidenceVector,
    ExtractionQuality,
    ExtractionQualityStatus,
    ForbiddenConfidenceOutput,
    InstrumentProbability,
    InstrumentProbabilitySource,
    InterInstrumentAgreement,
    SystemAbstention,
    required_abstention_reasons,
)
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
from ctrt.measurement import (
    AnalysisTarget,
    AnalysisTargetKind,
    EvidenceSupport,
    EvidenceSupportStatus,
)
from ctrt.segmentation import (
    ContentSegment,
    SegmentationKind,
    SegmentationManifest,
    SegmentationMethod,
)
from ctrt.taxonomy import (
    TaxonomyComparison,
    TaxonomyDisplayMode,
    TaxonomyRef,
    TaxonomyRelation,
)

__all__ = [
    "AggregationPolicy",
    "AgreementStatus",
    "AmbiguityBudget",
    "AmbiguityBudgetStatus",
    "AnalysisTarget",
    "AnalysisTargetKind",
    "Analyzer",
    "AnalyzerIdentity",
    "Applicability",
    "ApplicabilityStatus",
    "Calibration",
    "CalibrationStatus",
    "ConfidenceSignal",
    "ConfidenceVector",
    "ContentItem",
    "ContentSegment",
    "DimensionStatus",
    "EligibilityDecision",
    "EvidenceSpan",
    "EvidenceSupport",
    "EvidenceSupportStatus",
    "ExtractionQuality",
    "ExtractionQualityStatus",
    "ForbiddenConfidenceOutput",
    "InstrumentProbability",
    "InstrumentProbabilitySource",
    "InterInstrumentAgreement",
    "ModelResult",
    "NormalizedScore",
    "ReportEligibility",
    "ResultStatus",
    "SegmentationKind",
    "SegmentationManifest",
    "SegmentationMethod",
    "SourceType",
    "SystemAbstention",
    "TaxonomyComparison",
    "TaxonomyDisplayMode",
    "TaxonomyRef",
    "TaxonomyRelation",
    "evaluate_dimension_eligibility",
    "required_abstention_reasons",
]
