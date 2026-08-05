"""Loopback-only browser surface over the local creator-preflight execution path.

This module renders HTML. It does not analyze content. Every measurement,
authorization, persistence, and verification step is delegated unchanged to
:func:`ctrt.creator_preflight_local.run_local_creator_preflight`.
"""

from __future__ import annotations

import argparse
import html
import ipaddress
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from ctrt.creator_preflight import (
    CreatorObservation,
    CreatorObservationKind,
    CreatorPreflightView,
    CreatorProvidedContext,
    _unique_refs,
)
from ctrt.creator_preflight_local import (
    DEFAULT_CANDIDATE_REGISTRY,
    DEFAULT_METHOD_REGISTRY,
    LocalCreatorPreflightError,
    LocalCreatorPreflightRequest,
    run_local_creator_preflight,
)
from ctrt.evidence_view import (
    ComparisonEvidenceView,
    EvidenceArtifactReference,
    InstrumentEvidenceView,
)

LOCAL_PREFLIGHT_WEB_VERSION = "ctrt-local-creator-preflight-web@0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_WORKSPACE = Path(".ctrt") / "creator-preflight-web-runs"

MAX_REQUEST_BYTES = 65_536
MAX_FORM_FIELDS = 16
MAX_DRAFT_CHARACTERS = 20_000
MAX_INTENT_CHARACTERS = 2_000
MAX_AUDIENCE_CHARACTERS = 500
MAX_CONCERNS_CHARACTERS = 4_000
MAX_CONCERNS = 20

FORM_PATH = "/"
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
ALLOWED_METHODS = ("GET", "POST")
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

SYNTHETIC_DEMONSTRATION_NOTICE = (
    "This is a local synthetic demonstration. The two analyzers recognize only the "
    "fixture words 'good' and 'bad'. They are not real tone, sentiment, or quality "
    "instruments, and their output is not evidence about real-world content."
)
LOCAL_ONLY_NOTICE = (
    "This server is bound to loopback only. It has no accounts, no authentication, "
    "no remote storage, and no monitoring. Anyone able to run code on this machine "
    "can reach it."
)
NO_DECISION_NOTICE = "CTRT does not decide whether this draft should be published."
CONTEXT_NOTICE = (
    "Creator-provided context is not verified evidence. It is recorded here only to "
    "shape the reflection questions, and it is never written into the canonical "
    "artifact store."
)
NEUTRALITY_NOTICE = (
    "Agreement between instruments is not approval. Disagreement is not a warning or "
    "a failure. A verified lifecycle describes artifact integrity, not analytical "
    "correctness."
)

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0 auto;
  padding: 1.5rem 1rem 4rem;
  max-width: 46rem;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 1rem;
  line-height: 1.55;
}
h1 { font-size: 1.5rem; margin: 0 0 0.5rem; }
h2 { font-size: 1.15rem; margin: 2rem 0 0.5rem; }
h3 { font-size: 1rem; margin: 1.25rem 0 0.25rem; font-weight: 600; }
p, li { margin: 0.4rem 0; }
label { display: block; margin: 1rem 0 0.25rem; font-weight: 600; }
.hint { font-size: 0.875rem; opacity: 0.8; margin: 0.15rem 0 0.35rem; }
input[type="text"], textarea {
  width: 100%;
  padding: 0.5rem;
  font: inherit;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  color: inherit;
}
textarea { min-height: 6rem; resize: vertical; }
button {
  margin-top: 1.25rem;
  padding: 0.55rem 1.1rem;
  font: inherit;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.note {
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 0.6rem 0.8rem;
  margin: 0.75rem 0;
  font-size: 0.925rem;
}
.card {
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 0.6rem 0.8rem;
  margin: 0.75rem 0;
}
.draft {
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
  font: inherit;
  margin: 0.5rem 0;
}
dl { margin: 0.4rem 0; }
dt { font-weight: 600; margin-top: 0.4rem; }
dd { margin: 0 0 0 1rem; }
code { font-size: 0.85rem; word-break: break-all; }
details { margin-top: 0.75rem; }
summary { cursor: pointer; font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td {
  border: 1px solid currentColor;
  padding: 0.3rem 0.4rem;
  text-align: left;
  vertical-align: top;
  word-break: break-all;
}
.errors { border: 1px solid currentColor; border-radius: 4px; padding: 0.6rem 0.8rem; }
footer { margin-top: 3rem; font-size: 0.875rem; opacity: 0.85; }
"""


class CreatorPreflightWebError(ValueError):
    """Raised when a local browser request cannot be served as specified."""


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _page(*, title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _boundary_notes() -> str:
    return "\n".join(
        f'<p class="note">{_esc(item)}</p>'
        for item in (
            SYNTHETIC_DEMONSTRATION_NOTICE,
            LOCAL_ONLY_NOTICE,
            NEUTRALITY_NOTICE,
        )
    )


@dataclass(frozen=True, slots=True)
class CreatorFormInput:
    """Exactly what the creator typed, preserved verbatim across re-rendering."""

    draft: str = ""
    intent: str = ""
    audience: str = ""
    concerns: str = ""


def render_creator_form_html(
    *,
    form: CreatorFormInput | None = None,
    errors: Sequence[str] = (),
) -> str:
    """Render the single plain-language creator form, preserving prior input."""

    values = form if form is not None else CreatorFormInput()
    error_block = ""
    if errors:
        items = "\n".join(f"<li>{_esc(item)}</li>" for item in errors)
        error_block = (
            '<div class="errors">\n'
            "<h2>This draft was not run</h2>\n"
            f"<ul>\n{items}\n</ul>\n"
            "</div>\n"
        )
    body = (
        "<h1>Check before I publish</h1>\n"
        f"<p>{_esc(NO_DECISION_NOTICE)}</p>\n"
        f"{_boundary_notes()}\n"
        f"{error_block}"
        f'<form method="post" action="{FORM_PATH}">\n'
        '<label for="draft">Your draft</label>\n'
        '<p class="hint" id="draft-hint">The exact text you are thinking of '
        f"publishing. Up to {MAX_DRAFT_CHARACTERS} characters.</p>\n"
        '<textarea id="draft" name="draft" rows="12" required '
        'aria-describedby="draft-hint">'
        f"{_esc(values.draft)}</textarea>\n"
        '<label for="intent">What you intend this draft to communicate</label>\n'
        '<p class="hint" id="intent-hint">Your own words. This is context, not '
        "evidence.</p>\n"
        '<input type="text" id="intent" name="intent" required '
        f'aria-describedby="intent-hint" value="{_esc(values.intent)}">\n'
        '<label for="audience">Intended audience (optional)</label>\n'
        '<input type="text" id="audience" name="audience" '
        f'value="{_esc(values.audience)}">\n'
        '<label for="concerns">Your concerns (optional)</label>\n'
        '<p class="hint" id="concerns-hint">One concern per line. Each line must be '
        "different.</p>\n"
        '<textarea id="concerns" name="concerns" rows="4" '
        'aria-describedby="concerns-hint">'
        f"{_esc(values.concerns)}</textarea>\n"
        "<button type=\"submit\">Run the synthetic preflight</button>\n"
        "</form>\n"
        "<footer>\n"
        f"<p>Interface contract: <code>{_esc(LOCAL_PREFLIGHT_WEB_VERSION)}</code></p>\n"
        "</footer>\n"
    )
    return _page(title="Check before I publish", body=body)


def _observation_heading(kind: CreatorObservationKind) -> str:
    return {
        CreatorObservationKind.LIFECYCLE: "Lifecycle",
        CreatorObservationKind.INSTRUMENT: "Instrument record",
        CreatorObservationKind.COMPARISON: "Comparison record",
        CreatorObservationKind.UNCERTAINTY: "Uncertainty",
        CreatorObservationKind.LIMITATION: "Limitation",
    }[kind]


def _observation_cards(observations: Sequence[CreatorObservation]) -> str:
    if not observations:
        return ""
    return "\n".join(
        '<div class="card">\n'
        f"<h3>{_esc(_observation_heading(item.kind))}</h3>\n"
        f"<p>{_esc(item.text)}</p>\n"
        "</div>"
        for item in observations
    )


def _instrument_details(measurement: InstrumentEvidenceView) -> str:
    measurements = (
        "\n".join(
            "<li>"
            f"{_esc(item.key)}: {_esc(f'{item.value:g}')} within "
            f"[{_esc(f'{item.lower_bound:g}')}, {_esc(f'{item.upper_bound:g}')}]"
            "</li>"
            for item in measurement.normalized_measurements
        )
        or "<li>No normalized measurement was recorded.</li>"
    )
    excerpts = (
        "\n".join(
            "<li>"
            f"<code>[{item.start}:{item.end}]</code> {_esc(item.excerpt)}"
            "</li>"
            for item in measurement.evidence_spans
        )
        or "<li>No supporting excerpt was recorded.</li>"
    )
    abstention = (
        "\n".join(f"<li>{_esc(item)}</li>" for item in measurement.abstention_reasons)
        or "<li>No abstention reason was recorded.</li>"
    )
    return (
        "<dl>\n"
        "<dt>Recorded status</dt>"
        f"<dd>{_esc(measurement.status)}</dd>\n"
        "<dt>Dimension</dt>"
        f"<dd>{_esc(measurement.dimension_id)} "
        f"({_esc(measurement.dimension_version)})</dd>\n"
        "<dt>Normalized measurements</dt>"
        f"<dd><ul>\n{measurements}\n</ul></dd>\n"
        "<dt>Exact supporting excerpts</dt>"
        f"<dd><ul>\n{excerpts}\n</ul></dd>\n"
        "<dt>Abstention withheld a measurement</dt>"
        f"<dd>{'yes' if measurement.abstention_triggered else 'no'}</dd>\n"
        "<dt>Preserved abstention reasons</dt>"
        f"<dd><ul>\n{abstention}\n</ul></dd>\n"
        "<dt>Calibration</dt>"
        f"<dd>{_esc(measurement.calibration_status)}</dd>\n"
        "<dt>Applicability</dt>"
        f"<dd>{_esc(measurement.applicability_status)}</dd>\n"
        "<dt>Extraction quality</dt>"
        f"<dd>{_esc(measurement.extraction_quality_status)}</dd>\n"
        "</dl>\n"
    )


def _instrument_sections(
    measurements: Sequence[InstrumentEvidenceView],
) -> str:
    return "\n".join(
        '<div class="card">\n'
        f"<h3>{_esc(item.analyzer_id)}</h3>\n"
        f"<p>Provider {_esc(item.provider)}, model {_esc(item.model_id)} "
        f"{_esc(item.model_version)}, adapter {_esc(item.adapter_version)}.</p>\n"
        f"{_instrument_details(item)}"
        "</div>"
        for item in measurements
    )


def _comparison_section(comparison: ComparisonEvidenceView) -> str:
    disagreements = (
        "\n".join(
            "<li>"
            f"{_esc(item.description)} "
            f"(material: {'yes' if item.material else 'no'}; results "
            f"{_esc(', '.join(item.result_ids))})"
            "</li>"
            for item in comparison.disagreements
        )
        or "<li>No disagreement was recorded.</li>"
    )
    abstention = (
        "\n".join(f"<li>{_esc(item)}</li>" for item in comparison.abstention_reasons)
        or "<li>No comparison abstention reason was recorded.</li>"
    )
    limitations = (
        "\n".join(f"<li>{_esc(item)}</li>" for item in comparison.limitations)
        or "<li>No limitation was recorded.</li>"
    )
    return (
        '<div class="card">\n'
        "<dl>\n"
        "<dt>Recorded agreement state</dt>"
        f"<dd>{_esc(comparison.agreement_status)}</dd>\n"
        "<dt>Recorded notes</dt>"
        f"<dd>{_esc(comparison.agreement_notes)}</dd>\n"
        "<dt>Comparison status</dt>"
        f"<dd>{_esc(comparison.status)}</dd>\n"
        "<dt>Preserved disagreements</dt>"
        f"<dd><ul>\n{disagreements}\n</ul></dd>\n"
        "<dt>Comparison withheld a combined result</dt>"
        f"<dd>{'yes' if comparison.abstention_triggered else 'no'}</dd>\n"
        "<dt>Preserved comparison abstention reasons</dt>"
        f"<dd><ul>\n{abstention}\n</ul></dd>\n"
        "<dt>Score combination permitted</dt>"
        f"<dd>{'yes' if comparison.score_combination_permitted else 'no'}</dd>\n"
        "<dt>Preserved limitations</dt>"
        f"<dd><ul>\n{limitations}\n</ul></dd>\n"
        "</dl>\n"
        "</div>\n"
    )


def _reference_rows(references: Sequence[EvidenceArtifactReference]) -> str:
    return "\n".join(
        "<tr>"
        f"<td><code>{_esc(item.role)}</code></td>"
        f"<td><code>{_esc(item.artifact_id)}</code></td>"
        f"<td><code>{_esc(item.artifact_hash)}</code></td>"
        "</tr>"
        for item in references
    )


def render_creator_preflight_html(view: CreatorPreflightView) -> str:
    """Render one verified reflection view without adding any judgement of it."""

    context = view.creator_context
    concerns = (
        "\n".join(f"<li>{_esc(item)}</li>" for item in context.concerns)
        or "<li>None provided.</li>"
    )
    instrument_observations = tuple(
        item
        for item in view.observations
        if item.kind is CreatorObservationKind.INSTRUMENT
    )
    other_observations = tuple(
        item
        for item in view.observations
        if item.kind is not CreatorObservationKind.INSTRUMENT
    )
    references = _unique_refs(
        (
            *view.completion_refs,
            *view.evidence.artifact_refs,
            *(ref for item in view.observations for ref in item.evidence_refs),
            *(ref for item in view.reflection_prompts for ref in item.evidence_refs),
        )
    )
    body = (
        "<h1>Check before I publish</h1>\n"
        f"<p>{_esc(NO_DECISION_NOTICE)}</p>\n"
        f"{_boundary_notes()}\n"
        "<h2>Your draft</h2>\n"
        f'<div class="draft">{_esc(view.evidence.text)}</div>\n'
        "<h2>Your context</h2>\n"
        f'<p class="note">{_esc(CONTEXT_NOTICE)}</p>\n'
        "<dl>\n"
        "<dt>Intended message</dt>"
        f"<dd>{_esc(context.intent)}</dd>\n"
        "<dt>Intended audience</dt>"
        f"<dd>{_esc(context.intended_audience or 'Not provided.')}</dd>\n"
        "<dt>Concerns</dt>"
        f"<dd><ul>\n{concerns}\n</ul></dd>\n"
        "</dl>\n"
        "<h2>What each instrument recorded separately</h2>\n"
        f"{_instrument_sections(view.evidence.measurements)}\n"
        f"{_observation_cards(instrument_observations)}\n"
        "<h2>Comparison, disagreement, abstention, uncertainty, and limitations</h2>\n"
        f"{_comparison_section(view.evidence.comparison)}\n"
        f"{_observation_cards(other_observations)}\n"
        "<h2>Questions for you</h2>\n"
        "<ul>\n"
        + "\n".join(
            f"<li>{_esc(item.question)}</li>" for item in view.reflection_prompts
        )
        + "\n</ul>\n"
        "<h2>Your decision remains yours</h2>\n"
        "<p>CTRT does not select among these creator-controlled actions:</p>\n"
        "<ul>\n"
        + "\n".join(
            f"<li>{_esc(item)}</li>" for item in view.creator_controlled_actions
        )
        + "\n</ul>\n"
        "<h2>Interpretation boundary</h2>\n"
        "<ul>\n"
        + "\n".join(f"<li>{_esc(item)}</li>" for item in view.notices)
        + "\n</ul>\n"
        "<details>\n"
        "<summary>Immutable evidence references</summary>\n"
        "<table>\n"
        "<thead><tr><th>Role</th><th>Artifact ID</th><th>Artifact hash</th></tr>"
        "</thead>\n"
        f"<tbody>\n{_reference_rows(references)}\n</tbody>\n"
        "</table>\n"
        "</details>\n"
        "<footer>\n"
        f"<p>Preflight contract: <code>{_esc(view.preflight_version)}</code></p>\n"
        f"<p>Interface contract: <code>{_esc(LOCAL_PREFLIGHT_WEB_VERSION)}</code></p>\n"
        f"<p>Experiment run: <code>{_esc(view.experiment_run_id)}</code></p>\n"
        f'<p><a href="{FORM_PATH}">Check another draft</a></p>\n'
        "</footer>\n"
    )
    return _page(title="Check before I publish", body=body)


@dataclass(frozen=True, slots=True)
class WebRequest:
    """One decoded local HTTP request, independent of any socket."""

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


@dataclass(frozen=True, slots=True)
class WebResponse:
    """One rendered local HTTP response with fixed protective headers."""

    status: int
    body: str
    extra_headers: tuple[tuple[str, str], ...] = ()

    @property
    def headers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Content-Type", HTML_CONTENT_TYPE),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Frame-Options", "DENY"),
            *self.extra_headers,
        )

    def encoded_body(self) -> bytes:
        return self.body.encode("utf-8")


def _message_page(*, title: str, detail: str) -> str:
    body = (
        f"<h1>{_esc(title)}</h1>\n"
        f"<p>{_esc(detail)}</p>\n"
        f'<p><a href="{FORM_PATH}">Return to the creator form</a></p>\n'
    )
    return _page(title=title, body=body)


def _bounded_field(
    values: Mapping[str, list[str]],
    name: str,
    limit: int,
    errors: list[str],
) -> str:
    entries = values.get(name, [])
    if len(entries) > 1:
        errors.append(f"The {name} field was submitted more than once.")
        return ""
    value = _normalize_newlines(entries[0]) if entries else ""
    if len(value) > limit:
        errors.append(f"The {name} field exceeds its {limit}-character limit.")
        return value[:limit]
    return value


def _parse_concerns(raw: str, errors: list[str]) -> tuple[str, ...]:
    values = tuple(line.strip() for line in raw.split("\n") if line.strip())
    if len(values) > MAX_CONCERNS:
        errors.append(f"At most {MAX_CONCERNS} concerns may be submitted.")
        return ()
    if len(values) != len(set(values)):
        errors.append("Each concern must be different from the others.")
        return ()
    return values


def _run_token() -> str:
    return f"web-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class CreatorPreflightWebApp:
    """Stateless request handler that delegates all analysis to the local path.

    The app holds immutable configuration only. No analytical state, rendered
    page, or evidence view is retained between requests.
    """

    workspace: Path = DEFAULT_WORKSPACE
    candidate_registry_path: Path = DEFAULT_CANDIDATE_REGISTRY
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY

    def handle(self, request: WebRequest) -> WebResponse:
        """Route one decoded request to the form, the preflight run, or an error."""

        if request.method not in ALLOWED_METHODS:
            return WebResponse(
                status=405,
                body=_message_page(
                    title="Method not allowed",
                    detail=(
                        "This local surface accepts only GET and POST on the creator "
                        "form."
                    ),
                ),
                extra_headers=(("Allow", ", ".join(ALLOWED_METHODS)),),
            )
        if request.path != FORM_PATH:
            return WebResponse(
                status=404,
                body=_message_page(
                    title="Not found",
                    detail="This local surface serves exactly one page.",
                ),
            )
        if request.method == "GET":
            return WebResponse(status=200, body=render_creator_form_html())
        return self._handle_submission(request)

    def _handle_submission(self, request: WebRequest) -> WebResponse:
        if len(request.body) > MAX_REQUEST_BYTES:
            return WebResponse(
                status=413,
                body=_message_page(
                    title="Submission too large",
                    detail=(
                        f"The request body exceeds the {MAX_REQUEST_BYTES}-byte limit "
                        "for this local surface."
                    ),
                ),
            )
        content_type = (request.header("Content-Type") or "").split(";")[0].strip()
        if content_type != FORM_CONTENT_TYPE:
            return WebResponse(
                status=415,
                body=_message_page(
                    title="Unsupported media type",
                    detail=(
                        f"The creator form submits {FORM_CONTENT_TYPE}. No other "
                        "request body is accepted."
                    ),
                ),
            )
        try:
            decoded = request.body.decode("utf-8")
        except UnicodeDecodeError:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Malformed submission",
                    detail="The request body was not valid UTF-8.",
                ),
            )
        try:
            values = parse_qs(
                decoded,
                keep_blank_values=True,
                strict_parsing=False,
                max_num_fields=MAX_FORM_FIELDS,
            )
        except ValueError:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Malformed submission",
                    detail=(
                        "The request body was not a readable form submission within "
                        f"the {MAX_FORM_FIELDS}-field limit."
                    ),
                ),
            )

        errors: list[str] = []
        form = CreatorFormInput(
            draft=_bounded_field(values, "draft", MAX_DRAFT_CHARACTERS, errors),
            intent=_bounded_field(values, "intent", MAX_INTENT_CHARACTERS, errors),
            audience=_bounded_field(
                values, "audience", MAX_AUDIENCE_CHARACTERS, errors
            ),
            concerns=_bounded_field(
                values, "concerns", MAX_CONCERNS_CHARACTERS, errors
            ),
        )
        concerns = _parse_concerns(form.concerns, errors)
        if errors:
            return WebResponse(
                status=400,
                body=render_creator_form_html(form=form, errors=errors),
            )

        audience = form.audience.strip() or None
        try:
            preflight_request = LocalCreatorPreflightRequest(
                draft_text=form.draft,
                context=CreatorProvidedContext(
                    intent=form.intent,
                    intended_audience=audience,
                    concerns=concerns,
                ),
                workspace=self.workspace,
                run_token=_run_token(),
                started_at=datetime.now(UTC),
                candidate_registry_path=self.candidate_registry_path,
                method_registry_path=self.method_registry_path,
            )
        except (LocalCreatorPreflightError, ValueError) as exc:
            return WebResponse(
                status=400,
                body=render_creator_form_html(form=form, errors=(str(exc),)),
            )

        try:
            result = run_local_creator_preflight(preflight_request)
        except (LocalCreatorPreflightError, OSError, RuntimeError, ValueError) as exc:
            return WebResponse(
                status=500,
                body=_message_page(
                    title="The preflight stopped before presentation",
                    detail=(
                        "Nothing is shown when required provenance, authorization, or "
                        f"completion evidence cannot be verified. Reported cause: {exc}"
                    ),
                ),
            )
        return WebResponse(
            status=200,
            body=render_creator_preflight_html(result.preflight_view),
        )


class _CreatorPreflightRequestHandler(BaseHTTPRequestHandler):
    """Translate loopback HTTP into the pure request/response core and back."""

    server_version = "CTRTLocalCreatorPreflight/0.1"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def _app(self) -> CreatorPreflightWebApp:
        app = getattr(self.server, "creator_preflight_app", None)
        if not isinstance(app, CreatorPreflightWebApp):
            raise CreatorPreflightWebError("server is missing its preflight app")
        return app

    def _respond(self, response: WebResponse) -> None:
        payload = response.encoded_body()
        self.send_response(response.status)
        for name, value in response.headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _read_body(self) -> bytes | WebResponse:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return WebResponse(
                status=411,
                body=_message_page(
                    title="Length required",
                    detail="A form submission must declare its Content-Length.",
                ),
            )
        try:
            length = int(raw_length)
        except ValueError:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Malformed submission",
                    detail="The declared Content-Length was not an integer.",
                ),
            )
        if length < 0:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Malformed submission",
                    detail="The declared Content-Length was negative.",
                ),
            )
        if length > MAX_REQUEST_BYTES:
            self.close_connection = True
            return WebResponse(
                status=413,
                body=_message_page(
                    title="Submission too large",
                    detail=(
                        f"The request body exceeds the {MAX_REQUEST_BYTES}-byte limit "
                        "for this local surface."
                    ),
                ),
            )
        return self.rfile.read(length)

    def _dispatch(self, method: str, body: bytes) -> None:
        self._respond(
            self._app.handle(
                WebRequest(
                    method=method,
                    path=self.path,
                    headers={key: value for key, value in self.headers.items()},
                    body=body,
                )
            )
        )

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Serve the creator form."""

        self._dispatch("GET", b"")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Run one bounded preflight and serve its rendered evidence."""

        body = self._read_body()
        if isinstance(body, WebResponse):
            self._respond(body)
            return
        self._dispatch("POST", body)

    def do_HEAD(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Refuse HEAD explicitly rather than leaving it unimplemented."""

        self._dispatch("HEAD", b"")

    def do_PUT(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Refuse PUT with the allowed method set."""

        self._dispatch("PUT", b"")

    def do_DELETE(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Refuse DELETE with the allowed method set."""

        self._dispatch("DELETE", b"")

    def do_PATCH(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Refuse PATCH with the allowed method set."""

        self._dispatch("PATCH", b"")

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Refuse OPTIONS with the allowed method set."""

        self._dispatch("OPTIONS", b"")

    def log_message(self, format: str, *args: object) -> None:
        """Keep the local surface quiet rather than writing a request log."""

        return


class _CreatorPreflightServer(ThreadingHTTPServer):
    """Loopback HTTP server carrying one immutable app configuration."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        app: CreatorPreflightWebApp,
    ) -> None:
        self.creator_preflight_app = app
        super().__init__(server_address, _CreatorPreflightRequestHandler)


def validate_loopback_host(host: str) -> str:
    """Return the host only when it is a validated loopback address."""

    if host == "localhost":
        return host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise CreatorPreflightWebError(
            f"host must be a loopback address, not {host!r}"
        ) from exc
    if not address.is_loopback:
        raise CreatorPreflightWebError(
            f"host must be a loopback address, not {host!r}"
        )
    return host


def build_server(
    *,
    app: CreatorPreflightWebApp,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> _CreatorPreflightServer:
    """Bind a loopback-only server, refusing any externally reachable address."""

    validate_loopback_host(host)
    if not 0 <= port <= 65_535:
        raise CreatorPreflightWebError(f"port must be within 0-65535, not {port}")
    return _CreatorPreflightServer((host, port), app)


def local_url(server: _CreatorPreflightServer) -> str:
    """Return the loopback URL a creator should open."""

    host, port = server.server_address[0], server.server_address[1]
    text = host.decode("ascii") if isinstance(host, bytes | bytearray) else str(host)
    if ":" in text:
        text = f"[{text}]"
    return f"http://{text}:{port}{FORM_PATH}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.creator_preflight_web",
        description=(
            "Serve a loopback-only browser form over the authorized synthetic CTRT "
            "creator-preflight demonstration."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Loopback address to bind. Non-loopback addresses are refused.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Loopback port to bind. Use 0 to let the operating system choose.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="Directory that will contain one append-only artifact store per run.",
    )
    parser.add_argument(
        "--candidate-registry",
        type=Path,
        default=DEFAULT_CANDIDATE_REGISTRY,
    )
    parser.add_argument(
        "--method-registry",
        type=Path,
        default=DEFAULT_METHOD_REGISTRY,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the bounded local browser surface."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    app = CreatorPreflightWebApp(
        workspace=arguments.workspace,
        candidate_registry_path=arguments.candidate_registry,
        method_registry_path=arguments.method_registry,
    )
    try:
        server = build_server(app=app, host=arguments.host, port=arguments.port)
    except (CreatorPreflightWebError, OSError) as exc:
        parser.exit(2, f"creator preflight web surface failed: {exc}\n")
        return 2
    sys.stdout.write(
        f"CTRT local creator preflight (synthetic demonstration) at {local_url(server)}\n"
        f"Artifact workspace: {app.workspace}\n"
        "This server is loopback-only and has no authentication. Press Ctrl+C to stop.\n"
    )
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("Stopped.\n")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_WORKSPACE",
    "LOCAL_PREFLIGHT_WEB_VERSION",
    "MAX_CONCERNS",
    "MAX_DRAFT_CHARACTERS",
    "MAX_REQUEST_BYTES",
    "CreatorFormInput",
    "CreatorPreflightWebApp",
    "CreatorPreflightWebError",
    "WebRequest",
    "WebResponse",
    "build_server",
    "local_url",
    "main",
    "render_creator_form_html",
    "render_creator_preflight_html",
    "validate_loopback_host",
]
