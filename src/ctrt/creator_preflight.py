"""Plain-language creator reflection derived from verified CTRT evidence."""

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

CREATOR_PREFLIGHT_VERSION = "ctrt-creator-preflight@0.1.0"
CREATOR_PREFLIGHT_NOTICES = (
    "This preflight is a derived reflection aid. Canonical stored artifacts remain controlling.",
    "Creator-provided intent, audience, and concerns are context, not verified evidence.",
    "Verified describes lifecycle and evidence integrity, not analytical success or correctness.",
    (
        "No overall CTRT score, content verdict, publish recommendation, restriction, or "
        "production-readiness claim is produced."
    ),
    "The creator remains responsible for whether to publish, revise, pause, or seek human feedback.",
)
CREATOR_CONTROLLED_ACTIONS = (
    "Publish as written.",
    "Revise the draft and run preflight again.",
    "Pause without publishing.",
    "Seek feedback from a person who understands the context.",
)


class CreatorPreflightError(ValueError):
    """Raised when exact verified evidence cannot support creator preflight."""


class CreatorObservationKind(StrEnum):
    """Plain-language evidence category without analytical aggregation."""

    LIFECYCLE = "lifecycle"
    INSTRUMENT = "instrument"
    COMPARISON = "comparison"
    UNCERTAINTY = "uncertainty"
    LIMITATION = "limitation"


class CreatorPromptKind(StrEnum):
    """Reason a reflection question appears in creator preflight."""

    INTENT = "intent"
    AUDIENCE = "audience"
    CONTEXT = "context"
    CREATOR_CONCERN = "creator-concern"
    EVIDENCE = "evidence"
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
class CreatorProvidedContext:
    """Context supplied by the creator and explicitly kept outside evidence."""

    intent: str
    intended_audience: str | None = None
    concerns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.intent, "creator intent")
        if self.intended_audience is not None:
            _require_text(self.intended_audience, "intended audience")
        if any(not item.strip() for item in self.concerns):
            raise ValueError("creator concerns must not contain empty values")
        if len(self.concerns) != len(set(self.concerns)):
            raise ValueError("creator concerns must not contain duplicates")


@dataclass(frozen=True, slots=True)
class CreatorPreflightRequest:
    """Select one exact stored draft and provide non-evidentiary creator context."""

    content_id: str
    context: CreatorProvidedContext

    def __post_init__(self) -> None:
        _require_text(self.content_id, "content_id")


@dataclass(frozen=True, slots=True)
class CreatorObservation:
    """One plain-language statement traceable to immutable evidence."""

    observation_id: str
    kind: CreatorObservationKind
    text: str
    evidence_refs: tuple[EvidenceArtifactReference, ...]

    def __post_init__(self) -> None:
        _require_text(self.observation_id, "observation_id")
        _require_text(self.text, "observation text")
        if not self.evidence_refs:
            raise ValueError("creator observation requires evidence references")
        if self.evidence_refs != _unique_refs(self.evidence_refs):
            raise ValueError("creator observation evidence references must be unique")


@dataclass(frozen=True, slots=True)
class CreatorReflectionPrompt:
    """One deterministic question that leaves the decision with the creator."""

    prompt_id: str
    kind: CreatorPromptKind
    question: str
    evidence_refs: tuple[EvidenceArtifactReference, ...]

    def __post_init__(self) -> None:
        _require_text(self.prompt_id, "prompt_id")
        _require_text(self.question, "reflection question")
        if not self.question.endswith("?"):
            raise ValueError("reflection question must end with a question mark")
        if not self.evidence_refs:
            raise ValueError("reflection prompt requires evidence references")
        if self.evidence_refs != _unique_refs(self.evidence_refs):
            raise ValueError("reflection prompt evidence references must be unique")


@dataclass(frozen=True, slots=True)
class CreatorPreflightView:
    """Noncanonical reflection view over one exact verified content item."""

    preflight_version: str
    experiment_run_id: str
    lifecycle_status: str
    content_id: str
    creator_context: CreatorProvidedContext
    evidence: ContentEvidenceView
    observations: tuple[CreatorObservation, ...]
    reflection_prompts: tuple[CreatorReflectionPrompt, ...]
    completion_refs: tuple[EvidenceArtifactReference, ...]
    creator_controlled_actions: tuple[str, ...]
    notices: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.preflight_version != CREATOR_PREFLIGHT_VERSION:
            raise ValueError("unsupported creator preflight version")
        if self.lifecycle_status != "verified":
            raise ValueError("creator preflight requires a verified evidence lifecycle")
        if self.content_id != self.evidence.content_id:
            raise ValueError("creator preflight content must match exact evidence")
        if not self.observations:
            raise ValueError("creator preflight requires evidence observations")
        if not self.reflection_prompts:
            raise ValueError("creator preflight requires reflection prompts")
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("creator observation IDs must be unique")
        prompt_ids = tuple(item.prompt_id for item in self.reflection_prompts)
        if len(prompt_ids) != len(set(prompt_ids)):
            raise ValueError("creator prompt IDs must be unique")
        if self.creator_controlled_actions != CREATOR_CONTROLLED_ACTIONS:
            raise ValueError("creator preflight must preserve neutral creator actions")
        if self.notices != CREATOR_PREFLIGHT_NOTICES:
            raise ValueError("creator preflight must preserve interpretation notices")


def _role_ref(
    content: ContentEvidenceView,
    role: str,
) -> EvidenceArtifactReference:
    values = tuple(item for item in content.artifact_refs if item.role == role)
    if len(values) != 1:
        raise CreatorPreflightError(
            f"content evidence must contain exactly one {role!r} reference"
        )
    return values[0]


def _measurement_text(measurement: InstrumentEvidenceView) -> str:
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
    if not values:
        values = "no normalized measurement"
    if not excerpts:
        excerpts = "no local evidence excerpt"
    return (
        f"{measurement.analyzer_id} returned status {measurement.status} and recorded "
        f"{values}. Exact supporting evidence: {excerpts}."
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
) -> tuple[CreatorObservation, ...]:
    values: list[CreatorObservation] = [
        CreatorObservation(
            observation_id="lifecycle-verified",
            kind=CreatorObservationKind.LIFECYCLE,
            text=(
                "The stored evidence lifecycle verified for this draft. This confirms "
                "artifact identity and completion, not analytical correctness."
            ),
            evidence_refs=_unique_refs(
                (*completion_refs, _role_ref(content, "session-receipt"))
            ),
        )
    ]
    for index, measurement in enumerate(content.measurements):
        values.append(
            CreatorObservation(
                observation_id=f"instrument-{index}",
                kind=CreatorObservationKind.INSTRUMENT,
                text=_measurement_text(measurement),
                evidence_refs=(measurement.artifact_ref,),
            )
        )
        uncertainty = _uncertainty_text(measurement)
        if uncertainty is not None:
            values.append(
                CreatorObservation(
                    observation_id=f"uncertainty-{index}",
                    kind=CreatorObservationKind.UNCERTAINTY,
                    text=uncertainty,
                    evidence_refs=(measurement.artifact_ref,),
                )
            )
    values.append(
        CreatorObservation(
            observation_id="comparison",
            kind=CreatorObservationKind.COMPARISON,
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
            CreatorObservation(
                observation_id="comparison-limitations",
                kind=CreatorObservationKind.LIMITATION,
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
    kind: CreatorPromptKind,
    question: str,
    refs: tuple[EvidenceArtifactReference, ...],
) -> CreatorReflectionPrompt:
    return CreatorReflectionPrompt(
        prompt_id=prompt_id,
        kind=kind,
        question=question,
        evidence_refs=_unique_refs(refs),
    )


def _reflection_prompts(
    *,
    context: CreatorProvidedContext,
    content: ContentEvidenceView,
) -> tuple[CreatorReflectionPrompt, ...]:
    content_ref = _role_ref(content, "canonical-content")
    result_refs = tuple(item.artifact_ref for item in content.measurements)
    comparison_ref = content.comparison.artifact_ref
    values: list[CreatorReflectionPrompt] = [
        _prompt(
            prompt_id="intent-alignment",
            kind=CreatorPromptKind.INTENT,
            question=(
                "Does the evidence shown here match what you intended this draft to "
                "communicate?"
            ),
            refs=(content_ref, *result_refs, comparison_ref),
        ),
        _prompt(
            prompt_id="missing-context",
            kind=CreatorPromptKind.CONTEXT,
            question=(
                "What context is present in your mind but absent from the exact stored text?"
            ),
            refs=(content_ref,),
        ),
    ]
    if context.intended_audience is not None:
        values.append(
            _prompt(
                prompt_id="audience-interpretation",
                kind=CreatorPromptKind.AUDIENCE,
                question=(
                    "How might your intended audience understand the highlighted wording "
                    "differently from your intent?"
                ),
                refs=(content_ref, *result_refs),
            )
        )
    for index, concern in enumerate(context.concerns):
        values.append(
            _prompt(
                prompt_id=f"creator-concern-{index}",
                kind=CreatorPromptKind.CREATOR_CONCERN,
                question=(
                    f"You identified this concern: {concern} Which evidence addresses it, "
                    "and what remains unanswered?"
                ),
                refs=(content_ref, *result_refs, comparison_ref),
            )
        )

    if any(item.evidence_spans for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="highlighted-evidence",
                kind=CreatorPromptKind.EVIDENCE,
                question=(
                    "Are the highlighted excerpts carrying the emphasis you intended when "
                    "read in their full surrounding context?"
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
                kind=CreatorPromptKind.DISAGREEMENT,
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
                kind=CreatorPromptKind.AGREEMENT,
                question=(
                    "The instruments agreed on this measured dimension; is that signal "
                    "intentional, and does it receive more emphasis than you intended?"
                ),
                refs=(comparison_ref, *result_refs),
            )
        )

    if any(item.abstention_triggered for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="instrument-abstention",
                kind=CreatorPromptKind.ABSTENTION,
                question=(
                    "What should you inspect manually instead of treating an instrument's "
                    "missing output as absence of a signal?"
                ),
                refs=result_refs,
            )
        )
    if content.comparison.abstention_triggered:
        values.append(
            _prompt(
                prompt_id="comparison-abstention",
                kind=CreatorPromptKind.ABSTENTION,
                question=(
                    "The comparison withheld a combined result; which original measurements "
                    "and excerpts deserve your attention before you decide?"
                ),
                refs=(comparison_ref, *result_refs),
            )
        )

    if any(item.calibration_status != "validated" for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="calibration-boundary",
                kind=CreatorPromptKind.CALIBRATION,
                question=(
                    "The instruments do not claim validated calibration here; what weight, "
                    "if any, should you give these measurements?"
                ),
                refs=result_refs,
            )
        )
    if any(item.applicability_status != "in-domain" for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="applicability-boundary",
                kind=CreatorPromptKind.APPLICABILITY,
                question=(
                    "Does this draft fall within each instrument's declared applicability, "
                    "or should its output receive less weight?"
                ),
                refs=result_refs,
            )
        )
    if any(item.extraction_quality_status != "clean" for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="extraction-boundary",
                kind=CreatorPromptKind.EXTRACTION,
                question=(
                    "Should you inspect the original source before relying on measurements "
                    "derived from non-clean extraction?"
                ),
                refs=(content_ref, *result_refs),
            )
        )
    if any(item.preserved_uncertainties for item in content.measurements):
        values.append(
            _prompt(
                prompt_id="preserved-uncertainty",
                kind=CreatorPromptKind.UNCERTAINTY,
                question=(
                    "Which preserved uncertainty matters most to your decision about this "
                    "draft?"
                ),
                refs=result_refs,
            )
        )
    if content.comparison.limitations:
        values.append(
            _prompt(
                prompt_id="comparison-limitations",
                kind=CreatorPromptKind.LIMITATION,
                question="Which listed limitation matters most for this draft and audience?",
                refs=(comparison_ref,),
            )
        )
    return tuple(values)


def build_creator_preflight(
    *,
    request: CreatorPreflightRequest,
    receipt: VerifiedStoredContentExperimentReceipt,
    artifact_store: FileSystemArtifactStore,
) -> CreatorPreflightView:
    """Reverify stored evidence and derive one creator-controlled reflection view."""

    evidence_view = build_stored_content_evidence_view(
        receipt=receipt,
        artifact_store=artifact_store,
    )
    matches = tuple(
        item for item in evidence_view.contents if item.content_id == request.content_id
    )
    if len(matches) != 1:
        raise CreatorPreflightError(
            "creator preflight content_id must identify exactly one verified content item"
        )
    content = matches[0]
    return CreatorPreflightView(
        preflight_version=CREATOR_PREFLIGHT_VERSION,
        experiment_run_id=evidence_view.experiment_run_id,
        lifecycle_status=evidence_view.lifecycle_status,
        content_id=content.content_id,
        creator_context=request.context,
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
        creator_controlled_actions=CREATOR_CONTROLLED_ACTIONS,
        notices=CREATOR_PREFLIGHT_NOTICES,
    )


def _markdown_quote(value: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in value.splitlines() or [""]]


def _display_optional(value: str | None) -> str:
    return value if value is not None else "not provided"


def _observation_heading(kind: CreatorObservationKind) -> str:
    return {
        CreatorObservationKind.LIFECYCLE: "Lifecycle",
        CreatorObservationKind.INSTRUMENT: "Instrument record",
        CreatorObservationKind.COMPARISON: "Comparison record",
        CreatorObservationKind.UNCERTAINTY: "Uncertainty",
        CreatorObservationKind.LIMITATION: "Limitation",
    }[kind]


def render_creator_preflight_markdown(view: CreatorPreflightView) -> str:
    """Render a plain-language reflection aid without choosing a creator action."""

    lines = [
        "# Check before I publish",
        "",
        "CTRT does not decide whether this draft should be published.",
        "",
        f"Preflight contract: `{view.preflight_version}`",
        "",
        "## Your draft",
        "",
        *_markdown_quote(view.evidence.text),
        "",
        "## Your context",
        "",
        "*Creator-provided context is not verified evidence.*",
        "",
        f"- Intended message: {view.creator_context.intent}",
        f"- Intended audience: {_display_optional(view.creator_context.intended_audience)}",
        "- Concerns: "
        + ("; ".join(view.creator_context.concerns) or "none provided"),
        "",
        "## What the evidence records",
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

    lines.extend(["## Questions for you", ""])
    lines.extend(f"- [ ] {item.question}" for item in view.reflection_prompts)
    lines.extend(
        [
            "",
            "## Your decision remains yours",
            "",
            "CTRT does not select among these creator-controlled actions:",
            "",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in view.creator_controlled_actions)
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
    "CREATOR_CONTROLLED_ACTIONS",
    "CREATOR_PREFLIGHT_NOTICES",
    "CREATOR_PREFLIGHT_VERSION",
    "CreatorObservation",
    "CreatorObservationKind",
    "CreatorPreflightError",
    "CreatorPreflightRequest",
    "CreatorPreflightView",
    "CreatorPromptKind",
    "CreatorProvidedContext",
    "CreatorReflectionPrompt",
    "build_creator_preflight",
    "render_creator_preflight_markdown",
]
