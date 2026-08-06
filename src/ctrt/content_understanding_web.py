"""Loopback-only browser surface over local content understanding.

This module renders HTML and translates HTTP. It delegates extraction,
eligibility, analysis, persistence, and verification unchanged to
:func:`ctrt.content_understanding_local.run_local_content_understanding`.
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

from ctrt.content_understanding import (
    ContentUnderstandingView,
    ReaderProvidedContext,
    UnderstandingObservation,
    UnderstandingObservationKind,
    _unique_refs,
)
from ctrt.content_understanding_local import (
    LocalContentUnderstandingError,
    LocalContentUnderstandingRequest,
    run_local_content_understanding,
)
from ctrt.creator_preflight_local import (
    DEFAULT_CANDIDATE_REGISTRY,
    DEFAULT_METHOD_REGISTRY,
)
from ctrt.evidence_view import (
    ComparisonEvidenceView,
    EvidenceArtifactReference,
    InstrumentEvidenceView,
)

LOCAL_CONTENT_UNDERSTANDING_WEB_VERSION = (
    "ctrt-local-content-understanding-web@0.1.0"
)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
DEFAULT_WORKSPACE = Path(".ctrt") / "content-understanding-web-runs"

MAX_REQUEST_BYTES = 65_536
MAX_FORM_FIELDS = 12
MAX_CONTENT_CHARACTERS = 20_000
MAX_PURPOSE_CHARACTERS = 2_000
MAX_CONTEXT_CHARACTERS = 4_000
MAX_QUESTIONS_CHARACTERS = 4_000
MAX_QUESTIONS = 20

FORM_PATH = "/"
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
ALLOWED_METHODS = ("GET", "POST")
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

SYNTHETIC_DEMONSTRATION_NOTICE = (
    "This is a local synthetic demonstration. The two analyzers recognize only "
    "the fixture words 'good' and 'bad'. They are not real meaning, safety, tone, "
    "or quality instruments."
)
LOCAL_ONLY_NOTICE = (
    "This server is bound to loopback only. It has no accounts, authentication, "
    "remote storage, analytics, or monitoring. Anyone able to run code on this "
    "machine may be able to reach it."
)
NO_DECISION_NOTICE = (
    "CTRT helps inspect submitted content. It does not decide what the content "
    "means or what anyone should do."
)
CONTEXT_NOTICE = (
    "Reader-provided purpose, context, and questions are not verified evidence. "
    "They shape reflection questions but are never written into canonical evidence."
)
NEUTRALITY_NOTICE = (
    "Agreement is not approval. Disagreement is not a warning or failure. "
    "Abstention is not proof that no meaningful signal exists. Verified describes "
    "artifact integrity, not analytical correctness."
)

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0 auto; padding: 1.5rem 1rem 4rem; max-width: 48rem;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.55; }
h1 { font-size: 1.5rem; margin: 0 0 .5rem; }
h2 { font-size: 1.15rem; margin: 2rem 0 .5rem; }
h3 { font-size: 1rem; margin: 1.25rem 0 .25rem; }
p, li { margin: .4rem 0; }
label { display: block; margin: 1rem 0 .25rem; font-weight: 600; }
.hint { font-size: .875rem; opacity: .8; margin: .15rem 0 .35rem; }
input[type="text"], textarea { width: 100%; padding: .5rem; font: inherit;
  border: 1px solid currentColor; border-radius: 4px; background: transparent;
  color: inherit; }
textarea { min-height: 6rem; resize: vertical; }
button { margin-top: 1.25rem; padding: .55rem 1.1rem; font: inherit;
  border: 1px solid currentColor; border-radius: 4px; background: transparent;
  color: inherit; cursor: pointer; }
.note, .card, .errors { border: 1px solid currentColor; border-radius: 4px;
  padding: .65rem .8rem; margin: .75rem 0; }
.submitted { border: 1px solid currentColor; border-radius: 4px; padding: .8rem;
  white-space: pre-wrap; word-break: break-word; }
dl { margin: .4rem 0; }
dt { font-weight: 600; margin-top: .4rem; }
dd { margin: 0 0 0 1rem; }
code { font-size: .85rem; word-break: break-all; }
details { margin-top: .75rem; }
summary { cursor: pointer; font-weight: 600; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { border: 1px solid currentColor; padding: .3rem .4rem; text-align: left;
  vertical-align: top; word-break: break-all; }
footer { margin-top: 3rem; font-size: .875rem; opacity: .85; }
"""


class ContentUnderstandingWebError(ValueError):
    """Raised when a local browser request cannot be served safely."""


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _page(*, title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n<style>{_STYLE}</style>\n"
        f"</head>\n<body>\n{body}\n</body>\n</html>\n"
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
class UnderstandingFormInput:
    """Exactly what the reader typed, retained only for form re-rendering."""

    content: str = ""
    purpose: str = ""
    known_context: str = ""
    questions: str = ""


def render_content_form_html(
    *,
    form: UnderstandingFormInput | None = None,
    errors: Sequence[str] = (),
) -> str:
    """Render the bounded reader form while escaping all prior input."""

    values = form if form is not None else UnderstandingFormInput()
    error_block = ""
    if errors:
        items = "\n".join(f"<li>{_esc(item)}</li>" for item in errors)
        error_block = (
            '<div class="errors"><h2>This content was not run</h2>'
            f"<ul>{items}</ul></div>\n"
        )
    body = (
        "<h1>Understand this content</h1>\n"
        f"<p>{_esc(NO_DECISION_NOTICE)}</p>\n{_boundary_notes()}\n{error_block}"
        f'<form method="post" action="{FORM_PATH}">\n'
        '<label for="content">Content to inspect</label>\n'
        f'<p class="hint">Exact submitted text. Up to {MAX_CONTENT_CHARACTERS} characters.</p>\n'
        '<textarea id="content" name="content" rows="12" required>'
        f"{_esc(values.content)}</textarea>\n"
        '<label for="purpose">What are you trying to understand?</label>\n'
        '<p class="hint">Your purpose is context, not verified evidence.</p>\n'
        '<input type="text" id="purpose" name="purpose" required '
        f'value="{_esc(values.purpose)}">\n'
        '<label for="known-context">Known context (optional)</label>\n'
        '<textarea id="known-context" name="known_context" rows="4">'
        f"{_esc(values.known_context)}</textarea>\n"
        '<label for="questions">Questions (optional)</label>\n'
        '<p class="hint">One distinct question ending in ? per line.</p>\n'
        '<textarea id="questions" name="questions" rows="4">'
        f"{_esc(values.questions)}</textarea>\n"
        '<button type="submit">Run synthetic content inspection</button>\n'
        "</form>\n<footer>\n"
        f"<p>Interface contract: <code>{_esc(LOCAL_CONTENT_UNDERSTANDING_WEB_VERSION)}</code></p>\n"
        "</footer>"
    )
    return _page(title="Understand this content", body=body)


def _observation_heading(kind: UnderstandingObservationKind) -> str:
    return {
        UnderstandingObservationKind.LIFECYCLE: "Lifecycle",
        UnderstandingObservationKind.INSTRUMENT: "Instrument record",
        UnderstandingObservationKind.COMPARISON: "Comparison record",
        UnderstandingObservationKind.UNCERTAINTY: "Uncertainty",
        UnderstandingObservationKind.LIMITATION: "Limitation",
    }[kind]


def _observation_cards(observations: Sequence[UnderstandingObservation]) -> str:
    return "\n".join(
        '<div class="card">'
        f"<h3>{_esc(_observation_heading(item.kind))}</h3>"
        f"<p>{_esc(item.text)}</p></div>"
        for item in observations
    )


def _instrument_section(measurement: InstrumentEvidenceView) -> str:
    values = "\n".join(
        f"<li>{_esc(item.key)}: {item.value:g} within "
        f"[{item.lower_bound:g}, {item.upper_bound:g}]</li>"
        for item in measurement.normalized_measurements
    ) or "<li>No normalized measurement was recorded.</li>"
    spans = "\n".join(
        f"<li><code>[{item.start}:{item.end}]</code> {_esc(item.excerpt)}</li>"
        for item in measurement.evidence_spans
    ) or "<li>No exact supporting excerpt was recorded.</li>"
    abstentions = "\n".join(
        f"<li>{_esc(item)}</li>" for item in measurement.abstention_reasons
    ) or "<li>No abstention reason was recorded.</li>"
    uncertainties = "\n".join(
        f"<li>{_esc(item)}</li>" for item in measurement.preserved_uncertainties
    ) or "<li>No additional uncertainty was recorded.</li>"
    return (
        '<div class="card">'
        f"<h3>{_esc(measurement.analyzer_id)}</h3><dl>"
        f"<dt>Status</dt><dd>{_esc(measurement.status)}</dd>"
        f"<dt>Provider and model</dt><dd>{_esc(measurement.provider)} / "
        f"{_esc(measurement.model_id)} {_esc(measurement.model_version)}</dd>"
        f"<dt>Dimension</dt><dd>{_esc(measurement.dimension_id)} "
        f"{_esc(measurement.dimension_version)}</dd>"
        f"<dt>Measurements</dt><dd><ul>{values}</ul></dd>"
        f"<dt>Exact excerpts</dt><dd><ul>{spans}</ul></dd>"
        f"<dt>Evidence support</dt><dd>{_esc(measurement.evidence_support_status)}</dd>"
        f"<dt>Calibration</dt><dd>{_esc(measurement.calibration_status)}</dd>"
        f"<dt>Applicability</dt><dd>{_esc(measurement.applicability_status)}</dd>"
        f"<dt>Extraction quality</dt><dd>{_esc(measurement.extraction_quality_status)}</dd>"
        f"<dt>Abstention</dt><dd>{'yes' if measurement.abstention_triggered else 'no'}</dd>"
        f"<dt>Abstention reasons</dt><dd><ul>{abstentions}</ul></dd>"
        f"<dt>Ambiguity</dt><dd>{_esc(measurement.ambiguity_status)}</dd>"
        f"<dt>Preserved uncertainties</dt><dd><ul>{uncertainties}</ul></dd>"
        "</dl></div>"
    )


def _comparison_section(comparison: ComparisonEvidenceView) -> str:
    disagreements = "\n".join(
        f"<li>{_esc(item.description)} (material: "
        f"{'yes' if item.material else 'no'})</li>"
        for item in comparison.disagreements
    ) or "<li>No disagreement was recorded.</li>"
    abstentions = "\n".join(
        f"<li>{_esc(item)}</li>" for item in comparison.abstention_reasons
    ) or "<li>No comparison abstention reason was recorded.</li>"
    limitations = "\n".join(
        f"<li>{_esc(item)}</li>" for item in comparison.limitations
    ) or "<li>No limitation was recorded.</li>"
    return (
        '<div class="card"><dl>'
        f"<dt>Agreement state</dt><dd>{_esc(comparison.agreement_status)}</dd>"
        f"<dt>Notes</dt><dd>{_esc(comparison.agreement_notes)}</dd>"
        f"<dt>Status</dt><dd>{_esc(comparison.status)}</dd>"
        f"<dt>Disagreements</dt><dd><ul>{disagreements}</ul></dd>"
        f"<dt>Combined result withheld</dt><dd>"
        f"{'yes' if comparison.abstention_triggered else 'no'}</dd>"
        f"<dt>Abstention reasons</dt><dd><ul>{abstentions}</ul></dd>"
        f"<dt>Score combination permitted</dt><dd>"
        f"{'yes' if comparison.score_combination_permitted else 'no'}</dd>"
        f"<dt>Limitations</dt><dd><ul>{limitations}</ul></dd>"
        "</dl></div>"
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


def render_content_understanding_html(view: ContentUnderstandingView) -> str:
    """Render all structured content-understanding fields without a verdict."""

    context = view.reader_context
    questions = "\n".join(
        f"<li>{_esc(item)}</li>" for item in context.questions
    ) or "<li>None provided.</li>"
    references = _unique_refs(
        (
            *view.completion_refs,
            *view.evidence.artifact_refs,
            *(ref for item in view.observations for ref in item.evidence_refs),
            *(ref for item in view.reflection_prompts for ref in item.evidence_refs),
        )
    )
    body = (
        "<h1>Understand this content</h1>"
        f"<p>{_esc(NO_DECISION_NOTICE)}</p>{_boundary_notes()}"
        "<h2>Submitted content</h2>"
        f'<div class="submitted">{_esc(view.evidence.text)}</div>'
        "<h2>Your questions and context</h2>"
        f'<p class="note">{_esc(CONTEXT_NOTICE)}</p><dl>'
        f"<dt>Purpose</dt><dd>{_esc(context.purpose)}</dd>"
        f"<dt>Known context</dt><dd>{_esc(context.known_context or 'Not provided.')}</dd>"
        f"<dt>Questions</dt><dd><ul>{questions}</ul></dd></dl>"
        "<h2>What each instrument recorded separately</h2>"
        + "\n".join(_instrument_section(item) for item in view.evidence.measurements)
        + "<h2>Comparison, disagreement, abstention, uncertainty, and limitations</h2>"
        + _comparison_section(view.evidence.comparison)
        + _observation_cards(view.observations)
        + "<h2>Questions for closer inspection</h2><ul>"
        + "\n".join(
            f"<li>{_esc(item.question)}</li>" for item in view.reflection_prompts
        )
        + "</ul><h2>Ways to continue understanding</h2>"
        "<p>CTRT does not rank or select among these paths:</p><ul>"
        + "\n".join(f"<li>{_esc(item)}</li>" for item in view.inspection_paths)
        + "</ul><h2>Interpretation boundary</h2><ul>"
        + "\n".join(f"<li>{_esc(item)}</li>" for item in view.notices)
        + "</ul><details><summary>Immutable evidence references</summary>"
        "<table><thead><tr><th>Role</th><th>Artifact ID</th><th>Hash</th></tr>"
        f"</thead><tbody>{_reference_rows(references)}</tbody></table></details>"
        "<footer>"
        f"<p>Understanding contract: <code>{_esc(view.understanding_version)}</code></p>"
        f"<p>Interface contract: <code>{_esc(LOCAL_CONTENT_UNDERSTANDING_WEB_VERSION)}</code></p>"
        f"<p>Experiment run: <code>{_esc(view.experiment_run_id)}</code></p>"
        f'<p><a href="{FORM_PATH}">Inspect another content item</a></p></footer>'
    )
    return _page(title="Understand this content", body=body)


@dataclass(frozen=True, slots=True)
class WebRequest:
    """One decoded local HTTP request, independent of a socket."""

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        return next(
            (value for key, value in self.headers.items() if key.lower() == lowered),
            None,
        )


@dataclass(frozen=True, slots=True)
class WebResponse:
    """One HTML response with fixed browser protections."""

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
    return _page(
        title=title,
        body=(
            f"<h1>{_esc(title)}</h1><p>{_esc(detail)}</p>"
            f'<p><a href="{FORM_PATH}">Return to the form</a></p>'
        ),
    )


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


def _parse_questions(raw: str, errors: list[str]) -> tuple[str, ...]:
    questions = tuple(line.strip() for line in raw.split("\n") if line.strip())
    if len(questions) > MAX_QUESTIONS:
        errors.append(f"At most {MAX_QUESTIONS} questions may be submitted.")
        return ()
    if len(questions) != len(set(questions)):
        errors.append("Each question must be different from the others.")
        return ()
    if any(not item.endswith("?") for item in questions):
        errors.append("Every question must end with a question mark.")
        return ()
    return questions


def _run_token() -> str:
    return f"web-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class ContentUnderstandingWebApp:
    """Stateless local request handler with immutable configuration only."""

    workspace: Path = DEFAULT_WORKSPACE
    candidate_registry_path: Path = DEFAULT_CANDIDATE_REGISTRY
    method_registry_path: Path = DEFAULT_METHOD_REGISTRY

    def handle(self, request: WebRequest) -> WebResponse:
        if request.method not in ALLOWED_METHODS:
            return WebResponse(
                status=405,
                body=_message_page(
                    title="Method not allowed",
                    detail="This local surface accepts only GET and POST.",
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
            return WebResponse(status=200, body=render_content_form_html())
        return self._handle_submission(request)

    def _handle_submission(self, request: WebRequest) -> WebResponse:
        if len(request.body) > MAX_REQUEST_BYTES:
            return WebResponse(
                status=413,
                body=_message_page(
                    title="Submission too large",
                    detail=f"The request exceeds {MAX_REQUEST_BYTES} bytes.",
                ),
            )
        content_type = (request.header("Content-Type") or "").split(";", 1)[0].strip()
        if content_type != FORM_CONTENT_TYPE:
            return WebResponse(
                status=415,
                body=_message_page(
                    title="Unsupported media type",
                    detail="Submit the browser form as URL-encoded data.",
                ),
            )
        try:
            decoded = request.body.decode("utf-8", errors="strict")
            values = parse_qs(
                decoded,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=MAX_FORM_FIELDS,
                encoding="utf-8",
                errors="strict",
            )
        except (UnicodeDecodeError, ValueError) as exc:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Malformed submission",
                    detail=f"The form could not be decoded: {exc}",
                ),
            )
        errors: list[str] = []
        content = _bounded_field(
            values, "content", MAX_CONTENT_CHARACTERS, errors
        )
        purpose = _bounded_field(
            values, "purpose", MAX_PURPOSE_CHARACTERS, errors
        )
        known_context = _bounded_field(
            values, "known_context", MAX_CONTEXT_CHARACTERS, errors
        )
        questions_raw = _bounded_field(
            values, "questions", MAX_QUESTIONS_CHARACTERS, errors
        )
        questions = _parse_questions(questions_raw, errors)
        if not content.strip():
            errors.append("Content to inspect is required.")
        if not purpose.strip():
            errors.append("A purpose is required.")
        form = UnderstandingFormInput(
            content=content,
            purpose=purpose,
            known_context=known_context,
            questions=questions_raw,
        )
        if errors:
            return WebResponse(
                status=422,
                body=render_content_form_html(form=form, errors=tuple(errors)),
            )
        try:
            result = run_local_content_understanding(
                LocalContentUnderstandingRequest(
                    content_text=content,
                    context=ReaderProvidedContext(
                        purpose=purpose,
                        known_context=known_context or None,
                        questions=questions,
                    ),
                    workspace=self.workspace,
                    run_token=_run_token(),
                    started_at=datetime.now(UTC),
                    candidate_registry_path=self.candidate_registry_path,
                    method_registry_path=self.method_registry_path,
                )
            )
        except (LocalContentUnderstandingError, OSError, RuntimeError, ValueError) as exc:
            return WebResponse(
                status=422,
                body=render_content_form_html(form=form, errors=(str(exc),)),
            )
        return WebResponse(
            status=200,
            body=render_content_understanding_html(result.understanding_view),
        )


def validate_loopback_host(host: str) -> str:
    """Accept only a literal loopback address before any bind occurs."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ContentUnderstandingWebError(
            "host must be a literal loopback IP address"
        ) from exc
    if not address.is_loopback:
        raise ContentUnderstandingWebError("host must be loopback only")
    return str(address)


def local_url(host: str, port: int) -> str:
    validated = validate_loopback_host(host)
    display_host = f"[{validated}]" if ":" in validated else validated
    return f"http://{display_host}:{port}/"


def _handler_for(app: ContentUnderstandingWebApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str, *, include_body: bool = True) -> None:
            path = self.path.split("?", 1)[0]
            body = b""
            if method == "POST":
                length_value = self.headers.get("Content-Length")
                if length_value is None:
                    response = WebResponse(
                        status=411,
                        body=_message_page(
                            title="Length required",
                            detail="POST requires a Content-Length header.",
                        ),
                    )
                    self._write(response, include_body=include_body)
                    return
                try:
                    length = int(length_value)
                except ValueError:
                    length = -1
                if length < 0:
                    response = WebResponse(
                        status=400,
                        body=_message_page(
                            title="Malformed submission",
                            detail="Content-Length must be a non-negative integer.",
                        ),
                    )
                    self._write(response, include_body=include_body)
                    return
                if length > MAX_REQUEST_BYTES:
                    response = WebResponse(
                        status=413,
                        body=_message_page(
                            title="Submission too large",
                            detail=f"The request exceeds {MAX_REQUEST_BYTES} bytes.",
                        ),
                    )
                    self._write(response, include_body=include_body)
                    return
                body = self.rfile.read(length)
            response = app.handle(
                WebRequest(
                    method=method,
                    path=path,
                    headers={key: value for key, value in self.headers.items()},
                    body=body,
                )
            )
            self._write(response, include_body=include_body)

        def _write(self, response: WebResponse, *, include_body: bool) -> None:
            encoded = response.encoded_body()
            self.send_response(response.status)
            for key, value in response.headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if include_body:
                self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve("HEAD", include_body=False)

        def do_PUT(self) -> None:  # noqa: N802
            self._serve("PUT")

        def do_DELETE(self) -> None:  # noqa: N802
            self._serve("DELETE")

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write("content-understanding-web: " + (format % args) + "\n")

    return Handler


def build_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    app: ContentUnderstandingWebApp | None = None,
) -> ThreadingHTTPServer:
    """Build, but do not start, a loopback-only local server."""

    validated = validate_loopback_host(host)
    if not 0 <= port <= 65_535:
        raise ContentUnderstandingWebError("port must be between 0 and 65535")
    active_app = app if app is not None else ContentUnderstandingWebApp()
    return ThreadingHTTPServer((validated, port), _handler_for(active_app))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.content_understanding_web",
        description="Serve the local synthetic Understand this content form.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--candidate-registry", type=Path, default=DEFAULT_CANDIDATE_REGISTRY
    )
    parser.add_argument(
        "--method-registry", type=Path, default=DEFAULT_METHOD_REGISTRY
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Start the loopback-only browser surface until interrupted."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        app = ContentUnderstandingWebApp(
            workspace=arguments.workspace,
            candidate_registry_path=arguments.candidate_registry,
            method_registry_path=arguments.method_registry,
        )
        server = build_server(host=arguments.host, port=arguments.port, app=app)
    except (ContentUnderstandingWebError, OSError, ValueError) as exc:
        parser.exit(2, f"content understanding web failed: {exc}\n")
    actual_port = int(server.server_address[1])
    sys.stdout.write(f"Local content understanding: {local_url(arguments.host, actual_port)}\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALLOWED_METHODS",
    "CONTENT_SECURITY_POLICY",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_WORKSPACE",
    "LOCAL_CONTENT_UNDERSTANDING_WEB_VERSION",
    "MAX_CONTENT_CHARACTERS",
    "MAX_FORM_FIELDS",
    "MAX_QUESTIONS",
    "MAX_REQUEST_BYTES",
    "ContentUnderstandingWebApp",
    "ContentUnderstandingWebError",
    "UnderstandingFormInput",
    "WebRequest",
    "WebResponse",
    "build_server",
    "local_url",
    "main",
    "render_content_form_html",
    "render_content_understanding_html",
    "validate_loopback_host",
]
