"""Human-readable Phase 1B views derived from verified stored evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ctrt.artifact_store import (
    ArtifactIntegrityError,
    FileSystemArtifactStore,
    StoredArtifactRef,
    load_experiment_bundle,
)
from ctrt.canonical_content import CanonicalContentSnapshot
from ctrt.execution_session import ExecutionSessionStatus, VerifiedExecutionReceipt
from ctrt.serialization import (
    CanonicalArtifact,
    canonical_json_text,
    serialize_artifact,
)
from ctrt.stored_content_runner import (
    StoredContentRunnerStatus,
    VerifiedStoredContentExperimentReceipt,
)

PRESENTATION_VERSION = "ctrt-evidence-view@0.1.0"
PRESENTATION_NOTICES = (
    "This is a derived presentation. Canonical stored artifacts remain controlling.",
    "Verified describes lifecycle and evidence integrity, not analytical success.",
    (
        "No overall CTRT score, content verdict, publish recommendation, or "
        "production-readiness claim is produced."
    ),
)


class EvidenceViewError(ValueError):
    """Raised when verified artifacts cannot support an exact evidence view."""


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvidenceViewError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise EvidenceViewError(f"{field_name} keys must be strings")
    return cast(Mapping[str, object], value)


def _array(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise EvidenceViewError(f"{field_name} must be an array")
    return tuple(value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceViewError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    return tuple(_string(item, field_name) for item in _array(value, field_name))


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceViewError(f"{field_name} must be a boolean")
    return value


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceViewError(f"{field_name} must be an integer")
    return value


def _optional_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceViewError(f"{field_name} must be a number")
    return float(value)


def _number(value: object, field_name: str) -> float:
    observed = _optional_number(value, field_name)
    if observed is None:
        raise EvidenceViewError(f"{field_name} must be a number")
    return observed


def _document(artifact: CanonicalArtifact, field_name: str) -> Mapping[str, object]:
    try:
        value = json.loads(artifact.text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceViewError(f"{field_name} is not readable JSON") from exc
    return _mapping(value, field_name)


@dataclass(frozen=True, slots=True)
class EvidenceArtifactReference:
    """One immutable artifact reference supporting the derived view."""

    role: str
    artifact_id: str
    artifact_hash: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.role, self.artifact_id)):
            raise ValueError("evidence artifact identity fields must not be empty")
        if not self.artifact_hash.startswith("sha256:"):
            raise ValueError("evidence artifact hash must use sha256 identity")

    @classmethod
    def from_stored(
        cls,
        *,
        role: str,
        reference: StoredArtifactRef,
    ) -> EvidenceArtifactReference:
        return cls(
            role=role,
            artifact_id=reference.artifact_id,
            artifact_hash=reference.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class EvidenceSpanView:
    """Exact quoted canonical text supporting one instrument output."""

    start: int
    end: int
    excerpt: str
    label: str | None
    score: float | None

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(
                "evidence span coordinates must be positive half-open bounds"
            )
        if not self.excerpt:
            raise ValueError("evidence excerpt must not be empty")


@dataclass(frozen=True, slots=True)
class NormalizedMeasurementView:
    """One instrument-level normalized value with declared bounds."""

    key: str
    value: float
    lower_bound: float
    upper_bound: float

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("normalized measurement key must not be empty")
        if self.lower_bound >= self.upper_bound:
            raise ValueError("normalized measurement bounds must be ordered")
        if not self.lower_bound <= self.value <= self.upper_bound:
            raise ValueError("normalized measurement must remain within its bounds")


@dataclass(frozen=True, slots=True)
class InstrumentEvidenceView:
    """Human-readable projection of one immutable analyzer result."""

    result_id: str
    status: str
    analyzer_id: str
    provider: str
    model_id: str
    model_version: str
    adapter_version: str
    taxonomy_id: str
    taxonomy_version: str
    dimension_id: str
    dimension_version: str
    evidence_support_status: str
    evidence_method_id: str | None
    evidence_method_version: str | None
    normalized_measurements: tuple[NormalizedMeasurementView, ...]
    evidence_spans: tuple[EvidenceSpanView, ...]
    instrument_probability: float | None
    probability_source: str | None
    calibration_status: str
    applicability_status: str
    applicability_reasons: tuple[str, ...]
    extraction_quality_status: str
    extraction_quality_issues: tuple[str, ...]
    abstention_triggered: bool
    abstention_reasons: tuple[str, ...]
    ambiguity_status: str
    preserved_uncertainties: tuple[str, ...]
    raw_output_json: str
    configuration_json: str
    confidence_json: str
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    artifact_ref: EvidenceArtifactReference


@dataclass(frozen=True, slots=True)
class DisagreementView:
    """One preserved comparison disagreement."""

    result_ids: tuple[str, ...]
    description: str
    material: bool


@dataclass(frozen=True, slots=True)
class ComparisonEvidenceView:
    """Presentation of the separate comparison artifact."""

    comparison_id: str
    status: str
    dimension_id: str
    dimension_version: str
    result_ids: tuple[str, ...]
    analyzer_ids: tuple[str, ...]
    agreement_status: str
    agreement_notes: str
    abstention_triggered: bool
    abstention_reasons: tuple[str, ...]
    disagreements: tuple[DisagreementView, ...]
    limitations: tuple[str, ...]
    score_combination_permitted: bool
    confidence_json: str
    artifact_ref: EvidenceArtifactReference

    def __post_init__(self) -> None:
        if self.score_combination_permitted:
            raise ValueError("Phase 1B evidence views may not permit score combination")


@dataclass(frozen=True, slots=True)
class ContentEvidenceView:
    """Exact content, instrument evidence, and comparison for one session."""

    position: int
    content_id: str
    text: str
    content_hash: str
    language: str
    source_type: str
    source_uri: str | None
    extraction_ref: str
    run_id: str
    session_id: str
    lifecycle_status: str
    measurements: tuple[InstrumentEvidenceView, ...]
    comparison: ComparisonEvidenceView
    artifact_refs: tuple[EvidenceArtifactReference, ...]

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("content evidence position must be non-negative")
        if not self.text.strip():
            raise ValueError("content evidence text must not be empty")
        if self.lifecycle_status != "verified":
            raise ValueError("content evidence requires a verified session")
        if len(self.measurements) < 2:
            raise ValueError("content evidence requires multiple measurements")


@dataclass(frozen=True, slots=True)
class StoredContentEvidenceView:
    """Noncanonical human view derived from verified stored-content evidence."""

    presentation_version: str
    experiment_run_id: str
    lifecycle_status: str
    experiment_id: str
    experiment_version: str
    contents: tuple[ContentEvidenceView, ...]
    completion_refs: tuple[EvidenceArtifactReference, ...]
    notices: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.presentation_version != PRESENTATION_VERSION:
            raise ValueError("unsupported evidence presentation version")
        if self.lifecycle_status != "verified":
            raise ValueError("stored-content evidence view requires verified lifecycle")
        if len(self.contents) < 2:
            raise ValueError(
                "stored-content evidence view requires multiple content items"
            )
        positions = tuple(item.position for item in self.contents)
        if positions != tuple(range(len(self.contents))):
            raise ValueError(
                "content evidence positions must be contiguous and ordered"
            )
        if self.notices != PRESENTATION_NOTICES:
            raise ValueError("evidence view must preserve interpretation notices")


def _confidence_parts(
    value: object,
    field_name: str,
) -> tuple[
    float | None,
    str | None,
    str,
    str,
    tuple[str, ...],
    str,
    tuple[str, ...],
    bool,
    tuple[str, ...],
    str,
    tuple[str, ...],
    str,
]:
    document = _mapping(value, field_name)
    probability = _mapping(
        document.get("instrument_probability"),
        f"{field_name}.instrument_probability",
    )
    calibration = _mapping(
        document.get("calibration"),
        f"{field_name}.calibration",
    )
    applicability = _mapping(
        document.get("applicability"),
        f"{field_name}.applicability",
    )
    extraction = _mapping(
        document.get("extraction_quality"),
        f"{field_name}.extraction_quality",
    )
    abstention = _mapping(
        document.get("system_abstention"),
        f"{field_name}.system_abstention",
    )
    ambiguity = _mapping(
        document.get("ambiguity_budget"),
        f"{field_name}.ambiguity_budget",
    )
    return (
        _optional_number(
            probability.get("value"),
            f"{field_name}.instrument_probability.value",
        ),
        _optional_string(
            probability.get("source"),
            f"{field_name}.instrument_probability.source",
        ),
        _string(calibration.get("status"), f"{field_name}.calibration.status"),
        _string(
            applicability.get("status"),
            f"{field_name}.applicability.status",
        ),
        _strings(
            applicability.get("reasons"),
            f"{field_name}.applicability.reasons",
        ),
        _string(
            extraction.get("status"),
            f"{field_name}.extraction_quality.status",
        ),
        _strings(
            extraction.get("issues"),
            f"{field_name}.extraction_quality.issues",
        ),
        _boolean(
            abstention.get("triggered"),
            f"{field_name}.system_abstention.triggered",
        ),
        _strings(
            abstention.get("reasons"),
            f"{field_name}.system_abstention.reasons",
        ),
        _string(
            ambiguity.get("status"),
            f"{field_name}.ambiguity_budget.status",
        ),
        _strings(
            ambiguity.get("preserved_uncertainties"),
            f"{field_name}.ambiguity_budget.preserved_uncertainties",
        ),
        canonical_json_text(document),
    )


def _instrument_view(
    *,
    document: Mapping[str, object],
    reference: StoredArtifactRef,
    content: CanonicalContentSnapshot,
) -> InstrumentEvidenceView:
    if _string(document.get("content_id"), "result.content_id") != content.content_id:
        raise EvidenceViewError(
            "result content identity differs from canonical content"
        )
    analyzer = _mapping(document.get("analyzer"), "result.analyzer")
    target = _mapping(document.get("analysis_target"), "result.analysis_target")
    target_id = _string(
        target.get("content_id"),
        "result.analysis_target.content_id",
    )
    start = _integer(target.get("start"), "result.analysis_target.start")
    end = _integer(target.get("end"), "result.analysis_target.end")
    extraction_ref = _string(
        target.get("extraction_ref"),
        "result.analysis_target.extraction_ref",
    )
    if target_id != content.content_id:
        raise EvidenceViewError("result analysis target identifies different content")
    if start != 0 or end != len(content.text):
        raise EvidenceViewError(
            "result analysis target does not cover exact canonical text"
        )
    if extraction_ref != content.extraction_ref:
        raise EvidenceViewError(
            "result extraction identity differs from canonical content"
        )

    support = _mapping(document.get("evidence_support"), "result.evidence_support")
    normalized = tuple(
        NormalizedMeasurementView(
            key=_string(item.get("key"), "result.normalized_scores.key"),
            value=_number(item.get("value"), "result.normalized_scores.value"),
            lower_bound=_number(
                item.get("lower_bound"),
                "result.normalized_scores.lower_bound",
            ),
            upper_bound=_number(
                item.get("upper_bound"),
                "result.normalized_scores.upper_bound",
            ),
        )
        for item in (
            _mapping(value, "result.normalized_scores item")
            for value in _array(
                document.get("normalized_scores"),
                "result.normalized_scores",
            )
        )
    )
    spans: list[EvidenceSpanView] = []
    for value in _array(document.get("evidence_spans"), "result.evidence_spans"):
        item = _mapping(value, "result.evidence_spans item")
        span_start = _integer(item.get("start"), "result.evidence_spans.start")
        span_end = _integer(item.get("end"), "result.evidence_spans.end")
        if span_start < start or span_end > end:
            raise EvidenceViewError(
                "evidence span falls outside the exact analysis target"
            )
        spans.append(
            EvidenceSpanView(
                start=span_start,
                end=span_end,
                excerpt=content.text[span_start:span_end],
                label=_optional_string(
                    item.get("label"),
                    "result.evidence_spans.label",
                ),
                score=_optional_number(
                    item.get("score"),
                    "result.evidence_spans.score",
                ),
            )
        )
    (
        probability,
        probability_source,
        calibration,
        applicability,
        applicability_reasons,
        extraction,
        extraction_issues,
        abstention,
        abstention_reasons,
        ambiguity,
        uncertainties,
        confidence_json,
    ) = _confidence_parts(document.get("confidence"), "result.confidence")
    return InstrumentEvidenceView(
        result_id=_string(document.get("result_id"), "result.result_id"),
        status=_string(document.get("status"), "result.status"),
        analyzer_id=_string(
            analyzer.get("analyzer_id"),
            "result.analyzer.analyzer_id",
        ),
        provider=_string(analyzer.get("provider"), "result.analyzer.provider"),
        model_id=_string(analyzer.get("model_id"), "result.analyzer.model_id"),
        model_version=_string(
            analyzer.get("model_version"),
            "result.analyzer.model_version",
        ),
        adapter_version=_string(
            analyzer.get("adapter_version"),
            "result.analyzer.adapter_version",
        ),
        taxonomy_id=_string(
            analyzer.get("taxonomy_id"),
            "result.analyzer.taxonomy_id",
        ),
        taxonomy_version=_string(
            analyzer.get("taxonomy_version"),
            "result.analyzer.taxonomy_version",
        ),
        dimension_id=_string(document.get("dimension_id"), "result.dimension_id"),
        dimension_version=_string(
            document.get("dimension_version"),
            "result.dimension_version",
        ),
        evidence_support_status=_string(
            support.get("status"),
            "result.evidence_support.status",
        ),
        evidence_method_id=_optional_string(
            support.get("method_id"),
            "result.evidence_support.method_id",
        ),
        evidence_method_version=_optional_string(
            support.get("method_version"),
            "result.evidence_support.method_version",
        ),
        normalized_measurements=normalized,
        evidence_spans=tuple(spans),
        instrument_probability=probability,
        probability_source=probability_source,
        calibration_status=calibration,
        applicability_status=applicability,
        applicability_reasons=applicability_reasons,
        extraction_quality_status=extraction,
        extraction_quality_issues=extraction_issues,
        abstention_triggered=abstention,
        abstention_reasons=abstention_reasons,
        ambiguity_status=ambiguity,
        preserved_uncertainties=uncertainties,
        raw_output_json=canonical_json_text(
            _mapping(document.get("raw_output"), "result.raw_output")
        ),
        configuration_json=canonical_json_text(
            _mapping(document.get("configuration"), "result.configuration")
        ),
        confidence_json=confidence_json,
        warnings=_strings(document.get("warnings"), "result.warnings"),
        errors=_strings(document.get("errors"), "result.errors"),
        artifact_ref=EvidenceArtifactReference.from_stored(
            role="result",
            reference=reference,
        ),
    )


def _comparison_view(
    *,
    document: Mapping[str, object],
    reference: StoredArtifactRef,
    content: CanonicalContentSnapshot,
    measurements: tuple[InstrumentEvidenceView, ...],
) -> ComparisonEvidenceView:
    content_id = _string(document.get("content_id"), "comparison.content_id")
    if content_id != content.content_id:
        raise EvidenceViewError(
            "comparison content identity differs from canonical content"
        )
    result_ids = _strings(document.get("result_ids"), "comparison.result_ids")
    analyzer_ids = _strings(document.get("analyzer_ids"), "comparison.analyzer_ids")
    if result_ids != tuple(item.result_id for item in measurements):
        raise EvidenceViewError(
            "comparison result order differs from preserved measurements"
        )
    if analyzer_ids != tuple(item.analyzer_id for item in measurements):
        raise EvidenceViewError(
            "comparison analyzer order differs from preserved measurements"
        )
    confidence = _mapping(document.get("confidence"), "comparison.confidence")
    agreement = _mapping(
        confidence.get("inter_instrument_agreement"),
        "comparison.confidence.inter_instrument_agreement",
    )
    abstention = _mapping(
        confidence.get("system_abstention"),
        "comparison.confidence.system_abstention",
    )
    permitted = _boolean(
        document.get("score_combination_permitted"),
        "comparison.score_combination_permitted",
    )
    if permitted:
        raise EvidenceViewError("comparison unexpectedly permits score combination")
    disagreements = tuple(
        DisagreementView(
            result_ids=_strings(
                item.get("result_ids"),
                "comparison.disagreements.result_ids",
            ),
            description=_string(
                item.get("description"),
                "comparison.disagreements.description",
            ),
            material=_boolean(
                item.get("material"),
                "comparison.disagreements.material",
            ),
        )
        for item in (
            _mapping(value, "comparison.disagreements item")
            for value in _array(
                document.get("disagreements"),
                "comparison.disagreements",
            )
        )
    )
    return ComparisonEvidenceView(
        comparison_id=_string(
            document.get("comparison_id"),
            "comparison.comparison_id",
        ),
        status=_string(document.get("status"), "comparison.status"),
        dimension_id=_string(
            document.get("dimension_id"),
            "comparison.dimension_id",
        ),
        dimension_version=_string(
            document.get("dimension_version"),
            "comparison.dimension_version",
        ),
        result_ids=result_ids,
        analyzer_ids=analyzer_ids,
        agreement_status=_string(
            agreement.get("status"),
            "comparison.agreement.status",
        ),
        agreement_notes=str(agreement.get("notes", "")),
        abstention_triggered=_boolean(
            abstention.get("triggered"),
            "comparison.abstention.triggered",
        ),
        abstention_reasons=_strings(
            abstention.get("reasons"),
            "comparison.abstention.reasons",
        ),
        disagreements=disagreements,
        limitations=_strings(
            document.get("limitations"),
            "comparison.limitations",
        ),
        score_combination_permitted=permitted,
        confidence_json=canonical_json_text(confidence),
        artifact_ref=EvidenceArtifactReference.from_stored(
            role="comparison",
            reference=reference,
        ),
    )


def _verify_stored_receipt(
    *,
    store: FileSystemArtifactStore,
    receipt: VerifiedExecutionReceipt,
    reference: StoredArtifactRef,
) -> None:
    expected = serialize_artifact(reference.artifact_id, receipt)
    observed = store.get(
        reference.artifact_id,
        expected_hash=reference.artifact_hash,
    )
    if observed.payload != expected.payload:
        raise ArtifactIntegrityError(
            "stored session receipt differs from the supplied verified receipt"
        )


def _content_view(
    *,
    position: int,
    content: CanonicalContentSnapshot,
    receipt: VerifiedExecutionReceipt,
    receipt_ref: StoredArtifactRef,
    store: FileSystemArtifactStore,
) -> ContentEvidenceView:
    if receipt.status is not ExecutionSessionStatus.VERIFIED:
        raise EvidenceViewError("evidence view requires a verified execution receipt")
    if receipt.content_id != content.content_id:
        raise EvidenceViewError("session receipt content differs from stored content")
    _verify_stored_receipt(store=store, receipt=receipt, reference=receipt_ref)
    bundle = load_experiment_bundle(store, receipt.manifest_ref)
    if bundle.manifest.run_record_id != receipt.run_record_id:
        raise EvidenceViewError("bundle run record differs from session receipt")

    artifacts = bundle.manifest.artifacts
    result_items = tuple(item for item in artifacts if item.role.startswith("result:"))
    result_roles = tuple(item.role for item in result_items)
    expected_roles = tuple(f"result:{index}" for index in range(len(result_items)))
    if result_roles != expected_roles:
        raise EvidenceViewError("bundle result roles must be contiguous and ordered")
    if len(result_items) != len(receipt.analyzer_ids):
        raise EvidenceViewError("bundle result population differs from session receipt")

    measurements = tuple(
        _instrument_view(
            document=_document(
                store.get(
                    item.artifact.artifact_id,
                    expected_hash=item.artifact.artifact_hash,
                ),
                item.role,
            ),
            reference=item.artifact,
            content=content,
        )
        for item in result_items
    )
    if tuple(item.analyzer_id for item in measurements) != receipt.analyzer_ids:
        raise EvidenceViewError("result analyzer order differs from session receipt")
    expected_statuses = tuple(status.value for status in receipt.result_statuses)
    if tuple(item.status for item in measurements) != expected_statuses:
        raise EvidenceViewError("result statuses differ from session receipt")

    comparison_items = tuple(item for item in artifacts if item.role == "comparison")
    if len(comparison_items) != 1:
        raise EvidenceViewError("bundle must contain exactly one comparison artifact")
    comparison_item = comparison_items[0]
    comparison = _comparison_view(
        document=_document(
            store.get(
                comparison_item.artifact.artifact_id,
                expected_hash=comparison_item.artifact.artifact_hash,
            ),
            "comparison",
        ),
        reference=comparison_item.artifact,
        content=content,
        measurements=measurements,
    )
    if comparison.status != receipt.workbench_status.value:
        raise EvidenceViewError("comparison status differs from session receipt")

    references = (
        EvidenceArtifactReference.from_stored(
            role="canonical-content",
            reference=content.reference(),
        ),
        EvidenceArtifactReference.from_stored(
            role="session-receipt",
            reference=receipt_ref,
        ),
        EvidenceArtifactReference.from_stored(
            role="bundle-manifest",
            reference=receipt.manifest_ref,
        ),
        *tuple(
            EvidenceArtifactReference.from_stored(
                role=item.role,
                reference=item.artifact,
            )
            for item in artifacts
        ),
    )
    return ContentEvidenceView(
        position=position,
        content_id=content.content_id,
        text=content.text,
        content_hash=content.content_hash,
        language=content.language,
        source_type=content.source_type.value,
        source_uri=content.source_uri,
        extraction_ref=content.extraction_ref,
        run_id=receipt.run_id,
        session_id=receipt.session_id,
        lifecycle_status=receipt.status.value,
        measurements=measurements,
        comparison=comparison,
        artifact_refs=references,
    )


def build_stored_content_evidence_view(
    *,
    receipt: VerifiedStoredContentExperimentReceipt,
    artifact_store: FileSystemArtifactStore,
) -> StoredContentEvidenceView:
    """Re-read exact stored evidence and derive a noncanonical presentation view."""

    if receipt.status is not StoredContentRunnerStatus.VERIFIED:
        raise EvidenceViewError(
            "evidence reader requires a verified stored-content receipt"
        )
    experiment = receipt.corpus_bound_receipt.experiment_receipt
    if experiment.content_ids != receipt.content_ids:
        raise EvidenceViewError("experiment content order differs from stored receipt")
    if len(receipt.content_artifact_refs) != len(experiment.session_receipts):
        raise EvidenceViewError("stored content and session populations differ")

    completion_refs = (
        EvidenceArtifactReference.from_stored(
            role="stored-content-completion",
            reference=receipt.completion_manifest_ref,
        ),
        EvidenceArtifactReference.from_stored(
            role="corpus-bound-completion",
            reference=receipt.corpus_bound_receipt.completion_manifest_ref,
        ),
        EvidenceArtifactReference.from_stored(
            role="experiment-completion",
            reference=experiment.completion_manifest_ref,
        ),
    )
    for item in completion_refs:
        artifact_store.get(item.artifact_id, expected_hash=item.artifact_hash)

    content_views: list[ContentEvidenceView] = []
    zipped = zip(
        receipt.content_ids,
        receipt.content_artifact_refs,
        experiment.session_receipts,
        experiment.session_receipt_refs,
        strict=True,
    )
    for position, (
        content_id,
        content_ref,
        session_receipt,
        session_receipt_ref,
    ) in enumerate(zipped):
        artifact = artifact_store.get(
            content_ref.artifact_id,
            expected_hash=content_ref.artifact_hash,
        )
        content = CanonicalContentSnapshot.from_artifact(artifact)
        if content.reference() != content_ref:
            raise EvidenceViewError(
                "stored content reference differs after reconstruction"
            )
        if content.content_id != content_id:
            raise EvidenceViewError(
                "stored content order differs from verified receipt"
            )
        content_views.append(
            _content_view(
                position=position,
                content=content,
                receipt=session_receipt,
                receipt_ref=session_receipt_ref,
                store=artifact_store,
            )
        )

    return StoredContentEvidenceView(
        presentation_version=PRESENTATION_VERSION,
        experiment_run_id=receipt.experiment_run_id,
        lifecycle_status=receipt.status.value,
        experiment_id=receipt.experiment_id,
        experiment_version=receipt.experiment_version,
        contents=tuple(content_views),
        completion_refs=completion_refs,
        notices=PRESENTATION_NOTICES,
    )


def _markdown_quote(value: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in value.splitlines() or [""]]


def _markdown_json(value: str) -> list[str]:
    return [f"    {line}" for line in value.splitlines()]


def _display_optional(value: object) -> str:
    return "not available" if value is None else str(value)


def render_evidence_view_markdown(view: StoredContentEvidenceView) -> str:
    """Render a deterministic human-readable view without analytical aggregation."""

    lines = [
        "# CTRT Evidence View",
        "",
        f"Presentation contract: `{view.presentation_version}`",
        "",
        "## Experiment",
        "",
        f"- Run: `{view.experiment_run_id}`",
        f"- Experiment: `{view.experiment_id}@{view.experiment_version}`",
        f"- Lifecycle: **{view.lifecycle_status}**",
        f"- Ordered content items: {len(view.contents)}",
        "",
    ]
    for content in view.contents:
        lines.extend(
            [
                f"## {content.position + 1}. `{content.content_id}`",
                "",
                "### Exact stored content",
                "",
                *_markdown_quote(content.text),
                "",
                "### Provenance",
                "",
                f"- Content hash: `{content.content_hash}`",
                f"- Language: `{content.language}`",
                f"- Source type: `{content.source_type}`",
                f"- Source URI: {_display_optional(content.source_uri)}",
                f"- Extraction identity: `{content.extraction_ref}`",
                f"- Session: `{content.session_id}`",
                f"- Session lifecycle: **{content.lifecycle_status}**",
                "",
                "### Instrument measurements",
                "",
            ]
        )
        for measurement in content.measurements:
            lines.extend(
                [
                    f"#### `{measurement.analyzer_id}`",
                    "",
                    f"- Result status: **{measurement.status}**",
                    (
                        f"- Dimension: `{measurement.dimension_id}@"
                        f"{measurement.dimension_version}`"
                    ),
                    f"- Provider: `{measurement.provider}`",
                    (
                        f"- Instrument: `{measurement.model_id}@"
                        f"{measurement.model_version}`"
                    ),
                    f"- Adapter: `{measurement.adapter_version}`",
                    (
                        f"- Taxonomy: `{measurement.taxonomy_id}@"
                        f"{measurement.taxonomy_version}`"
                    ),
                    f"- Evidence support: `{measurement.evidence_support_status}`",
                    "",
                    "Normalized measurements:",
                ]
            )
            if measurement.normalized_measurements:
                lines.extend(
                    f"- `{item.key}` = **{item.value:g}** "
                    f"within [{item.lower_bound:g}, {item.upper_bound:g}]"
                    for item in measurement.normalized_measurements
                )
            else:
                lines.append("- No normalized measurement emitted.")
            lines.extend(["", "Evidence spans:"])
            if measurement.evidence_spans:
                for span in measurement.evidence_spans:
                    label = (
                        f", label `{span.label}`" if span.label is not None else ""
                    )
                    lines.append(
                        f"- [{span.start}:{span.end}] **{span.excerpt!r}**{label}"
                    )
            else:
                lines.append("- No local evidence span was available.")
            lines.extend(
                [
                    "",
                    "Dimensional confidence evidence:",
                    (
                        "- Instrument probability: "
                        f"{_display_optional(measurement.instrument_probability)}"
                    ),
                    f"- Calibration: {measurement.calibration_status}",
                    f"- Applicability: {measurement.applicability_status}",
                    "- Applicability reasons: "
                    + (", ".join(measurement.applicability_reasons) or "none"),
                    f"- Extraction quality: {measurement.extraction_quality_status}",
                    "- Extraction issues: "
                    + (", ".join(measurement.extraction_quality_issues) or "none"),
                    (
                        "- System abstention: "
                        + ("yes" if measurement.abstention_triggered else "no")
                    ),
                    "- Abstention reasons: "
                    + (", ".join(measurement.abstention_reasons) or "none"),
                    f"- Ambiguity handling: {measurement.ambiguity_status}",
                    "- Preserved uncertainty: "
                    + (
                        "; ".join(measurement.preserved_uncertainties)
                        or "none declared"
                    ),
                    "",
                    "Raw output:",
                    "",
                    *_markdown_json(measurement.raw_output_json),
                    "",
                    "Declared execution configuration:",
                    "",
                    *_markdown_json(measurement.configuration_json),
                ]
            )
            if measurement.warnings:
                lines.extend(["", "Warnings:"])
                lines.extend(f"- {item}" for item in measurement.warnings)
            if measurement.errors:
                lines.extend(["", "Errors:"])
                lines.extend(f"- {item}" for item in measurement.errors)
            lines.append("")

        comparison = content.comparison
        lines.extend(
            [
                "### Comparison",
                "",
                f"- Status: **{comparison.status}**",
                f"- Agreement: `{comparison.agreement_status}`",
                "- Score combination: **not permitted**",
                (
                    "- System abstention: "
                    + ("yes" if comparison.abstention_triggered else "no")
                ),
                "- Abstention reasons: "
                + (", ".join(comparison.abstention_reasons) or "none"),
            ]
        )
        if comparison.disagreements:
            lines.extend(["", "Preserved disagreements:"])
            lines.extend(
                f"- {item.description} "
                f"({'material' if item.material else 'not material'})"
                for item in comparison.disagreements
            )
        if comparison.limitations:
            lines.extend(["", "Limitations:"])
            lines.extend(f"- {item}" for item in comparison.limitations)
        lines.extend(["", "### Immutable evidence references", ""])
        lines.extend(
            f"- `{item.role}` → `{item.artifact_id}` (`{item.artifact_hash}`)"
            for item in content.artifact_refs
        )
        lines.append("")

    lines.extend(["## Interpretation boundary", ""])
    lines.extend(f"- {item}" for item in view.notices)
    lines.extend(["", "## Completion references", ""])
    lines.extend(
        f"- `{item.role}` → `{item.artifact_id}` (`{item.artifact_hash}`)"
        for item in view.completion_refs
    )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ComparisonEvidenceView",
    "ContentEvidenceView",
    "DisagreementView",
    "EvidenceArtifactReference",
    "EvidenceSpanView",
    "EvidenceViewError",
    "InstrumentEvidenceView",
    "NormalizedMeasurementView",
    "PRESENTATION_NOTICES",
    "PRESENTATION_VERSION",
    "StoredContentEvidenceView",
    "build_stored_content_evidence_view",
    "render_evidence_view_markdown",
]
