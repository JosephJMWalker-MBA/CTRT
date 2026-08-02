"""Dependency-free orchestration for the first CTRT Content Analysis Workbench slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from ctrt.confidence import (
    AgreementStatus,
    AmbiguityBudget,
    AmbiguityBudgetStatus,
    Applicability,
    ApplicabilityStatus,
    Calibration,
    CalibrationStatus,
    ConfidenceVector,
    ExtractionQuality,
    InstrumentProbability,
    InterInstrumentAgreement,
    SystemAbstention,
)
from ctrt.contracts import Analyzer, ContentItem, ModelResult, ResultStatus
from ctrt.measurement import AnalysisTarget
from ctrt.taxonomy import (
    TaxonomyComparison,
    TaxonomyDisplayMode,
    TaxonomyRef,
    TaxonomyRelation,
)


class WorkbenchReportStatus(StrEnum):
    """Outcome of comparing a set of immutable analyzer results."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DisagreementRecord:
    """Material disagreement preserved without rewriting analyzer results."""

    result_ids: tuple[str, ...]
    description: str
    material: bool

    def __post_init__(self) -> None:
        if len(self.result_ids) < 2:
            raise ValueError("disagreement requires at least two result IDs")
        if len(self.result_ids) != len(set(self.result_ids)):
            raise ValueError("disagreement result IDs must be unique")
        if not self.description.strip():
            raise ValueError("disagreement description must not be empty")


@dataclass(frozen=True, slots=True)
class WorkbenchComparison:
    """Side-by-side comparison record assembled from immutable results."""

    comparison_id: str
    content_id: str
    dimension_id: str
    dimension_version: str
    analysis_target: AnalysisTarget
    result_ids: tuple[str, ...]
    analyzer_ids: tuple[str, ...]
    taxonomy_comparisons: tuple[TaxonomyComparison, ...]
    confidence: ConfidenceVector
    status: WorkbenchReportStatus
    disagreements: tuple[DisagreementRecord, ...] = ()
    limitations: tuple[str, ...] = ()
    score_combination_permitted: bool = False

    def __post_init__(self) -> None:
        identity_fields = (
            self.comparison_id,
            self.content_id,
            self.dimension_id,
            self.dimension_version,
        )
        if any(not value.strip() for value in identity_fields):
            raise ValueError("comparison identity fields must not be empty")
        if self.content_id != self.analysis_target.content_id:
            raise ValueError("comparison content_id must match analysis target")
        if len(self.result_ids) < 2 or len(self.analyzer_ids) < 2:
            raise ValueError("side-by-side comparison requires at least two analyzers")
        if len(self.result_ids) != len(self.analyzer_ids):
            raise ValueError("comparison result and analyzer counts must match")
        if len(self.result_ids) != len(set(self.result_ids)):
            raise ValueError("comparison result IDs must be unique")
        if len(self.analyzer_ids) != len(set(self.analyzer_ids)):
            raise ValueError("comparison analyzer IDs must be unique")
        if self.score_combination_permitted:
            raise ValueError("initial workbench comparisons may not combine scores")
        if self.status is WorkbenchReportStatus.ABSTAINED:
            if not self.confidence.system_abstention.triggered:
                raise ValueError("abstained comparison requires triggered system abstention")
        elif self.confidence.system_abstention.triggered:
            raise ValueError("triggered system abstention requires abstained comparison status")
        if any(not limitation.strip() for limitation in self.limitations):
            raise ValueError("comparison limitations must not be empty")


@dataclass(frozen=True, slots=True)
class WorkbenchRun:
    """One reproducible execution of registered analyzers on shared content."""

    run_id: str
    content_id: str
    analyzer_ids: tuple[str, ...]
    results: tuple[ModelResult, ...]
    comparison: WorkbenchComparison

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.content_id.strip():
            raise ValueError("workbench run identity fields must not be empty")
        if len(self.analyzer_ids) < 2:
            raise ValueError("workbench run requires at least two analyzers")
        if len(self.analyzer_ids) != len(set(self.analyzer_ids)):
            raise ValueError("workbench analyzer IDs must be unique")
        if len(self.results) != len(self.analyzer_ids):
            raise ValueError("workbench run must preserve one result per analyzer")
        if tuple(result.analyzer.analyzer_id for result in self.results) != self.analyzer_ids:
            raise ValueError("workbench result order must match analyzer order")
        if any(result.content_id != self.content_id for result in self.results):
            raise ValueError("workbench results must reference the run content")
        if self.comparison.content_id != self.content_id:
            raise ValueError("workbench comparison must reference the run content")
        if self.comparison.result_ids != tuple(result.result_id for result in self.results):
            raise ValueError("comparison must reference every preserved result in order")


class AnalyzerRegistry:
    """Small provider-neutral registry for executable analyzer instances."""

    def __init__(self) -> None:
        self._analyzers: dict[str, Analyzer] = {}

    def register(self, analyzer: Analyzer) -> None:
        """Register one analyzer identity without selecting it for production use."""

        analyzer_id = analyzer.identity.analyzer_id
        if analyzer_id in self._analyzers:
            raise ValueError(f"analyzer already registered: {analyzer_id}")
        if not analyzer.dimension_id.strip():
            raise ValueError("registered analyzer dimension_id must not be empty")
        if not analyzer.implementation_revision.strip():
            raise ValueError("registered analyzer implementation_revision must not be empty")
        if analyzer.identity.adapter_version == "":
            raise ValueError("registered analyzer adapter_version must not be empty")
        _ = analyzer.execution_configuration
        self._analyzers[analyzer_id] = analyzer

    def get(self, analyzer_id: str) -> Analyzer:
        """Return a registered analyzer or fail explicitly."""

        try:
            return self._analyzers[analyzer_id]
        except KeyError as exc:
            raise KeyError(f"analyzer is not registered: {analyzer_id}") from exc

    def analyzer_ids(self, dimension_id: str | None = None) -> tuple[str, ...]:
        """List registered identities, optionally restricted to one dimension."""

        if dimension_id is None:
            return tuple(self._analyzers)
        return tuple(
            analyzer_id
            for analyzer_id, analyzer in self._analyzers.items()
            if analyzer.dimension_id == dimension_id
        )


class ContentAnalysisWorkbench:
    """Execute and compare analyzers while preserving every original result."""

    def __init__(self, registry: AnalyzerRegistry) -> None:
        self._registry = registry

    def run_content_item(
        self,
        *,
        run_id: str,
        content: ContentItem,
        analyzer_ids: tuple[str, ...],
    ) -> WorkbenchRun:
        """Run at least two analyzers against the same complete canonical item."""

        if len(analyzer_ids) < 2:
            raise ValueError("side-by-side workbench run requires at least two analyzers")
        if len(analyzer_ids) != len(set(analyzer_ids)):
            raise ValueError("workbench analyzer IDs must be unique")

        analyzers = tuple(self._registry.get(analyzer_id) for analyzer_id in analyzer_ids)
        dimensions = {analyzer.dimension_id for analyzer in analyzers}
        if len(dimensions) != 1:
            raise ValueError("one workbench comparison requires a shared dimension_id")

        results = tuple(analyzer.analyze(content) for analyzer in analyzers)
        expected_target = AnalysisTarget.for_content_item(
            content_id=content.content_id,
            content_length=len(content.text),
            extraction_ref=f"content-item:{content.content_id}",
        )
        self._validate_results(
            content=content,
            analyzers=analyzers,
            results=results,
            expected_target=expected_target,
        )
        comparison = self._compare(
            run_id=run_id,
            content=content,
            results=results,
            expected_target=expected_target,
        )
        return WorkbenchRun(
            run_id=run_id,
            content_id=content.content_id,
            analyzer_ids=analyzer_ids,
            results=results,
            comparison=comparison,
        )

    @staticmethod
    def _validate_results(
        *,
        content: ContentItem,
        analyzers: tuple[Analyzer, ...],
        results: tuple[ModelResult, ...],
        expected_target: AnalysisTarget,
    ) -> None:
        for analyzer, result in zip(analyzers, results, strict=True):
            if result.content_id != content.content_id:
                raise ValueError("analyzer result references unexpected content")
            if result.dimension_id != analyzer.dimension_id:
                raise ValueError("analyzer result dimension does not match registration")
            if result.analyzer != analyzer.identity:
                raise ValueError("analyzer result identity does not match registration")
            if result.analysis_target != expected_target:
                raise ValueError("all analyzers must receive the same canonical target")
            if result.configuration != analyzer.execution_configuration:
                raise ValueError("analyzer result configuration does not match runtime configuration")

    @staticmethod
    def _compare(
        *,
        run_id: str,
        content: ContentItem,
        results: tuple[ModelResult, ...],
        expected_target: AnalysisTarget,
    ) -> WorkbenchComparison:
        dimension_versions = {result.dimension_version for result in results}
        if len(dimension_versions) != 1:
            raise ValueError("comparison requires one dimension version")

        agreement = _agreement_for(results)
        mandatory_abstention = agreement.status in {
            AgreementStatus.STRONG_DISAGREEMENT,
            AgreementStatus.ABSTAIN,
        }
        abstention_reasons = (
            ("strong-disagreement",)
            if agreement.status is AgreementStatus.STRONG_DISAGREEMENT
            else (("agreement-abstain",) if agreement.status is AgreementStatus.ABSTAIN else ())
        )
        extraction = results[0].confidence.extraction_quality
        if any(result.confidence.extraction_quality != extraction for result in results[1:]):
            raise ValueError("comparison requires identical inherited extraction quality")

        confidence = ConfidenceVector(
            instrument_probability=InstrumentProbability(
                value=None,
                source=None,
                notes="Instrument probabilities are not aggregated at report level.",
            ),
            calibration=Calibration(status=CalibrationStatus.UNKNOWN),
            applicability=_report_applicability(results),
            extraction_quality=ExtractionQuality(
                status=extraction.status,
                issues=extraction.issues,
                evidence_ref=extraction.evidence_ref,
            ),
            inter_instrument_agreement=agreement,
            system_abstention=SystemAbstention(
                triggered=mandatory_abstention,
                reasons=abstention_reasons,
            ),
            ambiguity_budget=AmbiguityBudget(
                status=AmbiguityBudgetStatus.PRESERVED,
                preserved_uncertainties=(
                    "Synthetic fixture behavior is not evidence of real-world validity.",
                ),
                notes="Individual results remain intact when the comparison abstains.",
            ),
        )
        status = (
            WorkbenchReportStatus.ABSTAINED
            if mandatory_abstention
            else WorkbenchReportStatus.COMPLETE
        )
        disagreements = _disagreement_records(results, agreement)
        return WorkbenchComparison(
            comparison_id=f"{run_id}:comparison",
            content_id=content.content_id,
            dimension_id=results[0].dimension_id,
            dimension_version=results[0].dimension_version,
            analysis_target=expected_target,
            result_ids=tuple(result.result_id for result in results),
            analyzer_ids=tuple(result.analyzer.analyzer_id for result in results),
            taxonomy_comparisons=_taxonomy_comparisons(run_id, results),
            confidence=confidence,
            status=status,
            disagreements=disagreements,
            limitations=(
                "Synthetic analyzers validate orchestration contracts only.",
                "No model accuracy, calibration, or production suitability is implied.",
            ),
        )


def _normalized_valence(result: ModelResult) -> float | None:
    for score in result.normalized_scores:
        if score.key == "valence":
            return score.value
    return None


def _agreement_for(results: tuple[ModelResult, ...]) -> InterInstrumentAgreement:
    participants = tuple(result.analyzer.analyzer_id for result in results)
    if any(result.status in {ResultStatus.ABSTAINED, ResultStatus.FAILED} for result in results):
        return InterInstrumentAgreement(
            status=AgreementStatus.ABSTAIN,
            participants=participants,
            notes="At least one analyzer did not produce a comparable measurement.",
        )

    values = tuple(_normalized_valence(result) for result in results)
    if any(value is None for value in values):
        return InterInstrumentAgreement(
            status=AgreementStatus.ABSTAIN,
            participants=participants,
            notes="A required normalized valence value is unavailable.",
        )

    numeric_values = tuple(value for value in values if value is not None)
    if len(set(numeric_values)) == 1:
        status = AgreementStatus.AGREEMENT
        notes = "All synthetic analyzers emitted the same normalized valence."
    elif min(numeric_values) < 0.0 < max(numeric_values):
        status = AgreementStatus.STRONG_DISAGREEMENT
        notes = "Synthetic analyzers emitted opposite valence signs."
    else:
        status = AgreementStatus.PARTIAL_DISAGREEMENT
        notes = "Synthetic analyzers emitted different valence values."
    return InterInstrumentAgreement(
        status=status,
        participants=participants,
        metric="synthetic-signed-valence-v1",
        value=None,
        notes=notes,
    )


def _report_applicability(results: tuple[ModelResult, ...]) -> Applicability:
    states = {result.confidence.applicability.status for result in results}
    if states == {ApplicabilityStatus.IN_DOMAIN}:
        return Applicability(
            status=ApplicabilityStatus.IN_DOMAIN,
            evidence_ref="synthetic-workbench:fixture-domain-v1",
        )
    reasons = tuple(
        sorted(
            {
                reason
                for result in results
                for reason in result.confidence.applicability.reasons
            }
        )
    ) or ("Analyzer applicability states differ or remain unknown.",)
    return Applicability(
        status=ApplicabilityStatus.UNKNOWN,
        reasons=reasons,
        evidence_ref="synthetic-workbench:fixture-domain-v1",
    )


def _taxonomy_comparisons(
    run_id: str,
    results: tuple[ModelResult, ...],
) -> tuple[TaxonomyComparison, ...]:
    records: list[TaxonomyComparison] = []
    for index, (left_result, right_result) in enumerate(combinations(results, 2)):
        left = TaxonomyRef(
            taxonomy_id=left_result.analyzer.taxonomy_id,
            taxonomy_version=left_result.analyzer.taxonomy_version,
        )
        right = TaxonomyRef(
            taxonomy_id=right_result.analyzer.taxonomy_id,
            taxonomy_version=right_result.analyzer.taxonomy_version,
        )
        identical = left == right
        records.append(
            TaxonomyComparison(
                comparison_id=f"{run_id}:taxonomy:{index}",
                comparison_version="0.1.0",
                left=left,
                right=right,
                relation=(
                    TaxonomyRelation.IDENTICAL if identical else TaxonomyRelation.UNASSESSED
                ),
                display_mode=(
                    TaxonomyDisplayMode.MAPPED_COMPARISON
                    if identical
                    else TaxonomyDisplayMode.SIDE_BY_SIDE
                ),
                notes=(
                    "Taxonomy identity matches; analyzer behavior is still compared separately."
                    if identical
                    else "No equivalence or mapping is asserted."
                ),
            )
        )
    return tuple(records)


def _disagreement_records(
    results: tuple[ModelResult, ...],
    agreement: InterInstrumentAgreement,
) -> tuple[DisagreementRecord, ...]:
    if agreement.status not in {
        AgreementStatus.PARTIAL_DISAGREEMENT,
        AgreementStatus.STRONG_DISAGREEMENT,
        AgreementStatus.ABSTAIN,
    }:
        return ()
    return (
        DisagreementRecord(
            result_ids=tuple(result.result_id for result in results),
            description=agreement.notes,
            material=agreement.status in {
                AgreementStatus.STRONG_DISAGREEMENT,
                AgreementStatus.ABSTAIN,
            },
        ),
    )
