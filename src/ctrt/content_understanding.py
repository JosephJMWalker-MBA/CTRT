"""Content-directed reflection derived from exact verified CTRT evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.evidence_view import (
    ComparisonEvidenceView,
    ContentEvidenceView,
    EvidenceArtifactReference,
    InstrumentEvidenceView,
    build_stored_content_evidence_view,
)
from ctrt.stored_content_runner import VerifiedStoredContentExperimentReceipt

CONTENT_UNDERSTANDING_VERSION = "ctrt-content-understanding@0.1.0"
CONTENT_UNDERSTANDING_NOTICES = (
    (
        "This is a derived content-inspection aid. Canonical stored artifacts remain "
        "controlling."
    ),
    (
        "Reader-provided purpose, context, and questions are not verified evidence and "
        "do not amend the canonical graph."
    ),
    (
        "Verified describes lifecycle and evidence integrity, not complete meaning, "
        "analytical success, or correctness."
    ),
    (
        "No overall CTRT score, safety label, restriction recommendation, viewer profile, "
        "ambient monitoring, or production-readiness claim is produced."
    ),
    (
        "CTRT supports inspection and discussion; it does not replace direct source review "
        "or human judgment."
    ),
)
CONTENT_INSPECTION_PATHS = (
    "Read the content in its original surrounding context.",
    "Check the source, date, authorship, and material that may be omitted.",
    "Discuss the content with the person who encountered or shared it.",
    "Pause judgment and seek knowledgeable context when evidence is incomplete.",
)


class ContentUnderstandingError(ValueError):
    """Raised when verified evidence cannot support content understanding."""


class UnderstandingObservationKind(StrEnum):
    """Plain-language evidence category without analytical aggregation."""

    LIFECYCLE = "lifecycle"
    INSTRUMENT = "instrument"
    COMPARISON = "comparison"
    UNCERTAINTY = "uncertainty"
    LIMITATION = "limitation"


class UnderstandingPromptKind(StrEnum):
    """Reason an inspection question appears in the content view."""

    PURPOSE = "purpose"
    SOURCE = "source"
    CONTEXT = "context"
    READER_QUESTION = "reader-question"
    EVIDENCE = "evidence"
    DISCUSSION = "discussion"
    DISAGREEMENT = "disagreement"
    AGREEMENT = "agreement"
    ABSTENTION = "abstention"
    CALIBRATION = "calibration"
    APPLICABILITY = "applicability"
    EXTRACTION = "extraction"
    UNCERTAINTY = "uncertainty"
    LIMITATION = "limitation"


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _unique_refs(
    values: tuple[EvidenceArtifactReference, ...],
) -> tuple[EvidenceArtifactReference, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[EvidenceArtifactReference] = []
    for value in values:
        key = (value.role, value.artifact_id, value.artifact_hash)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ReaderProvidedContext:
    """Reader context explicitly kept outside verified evidence."""

    purpose: str
    known_context: str | None = None
    questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.purpose, "reader purpose")
        if self.known_context is not None:
            _require_text(self.known_context, "known context")
        if any(not item.strip() for item in self.questions):
            raise ValueError("reader questions must not contain empty values")
        if any(not item.endswith("?") for item in self.questions):
            raise ValueError("reader questions must end with a question mark")
        if len(self.questions) != len(set(self.questions)):
            raise ValueError("reader questions must not contain duplicates")


@dataclass(frozen=True, slots=True)
class ContentUnderstandingRequest:
    """Select one exact verified content item for content-directed reflection."""

    content_id: str
    context: ReaderProvidedContext

    def __post_init__(self) -> None:
        _require_text(self.content_id, "content_id")


@dataclass(frozen=True, slots=True)
class UnderstandingObservation:
    """One plain-language statement traceable to immutable evidence."""

    observation_id: str
    kind: UnderstandingObservationKind
    text: str
    evidence_refs: tuple[EvidenceArtifactReference, ...]

    def __post_init__(self) -> None:
        _require_text(self.observation_id, "observation_id")
        _require_text(self.text, "observation text")
        if not self.evidence_refs:
            raise ValueError("understanding observation requires evidence references")
        if self.evidence_refs != _unique_refs(self.evidence_refs):
            raise ValueError("understanding observation references must be unique")


@dataclass(frozen=True, slots=True)
class UnderstandingPrompt:
    """One deterministic question that preserves reader responsibility."""

    prompt_id: str
    kind: UnderstandingPromptKind
    question: str
    evidence_refs: tuple[EvidenceArtifactReference, ...]

    def __post_init__(self) -> None:
        _require_text(self.prompt_id, "prompt_id")
        _require_text(self.question, "understanding question")
        if not self.question.endswith("?"):
            raise ValueError("understanding question must end with a question mark")
        if not self.evidence_refs:
            raise ValueError("understanding prompt requires evidence references")
        if self.evidence_refs != _unique_refs(self.evidence_refs):
            raise ValueError("understanding prompt references must be unique")


@dataclass(frozen=True, slots=True)
class ContentUnderstandingView:
    """Noncanonical content-directed reflection over verified evidence."""

    understanding_version: str
    experiment_run_id: str
    lifecycle_status: str
    content_id: str
    reader_context: ReaderProvidedContext
    evidence: ContentEvidenceView
    observations: tuple[UnderstandingObservation, ...]
    reflection_prompts: tuple[UnderstandingPrompt, ...]
    completion_refs: tuple[EvidenceArtifactReference, ...]
    inspection_paths: tuple[str, ...]
    notices: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.understanding_version != CONTENT_UNDERSTANDING_VERSION:
            raise ValueError("unsupported content understanding version")
        if self.lifecycle_status != "verified":
            raise ValueError("content understanding requires verified evidence")
        if self.content_id != self.evidence.content_id:
            raise ValueError("content understanding must match exact evidence")
        if not self.observations:
            raise ValueError("content understanding requires observations")
        if not self.reflection_prompts:
            raise ValueError("content understanding requires reflection prompts")
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("understanding observation IDs must be unique")
        prompt_ids = tuple(item.prompt_id for item in self.reflection_prompts)
        if len(prompt_ids) != len(set(prompt_ids)):
            raise ValueError("understanding prompt IDs must be unique")
        if self.inspection_paths != CONTENT_INSPECTION_PATHS:
            raise ValueError("content understanding must preserve inspection paths")
        if self.notices != CONTENT_UNDERSTANDING_NOTICES:
            raise ValueError("content understanding must preserve notices")


def _role_ref(
    content: ContentEvidenceView,
    role: str,
) -> EvidenceArtifactReference:
    values = tuple(item for item in content.artifact_refs if item.role == role)
    if len(values) != 1:
        raise ContentUnderstandingError(
            f"content evidence must contain exactly one {role!r} reference"
        )
    return values[0]


def _instrument_text(measurement: InstrumentEvidenceView) -> str:
    if measurement.status == "abstained":
        reasons = ", ".join(measurement.abstention_reasons) or "no reason recorded"
        return (
            f"{measurement.analyzer_id} did not emit a measurement. "
            f"Preserved abstention reasons: {reasons}."
        )
    if measurement.status == "failed":
        errors = "; ".join(measurement.errors) or "no error detail recorded"
        return f"{measurement.analyzer_id} failed. Preserved errors: {errors}."

    values = ", ".join(
        f"{item.key} {item.value:g} within [{item.lower_bound:g}, {item.upper_bound:g}]"
        for item in measurement.normalized_measurements
    )
    excerpts = ", ".join(
        f"{item.excerpt!r} [{item.start}:{item.end}]"
        for item in measurement.evidence_spans
    )
    return (
        f"{measurement.analyzer_id} returned status {measurement.status} and recorded "
        f"{values or 'no normalized measurement'}. Exact supporting evidence: "
        f"{excerpts or 'no local evidence excerpt'}."
    )


def _comparison_text(comparison: ComparisonEvidenceView) -> str:
    abstention = (
        f" The comparison abstained for: {', '.join(comparison.abstention_reasons)}."
        if comparison.abstention_triggered
        else ""
    )
    return (
        f"The separate comparison recorded {comparison.agreement_status} with status "
        f"{comparison.status}.{abstention} Original instrument results remain separate, "
        "and score combination was not permitted."
    )


def _uncertainty_text(measurement: InstrumentEvidenceView) -> str | None:
    parts: list[str] = []
    if measurement.calibration_status != "validated":
        parts.append(f"calibration is {measurement.calibration_status}")
    if measurement.applicability_status != "in-domain":
        reasons = "; ".join(measurement.applicability_reasons)
        detail = f" ({reasons})" if reasons else ""
        parts.append(f"applicability is {measurement.applicability_status}{detail}")
    if measurement.extraction_quality_status != "clean":
        issues = "; ".join(measurement.extraction_quality_issues)
        detail = f" ({issues})" if issues else ""
        parts.append(
            f"extraction quality is {measurement.extraction_quality_status}{detail}"
        )
    if measurement.preserved_uncertainties:
        parts.append(
            "preserved uncertainty: " + "; ".join(measurement.preserved_uncertainties)
        )
    if not parts:
        return None
    return f"For {measurement.analyzer_id}, " + "; ".join(parts) + "."


def _observations(
    *,
    content: ContentEvidenceView,
    completion_refs: tuple[EvidenceArtifactReference, ...],
) -> tuple[UnderstandingObservation, ...]:
    values: list[UnderstandingObservation] = [
        UnderstandingObservation(
            observation_id="lifecycle-verified",
            kind=UnderstandingObservationKind.LIFECYCLE,
            text=(
                "The stored evidence lifecycle verified for this content. This confirms "
                "artifact identity and completion, not complete meaning or correctness."
            ),
            evidence_refs=_unique_refs(
                (*completion_refs, _role_ref(content, "session-receipt"))
            ),
        )
    ]
    for index, measurement in enumerate(content.measurements):
        values.append(
            UnderstandingObservation(
                observation_id=f"instrument-{index}",
                kind=UnderstandingObservationKind.INSTRUMENT,
                text=_instrument_text(measurement),
                evidence_refs=(measurement.artifact_ref,),
            )
        )
        uncertainty = _uncertainty_text(measurement)
        if uncertainty is not None:
            values.append(
                UnderstandingObservation(
                    observation_id=f"uncertainty-{index}",
                    kind=UnderstandingObservationKind.UNCERTAINTY,
                    text=uncertainty,
                    evidence_refs=(measurement.artifact_ref,),
                )
            )
    values.append(
        UnderstandingObservation(
            observation_id="comparison",
            kind=UnderstandingObservationKind.COMPARISON,
            text=_comparison_text(content.comparison),
            evidence_refs=_unique_refs(
                (
                    content.comparison.artifact_ref,
                    *(item.artifact_ref for item in content.measurements),
                )
            ),
        )
    )
    if content.comparison.limitations:
        values.append(
            UnderstandingObservation(
                observation_id="comparison-limitations",
                kind=UnderstandingObservationKind.LIMITATION,
                text=(
                    "The comparison preserved these limitations: "
                    + "; ".join(content.comparison.limitations)
                    + "."
                ),
                evidence_refs=(content.comparison.artifact_ref,),
            )
        )
    return tuple(values)


def _prompt(
    *,
    prompt_id: str,
    kind: UnderstandingPromptKind,
    question: str,
    refs: tuple[EvidenceArtifactReference, ...],
) -> UnderstandingPrompt:
    return UnderstandingPrompt(
        prompt_id=prompt_id,
        kind=kind,
        question=question,
        evidence_refs=_unique_refs(refs),
    )


def _reflection_prompts(
    *,
    context: ReaderProvidedContext,
    content: ContentEvidenceView,
) -> tuple[UnderstandingPrompt, ...]:
    content_ref = _role_ref(content, "canonical-content")
    result_refs = tuple(item.artifact_ref for item in content.measurements)
    comparison_ref = content.comparison.artifact_ref
    values: list[UnderstandingPrompt] = [
        _prompt(
            prompt_id="purpose-boundary",
            kind=UnderstandingPromptKind.PURPOSE,
            question=(
                "Which part of the preserved evidence helps with what you want to "
                "understand, and what remains outside it?"
            ),
            refs=(content_ref, *result_refs, comparison_ref),
        ),
        _prompt(
            prompt_id="source-context",
            kind=UnderstandingPromptKind.SOURCE,
            question=(
                "What source, date, speaker, audience, or surrounding material should be "
                "checked before interpreting this content?"
            ),
            refs=(content_ref,),
        ),
        _prompt(
            prompt_id="discussion-without-presumption",
            kind=UnderstandingPromptKind.DISCUSSION,
            question=(
                "What open-ended question could you ask someone who encountered this "
                "content without presuming what it meant to them?"
            ),
            refs=(content_ref,),
        ),
    ]
    if context.known_context is not None:
        values.append(
            _prompt(
                prompt_id="known-context-boundary",
                kind=UnderstandingPromptKind.CONTEXT,
                question=(
                    "Which parts of the context you supplied are supported by the exact "
                    "stored content, and which remain assumptions to verify?"
                ),
                refs=(content_ref,),
            )
        )
    for index, question in enumerate(context.questions):
        values.append(
            _prompt(
                prompt_id=f"reader-question-{index}",
                kind=UnderstandingPromptKind.READER_QUESTION,
                question=(
                    f"For your question, {question} What can the preserved evidence answer, "
                    "and what requires direct source or human context?"
                ),
                refs=(content_ref, *result_refs, comparison_ref),
            )
        )
    if any(item.evidence_spans for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="highlighted-evidence",
                kind=UnderstandingPromptKind.EVIDENCE,
                question=(
                    "What do the highlighted excerpts communicate when read in their full "
                    "surrounding context?"
                ),
                refs=(content_ref, *result_refs),
            )
        )

    material_disagreement = any(
        item.material for item in content.comparison.disagreements
    )
    if material_disagreement:
        values.append(
            _prompt(
                prompt_id="material-disagreement",
                kind=UnderstandingPromptKind.DISAGREEMENT,
                question=(
                    "What ambiguity, contrast, or missing context might explain the "
                    "instruments' material disagreement?"
                ),
                refs=(comparison_ref, *result_refs),
            )
        )
    elif content.comparison.agreement_status == "agreement":
        values.append(
            _prompt(
                prompt_id="instrument-agreement",
                kind=UnderstandingPromptKind.AGREEMENT,
                question=(
                    "The instruments agreed on this measured dimension; what does that "
                    "agreement still not establish about meaning, truth, or impact?"
                ),
                refs=(comparison_ref, *result_refs),
            )
        )

    if any(item.abstention_triggered for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="instrument-abstention",
                kind=UnderstandingPromptKind.ABSTENTION,
                question=(
                    "What should be inspected manually instead of treating missing output "
                    "as evidence that no meaningful signal exists?"
                ),
                refs=result_refs,
            )
        )
    if content.comparison.abstention_triggered:
        values.append(
            _prompt(
                prompt_id="comparison-abstention",
                kind=UnderstandingPromptKind.ABSTENTION,
                question=(
                    "The comparison withheld a combined result; which original measurements "
                    "and excerpts should remain separate during review?"
                ),
                refs=(comparison_ref, *result_refs),
            )
        )
    if any(item.calibration_status != "validated" for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="calibration-boundary",
                kind=UnderstandingPromptKind.CALIBRATION,
                question=(
                    "The instruments do not claim validated calibration here; what limits "
                    "does that place on interpretation?"
                ),
                refs=result_refs,
            )
        )
    if any(item.applicability_status != "in-domain" for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="applicability-boundary",
                kind=UnderstandingPromptKind.APPLICABILITY,
                question=(
                    "Does this content fall within each instrument's declared applicability, "
                    "or should the output receive less interpretive weight?"
                ),
                refs=result_refs,
            )
        )
    if any(item.extraction_quality_status != "clean" for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="extraction-boundary",
                kind=UnderstandingPromptKind.EXTRACTION,
                question=(
                    "Should the original source be inspected before relying on measurements "
                    "derived from non-clean extraction?"
                ),
                refs=(content_ref, *result_refs),
            )
        )
    if any(item.preserved_uncertainties for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="preserved-uncertainty",
                kind=UnderstandingPromptKind.UNCERTAINTY,
                question=(
                    "Which preserved uncertainty most affects what can responsibly be "
                    "understood from this content?"
                ),
                refs=result_refs,
            )
        )
    if content.comparison.limitations:
        values.append(
            _prompt(
                prompt_id="comparison-limitations",
                kind=UnderstandingPromptKind.LIMITATION,
                question=(
                    "Which listed limitation most constrains what this evidence can support?"
                ),
                refs=(comparison_ref,),
            )
        )
    return tuple(values)


def build_content_understanding(
    *,
    request: ContentUnderstandingRequest,
    receipt: VerifiedStoredContentExperimentReceipt,
    artifact_store: FileSystemArtifactStore,
) -> ContentUnderstandingView:
    """Reverify stored evidence and derive content-directed reflection."""

    evidence_view = build_stored_content_evidence_view(
        receipt=receipt,
        artifact_store=artifact_store,
    )
    matches = tuple(
        item for item in evidence_view.contents if item.content_id == request.content_id
    )
    if len(matches) != 1:
        raise ContentUnderstandingError(
            "content_id must identify exactly one verified content item"
        )
    content = matches[0]
    return ContentUnderstandingView(
        understanding_version=CONTENT_UNDERSTANDING_VERSION,
        experiment_run_id=evidence_view.experiment_run_id,
        lifecycle_status=evidence_view.lifecycle_status,
        content_id=content.content_id,
        reader_context=request.context,
        evidence=content,
        observations=_observations(
            content=content,
            completion_refs=evidence_view.completion_refs,
        ),
        reflection_prompts=_reflection_prompts(
            context=request.context,
            content=content,
        ),
        completion_refs=evidence_view.completion_refs,
        inspection_paths=CONTENT_INSPECTION_PATHS,
        notices=CONTENT_UNDERSTANDING_NOTICES,
    )


def _markdown_quote(value: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in value.splitlines() or [""]]


def _display_optional(value: str | None) -> str:
    return value if value is not None else "not provided"


def _observation_heading(kind: UnderstandingObservationKind) -> str:
    return {
        UnderstandingObservationKind.LIFECYCLE: "Lifecycle",
        UnderstandingObservationKind.INSTRUMENT: "Instrument record",
        UnderstandingObservationKind.COMPARISON: "Comparison record",
        UnderstandingObservationKind.UNCERTAINTY: "Uncertainty",
        UnderstandingObservationKind.LIMITATION: "Limitation",
    }[kind]


def render_content_understanding_markdown(view: ContentUnderstandingView) -> str:
    """Render a content-directed inspection aid without choosing a conclusion."""

    lines = [
        "# Understand this content",
        "",
        (
            "CTRT helps you inspect the submitted content. It does not decide what the "
            "content means or what anyone should do."
        ),
        "",
        f"Understanding contract: `{view.understanding_version}`",
        "",
        "## Submitted content",
        "",
        *_markdown_quote(view.evidence.text),
        "",
        "## Your questions and context",
        "",
        "*Reader-provided purpose, context, and questions are not verified evidence.*",
        "",
        f"- Purpose: {view.reader_context.purpose}",
        f"- Known context: {_display_optional(view.reader_context.known_context)}",
        "- Questions: "
        + ("; ".join(view.reader_context.questions) or "none provided"),
        "",
        "## What the verified evidence records",
        "",
    ]
    for item in view.observations:
        lines.extend(
            [
                f"### {_observation_heading(item.kind)}",
                "",
                item.text,
                "",
            ]
        )

    lines.extend(["## Questions for closer inspection", ""])
    lines.extend(f"- [ ] {item.question}" for item in view.reflection_prompts)
    lines.extend(
        [
            "",
            "## Ways to continue understanding",
            "",
            "CTRT does not rank or select among these inspection paths:",
            "",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in view.inspection_paths)
    lines.extend(["", "## Interpretation boundary", ""])
    lines.extend(f"- {item}" for item in view.notices)

    references = _unique_refs(
        (
            *view.completion_refs,
            *view.evidence.artifact_refs,
            *(ref for item in view.observations for ref in item.evidence_refs),
            *(ref for item in view.reflection_prompts for ref in item.evidence_refs),
        )
    )
    lines.extend(["", "## Immutable evidence references", ""])
    lines.extend(
        f"- `{item.role}` → `{item.artifact_id}` (`{item.artifact_hash}`)"
        for item in references
    )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "CONTENT_INSPECTION_PATHS",
    "CONTENT_UNDERSTANDING_NOTICES",
    "CONTENT_UNDERSTANDING_VERSION",
    "ContentUnderstandingError",
    "ContentUnderstandingRequest",
    "ContentUnderstandingView",
    "ReaderProvidedContext",
    "UnderstandingObservation",
    "UnderstandingObservationKind",
    "UnderstandingPrompt",
    "UnderstandingPromptKind",
    "build_content_understanding",
    "render_content_understanding_markdown",
]
