"""Loopback-only blinded surface for collecting human-reference annotations.

This module renders HTML and translates HTTP. Every substantive operation is
delegated unchanged to the merged collection contract in
:mod:`ctrt.human_reference_annotation`: assignment creation and resumption,
append-only response persistence, correction through supersession, completion,
and receipt verification. It creates no second collection lifecycle.

The surface is blinded by construction. It has no import, field, route, or
template capable of carrying a candidate identity, candidate output, candidate
characterization, evaluation protocol, evaluation result, or any majority,
consensus, gold, or expected label. It runs neither synthesis nor evaluation,
and it shows an annotator nothing about any other annotator.

A pseudonymous annotator identifier is a local label. It is not authentication
and not identity verification.
"""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs

from ctrt.artifact_store import (
    ArtifactNotFoundError,
    FileSystemArtifactStore,
    StoredArtifactRef,
)
from ctrt.human_reference_annotation import (
    DEFAULT_CORPUS,
    DEFAULT_PROTOCOL,
    AnnotationPacket,
    AnnotationResponse,
    AnnotationSession,
    AnnotatorAssignment,
    AssignmentCompletion,
    CollectionCounts,
    open_assignment,
    persist_collection_inputs,
    verify_collection,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    AbstentionReason,
    AnnotationProtocol,
    ContextSufficiency,
    EvaluationCorpus,
    HumanReferenceError,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    SupportingSpan,
    ValenceLabel,
    load_annotation_protocol,
    load_evaluation_corpus,
    validate_annotator_id,
)
from ctrt.serialization import serialize_artifact

ANNOTATION_WEB_VERSION = "ctrt-human-reference-annotation-web@0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
DEFAULT_WORKSPACE = Path(".ctrt") / "human-reference"

MAX_REQUEST_BYTES = 65_536
MAX_FORM_FIELDS = 16
MAX_RATIONALE_CHARACTERS = 4_000
MAX_REASON_CHARACTERS = 500
MAX_SPAN_CHARACTERS = 200
MAX_SPANS = 8

FORM_PATH = "/"
ANNOTATE_PATH = "/annotate"
CORRECT_PATH = "/correct"
COMPLETE_PATH = "/complete"
RECEIPT_PATH = "/receipt"
FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
ALLOWED_METHODS = ("GET", "POST")
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

BLINDED_NOTICE = (
    "This study is blinded. You are not being shown any instrument, model, or "
    "software output, and no answer is expected of you."
)
LOCAL_ONLY_NOTICE = (
    "This server is bound to loopback only. It has no accounts, authentication, "
    "encryption, remote storage, analytics, or monitoring, and it is not "
    "production software. Anyone able to run code on this machine may be able to "
    "reach it. Your responses are written to local disk unencrypted."
)
PSEUDONYM_NOTICE = (
    "Your annotator ID is a local pseudonymous label chosen by whoever set up this "
    "session. It is not a login, not authentication, and not identity "
    "verification. CTRT stores no mapping from this label to a person."
)
INDEPENDENT_NOTICE = (
    "Record your own reading. You will not see any other annotator's responses, "
    "and disagreement between annotators is a result this study preserves rather "
    "than an error to avoid."
)
ABSTENTION_NOTICE = (
    "Choosing 'cannot determine responsibly' is a valid and expected outcome for "
    "some items. Do not guess in order to avoid leaving an item unanswered."
)
CERTAINTY_NOTICE = (
    "Your certainty is a statement about you, not a measurement of the text."
)
APPEND_ONLY_NOTICE = (
    "A recorded response is never edited or deleted. A correction is stored as a "
    "new record that preserves and names the original."
)

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0 auto;
  padding: 1.5rem 1rem 4rem;
  max-width: 46rem;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.55;
}
h1 { font-size: 1.5rem; margin: 0 0 0.5rem; }
h2 { font-size: 1.15rem; margin: 2rem 0 0.5rem; }
p, li { margin: 0.4rem 0; }
fieldset {
  border: 1px solid currentColor;
  border-radius: 4px;
  margin: 1.25rem 0 0;
  padding: 0.75rem 1rem 1rem;
}
legend { font-weight: 600; padding: 0 0.35rem; }
label { display: block; margin: 0.3rem 0; }
input[type="text"], textarea {
  width: 100%;
  padding: 0.5rem;
  font: inherit;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  color: inherit;
}
textarea { min-height: 4rem; resize: vertical; }
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
.note, .item, .errors {
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 0.6rem 0.8rem;
  margin: 0.75rem 0;
}
.item { white-space: pre-wrap; word-break: break-word; }
.hint { font-size: 0.875rem; opacity: 0.85; margin: 0.15rem 0 0.4rem; }
dl { margin: 0.4rem 0; }
dt { font-weight: 600; margin-top: 0.4rem; }
dd { margin: 0 0 0 1rem; }
code { font-size: 0.85rem; word-break: break-all; }
footer { margin-top: 3rem; font-size: 0.875rem; opacity: 0.85; }
"""


class AnnotationWebError(ValueError):
    """Raised when a local annotation request cannot be served as specified."""


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
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def _notices(*values: str) -> str:
    return "\n".join(f'<p class="note">{_esc(item)}</p>' for item in values)


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
            f"<h1>{_esc(title)}</h1>\n"
            f"<p>{_esc(detail)}</p>\n"
            f'<p><a href="{FORM_PATH}">Return to your assignment</a></p>\n'
        ),
    )


def _radio_group(
    *,
    name: str,
    legend: str,
    hint: str,
    options: Sequence[tuple[str, str]],
    selected: str | None = None,
    required: bool = True,
) -> str:
    rows = "\n".join(
        "<label>"
        f'<input type="radio" name="{_esc(name)}" value="{_esc(value)}"'
        f'{" required" if required else ""}'
        f'{" checked" if selected == value else ""}> {_esc(display)}'
        "</label>"
        for value, display in options
    )
    hint_html = f'<p class="hint">{_esc(hint)}</p>\n' if hint else ""
    return (
        "<fieldset>\n"
        f"<legend>{_esc(legend)}</legend>\n"
        f"{hint_html}"
        f"{rows}\n"
        "</fieldset>\n"
    )


def _valence_options() -> tuple[tuple[str, str], ...]:
    return tuple(
        (label.value, label.value.replace("_", " ")) for label in ValenceLabel
    )


def render_progress_html(
    *,
    annotator_id: str,
    counts: CollectionCounts,
    answered: Sequence[str],
    remaining: Sequence[str],
    total: int,
    completed: bool,
) -> str:
    """Render the annotator's own progress. Never any other annotator's work."""

    body = (
        "<h1>Your annotation assignment</h1>\n"
        f'{_notices(BLINDED_NOTICE, INDEPENDENT_NOTICE, PSEUDONYM_NOTICE, LOCAL_ONLY_NOTICE)}\n'
        f"<p>Annotator: <code>{_esc(annotator_id)}</code></p>\n"
        "<h2>Progress</h2>\n"
        "<dl>\n"
        f"<dt>Items in your assignment</dt><dd>{total}</dd>\n"
        f"<dt>Answered with a judgement</dt><dd>{counts.answered_with_valence}</dd>\n"
        f"<dt>Explicitly abstained</dt><dd>{counts.abstained}</dd>\n"
        f"<dt>Not yet answered</dt><dd>{counts.unanswered}</dd>\n"
        f"<dt>Corrections preserved</dt><dd>{counts.superseded_records}</dd>\n"
        "</dl>\n"
        f'<p class="hint">{_esc(counts.notes)}</p>\n'
        f'<p class="hint">Not yet answered is a different state from an explicit '
        f"abstention. {_esc(APPEND_ONLY_NOTICE)}</p>\n"
    )
    if remaining:
        body += (
            f'<p><a href="{ANNOTATE_PATH}">Continue with the next unanswered item'
            "</a></p>\n"
        )
    else:
        body += (
            "<p>Every assigned item now has a recorded response.</p>\n"
            f'<form method="post" action="{COMPLETE_PATH}">\n'
            "<button type=\"submit\">Mark this assignment complete</button>\n"
            "</form>\n"
        )
    if completed:
        body += f'<p><a href="{RECEIPT_PATH}">View your completion receipt</a></p>\n'
    if answered:
        body += (
            "<h2>Recorded items</h2>\n"
            '<p class="hint">You may record a correction. The original is always '
            "kept.</p>\n<ul>\n"
            + "\n".join(
                f'<li><code>{_esc(item)}</code> '
                f'<a href="{CORRECT_PATH}?item={_esc(item)}">record a correction</a>'
                "</li>"
                for item in answered
            )
            + "\n</ul>\n"
        )
    body += (
        "<footer>\n"
        f"<p>Interface contract: <code>{_esc(ANNOTATION_WEB_VERSION)}</code></p>\n"
        "</footer>\n"
    )
    return _page(title="Your annotation assignment", body=body)


def render_item_html(
    *,
    packet: AnnotationPacket,
    action: str,
    heading: str,
    previous: AnnotationResponse | None = None,
    errors: Sequence[str] = (),
) -> str:
    """Render one item and the exact response scale from the frozen protocol."""

    error_block = ""
    if errors:
        items = "\n".join(f"<li>{_esc(item)}</li>" for item in errors)
        error_block = (
            f'<div class="errors">\n<h2>This response was not recorded</h2>\n'
            f"<ul>\n{items}\n</ul>\n</div>\n"
        )
    correction_block = ""
    if previous is not None:
        correction_block = (
            "<fieldset>\n<legend>Reason for this correction</legend>\n"
            f'<p class="hint">Your earlier response '
            f"(<code>{_esc(previous.valence_label.value)}</code>) is preserved and "
            'will remain readable.</p>\n'
            '<input type="text" name="supersession_reason" required '
            'aria-label="Reason for this correction">\n'
            "</fieldset>\n"
        )
    body = (
        f"<h1>{_esc(heading)}</h1>\n"
        f"{_notices(BLINDED_NOTICE, ABSTENTION_NOTICE)}\n"
        f"<p>Item {packet.position + 1} of {packet.total_items} "
        f"(<code>{_esc(packet.item_id)}</code>)</p>\n"
        f"{error_block}"
        f'<div class="item">{_esc(packet.text)}</div>\n'
        f"<p>{_esc(packet.task_statement)}</p>\n"
        "<ul>\n"
        + "\n".join(f"<li>{_esc(line)}</li>" for line in packet.instructions)
        + "\n</ul>\n"
        f'<form method="post" action="{_esc(action)}">\n'
        f'<input type="hidden" name="item_id" value="{_esc(packet.item_id)}">\n'
        f"{correction_block}"
        + _radio_group(
            name="valence_label",
            legend="How favorable or unfavorable is the language in this passage?",
            hint="Judge only the language present. There is no expected answer.",
            options=_valence_options(),
        )
        + _radio_group(
            name="abstention_reason",
            legend="If you cannot determine this responsibly, why?",
            hint="Required only when you choose 'cannot determine responsibly'.",
            options=tuple(
                (item.value, item.value.replace("_", " ")) for item in AbstentionReason
            ),
            required=False,
        )
        + _radio_group(
            name="context_sufficiency",
            legend="Was the shown text enough context to answer responsibly?",
            hint="Recorded separately from your judgement and from ambiguity.",
            options=tuple(
                (item.value, item.value) for item in ContextSufficiency
            ),
        )
        + _radio_group(
            name="perceived_ambiguity",
            legend="How open to more than one reading did this passage seem?",
            hint="Recorded separately from context sufficiency.",
            options=tuple((item.value, item.value) for item in PerceivedAmbiguity),
        )
        + _radio_group(
            name="self_reported_certainty",
            legend="How settled does your judgement feel? (optional)",
            hint=CERTAINTY_NOTICE,
            options=tuple(
                (item.value, item.value) for item in SelfReportedCertainty
            ),
            required=False,
        )
        + "<fieldset>\n<legend>Rationale (optional)</legend>\n"
        '<p class="hint">What in the passage did you respond to?</p>\n'
        '<textarea name="rationale" rows="3" aria-label="Rationale"></textarea>\n'
        "</fieldset>\n"
        "<fieldset>\n<legend>Supporting spans (optional)</legend>\n"
        '<p class="hint">One span per line as start-end character offsets, for '
        'example 0-12. Offsets must fall inside the passage above.</p>\n'
        '<textarea name="supporting_spans" rows="3" '
        'aria-label="Supporting spans"></textarea>\n'
        "</fieldset>\n"
        "<button type=\"submit\">Record this response</button>\n"
        "</form>\n"
        f'<p class="hint">{_esc(APPEND_ONLY_NOTICE)}</p>\n'
        f'<p><a href="{FORM_PATH}">Back to your assignment</a></p>\n'
    )
    return _page(title=heading, body=body)


def render_receipt_html(
    *,
    annotator_id: str,
    counts: CollectionCounts,
    completion_artifact_id: str,
    completion_artifact_hash: str,
    response_count: int,
) -> str:
    """Render the verified completion receipt for this annotator only."""

    body = (
        "<h1>Assignment complete</h1>\n"
        f"{_notices(BLINDED_NOTICE, INDEPENDENT_NOTICE)}\n"
        f"<p>Annotator: <code>{_esc(annotator_id)}</code></p>\n"
        "<dl>\n"
        f"<dt>Answered with a judgement</dt><dd>{counts.answered_with_valence}</dd>\n"
        f"<dt>Explicitly abstained</dt><dd>{counts.abstained}</dd>\n"
        f"<dt>Not yet answered</dt><dd>{counts.unanswered}</dd>\n"
        f"<dt>Corrections preserved</dt><dd>{counts.superseded_records}</dd>\n"
        f"<dt>Verified responses</dt><dd>{response_count}</dd>\n"
        "</dl>\n"
        f'<p class="hint">{_esc(counts.notes)}</p>\n'
        "<h2>Immutable receipt</h2>\n"
        f"<p><code>{_esc(completion_artifact_id)}</code></p>\n"
        f"<p><code>{_esc(completion_artifact_hash)}</code></p>\n"
        '<p class="hint">Give this receipt identifier to whoever is running the '
        "study. Nothing here is combined with any other annotator's responses by "
        "this surface.</p>\n"
        f'<p><a href="{FORM_PATH}">Back to your assignment</a></p>\n'
    )
    return _page(title="Assignment complete", body=body)


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


def parse_supporting_spans(raw: str, errors: list[str]) -> tuple[SupportingSpan, ...]:
    """Parse ``start-end`` lines into spans, reporting malformed input."""

    spans: list[SupportingSpan] = []
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if len(lines) > MAX_SPANS:
        errors.append(f"At most {MAX_SPANS} supporting spans may be submitted.")
        return ()
    for line in lines:
        parts = line.split("-")
        if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
            errors.append(
                f"Supporting span {line!r} must be two character offsets, "
                "for example 0-12."
            )
            continue
        start, end = (int(part.strip()) for part in parts)
        try:
            spans.append(SupportingSpan(start=start, end=end))
        except HumanReferenceError as exc:
            errors.append(str(exc))
    return tuple(spans)


@dataclass(frozen=True, slots=True)
class AnnotationWebApp:
    """Stateless blinded surface over one annotator's existing assignment.

    The app holds immutable configuration only. Every response, correction, and
    completion is delegated to the merged collection contract, and each request
    reopens the assignment from append-only storage rather than caching state.
    """

    workspace: Path
    annotator_id: str
    corpus_path: Path = DEFAULT_CORPUS
    protocol_path: Path = DEFAULT_PROTOCOL

    def __post_init__(self) -> None:
        validate_annotator_id(self.annotator_id)

    def _session(self) -> AnnotationSession:
        """Reopen the assignment from append-only storage for one request.

        Collection inputs are not persisted here. ``open_assignment`` stamps a
        fresh ``created_at`` on every call, so re-persisting the assignment on
        each request would attempt to bind a new hash to an append-only artifact
        ID. They are persisted once, on the path that needs their references.
        """

        session, _ = open_assignment(
            workspace=self.workspace,
            annotator_id=self.annotator_id,
            corpus_path=self.corpus_path,
            protocol_path=self.protocol_path,
        )
        return session

    def handle(self, request: WebRequest) -> WebResponse:
        """Route one decoded request to the annotator's own assignment."""

        if request.method not in ALLOWED_METHODS:
            return WebResponse(
                status=405,
                body=_message_page(
                    title="Method not allowed",
                    detail="This surface accepts only GET and POST.",
                ),
                extra_headers=(("Allow", ", ".join(ALLOWED_METHODS)),),
            )
        path, _, query = request.path.partition("?")
        try:
            if request.method == "GET":
                return self._handle_get(path, query)
            return self._handle_post(path, request)
        except HumanReferenceError as exc:
            return WebResponse(
                status=400,
                body=_message_page(title="Request refused", detail=str(exc)),
            )

    def _handle_get(self, path: str, query: str) -> WebResponse:
        session = self._session()
        if path == FORM_PATH:
            return WebResponse(status=200, body=self._progress(session))
        if path == ANNOTATE_PATH:
            packet = session.next_packet()
            if packet is None:
                return WebResponse(status=200, body=self._progress(session))
            return WebResponse(
                status=200,
                body=render_item_html(
                    packet=packet,
                    action=ANNOTATE_PATH,
                    heading="Record your reading",
                ),
            )
        if path == CORRECT_PATH:
            values = parse_qs(query, keep_blank_values=True, max_num_fields=4)
            item_ids = values.get("item", [])
            if len(item_ids) != 1:
                return WebResponse(
                    status=400,
                    body=_message_page(
                        title="Request refused",
                        detail="A correction names exactly one item.",
                    ),
                )
            item_id = item_ids[0]
            previous = session.current_response(item_id)
            if previous is None:
                return WebResponse(
                    status=400,
                    body=_message_page(
                        title="Nothing to correct",
                        detail=(
                            f"Item {item_id} has no recorded response yet, so there "
                            "is nothing to supersede."
                        ),
                    ),
                )
            return WebResponse(
                status=200,
                body=render_item_html(
                    packet=session.packet_for(item_id),
                    action=CORRECT_PATH,
                    heading="Record a correction",
                    previous=previous,
                ),
            )
        if path == RECEIPT_PATH:
            return self._receipt(session)
        return WebResponse(
            status=404,
            body=_message_page(
                title="Not found",
                detail="This surface serves your assignment only.",
            ),
        )

    def _handle_post(self, path: str, request: WebRequest) -> WebResponse:
        if path not in {ANNOTATE_PATH, CORRECT_PATH, COMPLETE_PATH}:
            return WebResponse(
                status=404,
                body=_message_page(
                    title="Not found",
                    detail="This surface serves your assignment only.",
                ),
            )
        if len(request.body) > MAX_REQUEST_BYTES:
            return WebResponse(
                status=413,
                body=_message_page(
                    title="Submission too large",
                    detail=(
                        f"The request body exceeds the {MAX_REQUEST_BYTES}-byte "
                        "limit for this local surface."
                    ),
                ),
            )
        content_type = (request.header("Content-Type") or "").split(";")[0].strip()
        if content_type != FORM_CONTENT_TYPE:
            return WebResponse(
                status=415,
                body=_message_page(
                    title="Unsupported media type",
                    detail=f"This surface accepts only {FORM_CONTENT_TYPE}.",
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

        session = self._session()
        if path == COMPLETE_PATH:
            return self._complete(session)
        return self._record(session, values=values, correcting=path == CORRECT_PATH)

    def _record(
        self,
        session: AnnotationSession,
        *,
        values: Mapping[str, list[str]],
        correcting: bool,
    ) -> WebResponse:
        errors: list[str] = []
        item_id = _bounded_field(values, "item_id", 128, errors)
        if item_id not in session.assignment.item_ids:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Request refused",
                    detail="That item is not part of your assignment.",
                ),
            )

        raw_label = _bounded_field(values, "valence_label", 128, errors)
        try:
            label = ValenceLabel(raw_label)
        except ValueError:
            errors.append("Choose one of the listed response options.")
            label = ABSTENTION_LABEL

        reason: AbstentionReason | None = None
        raw_reason = _bounded_field(values, "abstention_reason", MAX_REASON_CHARACTERS, errors)
        if label is ABSTENTION_LABEL:
            try:
                reason = AbstentionReason(raw_reason)
            except ValueError:
                errors.append(
                    "Choosing 'cannot determine responsibly' requires a reason."
                )
        elif raw_reason:
            errors.append(
                "An abstention reason applies only to 'cannot determine responsibly'."
            )

        sufficiency: ContextSufficiency | None = None
        try:
            sufficiency = ContextSufficiency(
                _bounded_field(values, "context_sufficiency", 64, errors)
            )
        except ValueError:
            errors.append("Choose whether the shown text was enough context.")

        ambiguity: PerceivedAmbiguity | None = None
        try:
            ambiguity = PerceivedAmbiguity(
                _bounded_field(values, "perceived_ambiguity", 64, errors)
            )
        except ValueError:
            errors.append("Choose how open to more than one reading the passage was.")

        certainty: SelfReportedCertainty | None = None
        raw_certainty = _bounded_field(values, "self_reported_certainty", 64, errors)
        if raw_certainty:
            try:
                certainty = SelfReportedCertainty(raw_certainty)
            except ValueError:
                errors.append("Certainty must be one of the listed options.")

        rationale = (
            _bounded_field(values, "rationale", MAX_RATIONALE_CHARACTERS, errors).strip()
            or None
        )
        spans = parse_supporting_spans(
            _bounded_field(values, "supporting_spans", MAX_SPAN_CHARACTERS, errors),
            errors,
        )
        supersession_reason = _bounded_field(
            values, "supersession_reason", MAX_REASON_CHARACTERS, errors
        ).strip()
        if correcting and not supersession_reason:
            errors.append("A correction requires a recorded reason.")

        if errors or sufficiency is None or ambiguity is None:
            previous = session.current_response(item_id) if correcting else None
            return WebResponse(
                status=400,
                body=render_item_html(
                    packet=session.packet_for(item_id),
                    action=CORRECT_PATH if correcting else ANNOTATE_PATH,
                    heading="Record a correction" if correcting else "Record your reading",
                    previous=previous,
                    errors=errors or ("A required response was missing.",),
                ),
            )

        try:
            if correcting:
                session.supersede(
                    item_id=item_id,
                    reason=supersession_reason,
                    valence_label=label,
                    context_sufficiency=sufficiency,
                    perceived_ambiguity=ambiguity,
                    abstention_reason=reason,
                    self_reported_certainty=certainty,
                    rationale=rationale,
                    supporting_spans=spans,
                )
            else:
                session.record(
                    item_id=item_id,
                    valence_label=label,
                    context_sufficiency=sufficiency,
                    perceived_ambiguity=ambiguity,
                    abstention_reason=reason,
                    self_reported_certainty=certainty,
                    rationale=rationale,
                    supporting_spans=spans,
                )
        except HumanReferenceError as exc:
            return WebResponse(
                status=400,
                body=render_item_html(
                    packet=session.packet_for(item_id),
                    action=CORRECT_PATH if correcting else ANNOTATE_PATH,
                    heading="Record a correction" if correcting else "Record your reading",
                    previous=session.current_response(item_id) if correcting else None,
                    errors=(str(exc),),
                ),
            )
        return WebResponse(status=200, body=self._progress(session))

    def _complete(self, session: AnnotationSession) -> WebResponse:
        # Completion is written by ``_receipt`` exactly once and then reread, so
        # marking complete and viewing the receipt are the same idempotent path.
        return self._receipt(session)

    def _receipt(self, session: AnnotationSession) -> WebResponse:
        counts = session.counts()
        if counts.unanswered:
            return WebResponse(
                status=400,
                body=_message_page(
                    title="Not yet complete",
                    detail=(
                        f"{counts.unanswered} assigned items still have no recorded "
                        "response."
                    ),
                ),
            )
        corpus = load_evaluation_corpus(_document(self.corpus_path))
        protocol = load_annotation_protocol(_document(self.protocol_path))
        _, store = open_assignment(
            workspace=self.workspace,
            annotator_id=self.annotator_id,
            corpus_path=self.corpus_path,
            protocol_path=self.protocol_path,
        )
        protocol_ref, corpus_ref, assignment_ref = _persist_inputs_once(
            store, corpus=corpus, protocol=protocol, assignment=session.assignment
        )
        completion, completion_ref = _complete_once(store, session)
        receipt = verify_collection(
            store=store,
            session=session,
            corpus=corpus,
            protocol=protocol,
            completion=completion,
            completion_ref=completion_ref,
            protocol_ref=protocol_ref,
            corpus_ref=corpus_ref,
            assignment_ref=assignment_ref,
        )
        return WebResponse(
            status=200,
            body=render_receipt_html(
                annotator_id=self.annotator_id,
                counts=counts,
                completion_artifact_id=receipt.completion_ref.artifact_id,
                completion_artifact_hash=receipt.completion_ref.artifact_hash,
                response_count=len(receipt.responses),
            ),
        )

    def _progress(self, session: AnnotationSession) -> str:
        counts = session.counts()
        return render_progress_html(
            annotator_id=self.annotator_id,
            counts=counts,
            answered=session.answered_item_ids(),
            remaining=session.unanswered_item_ids(),
            total=len(session.assignment.item_ids),
            completed=counts.unanswered == 0,
        )


def _document(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise AnnotationWebError(f"unable to read {path}") from exc
    if not isinstance(value, Mapping):
        raise AnnotationWebError(f"{path} must contain a JSON object")
    return value


def _persist_inputs_once(
    store: FileSystemArtifactStore,
    *,
    corpus: EvaluationCorpus,
    protocol: AnnotationProtocol,
    assignment: AnnotatorAssignment,
) -> tuple[StoredArtifactRef, StoredArtifactRef, StoredArtifactRef]:
    """Persist collection inputs once, then reuse the first stored assignment.

    ``open_assignment`` stamps a fresh ``created_at`` on every call, so the
    assignment artifact would otherwise bind a new hash to an append-only ID on
    every request. The item order is derived deterministically and reverified by
    ``verify_against``, so the first persisted assignment stays authoritative.
    """

    try:
        stored = store.get(assignment.assignment_id)
    except ArtifactNotFoundError:
        return persist_collection_inputs(
            store, corpus=corpus, protocol=protocol, assignment=assignment
        )
    protocol_ref = store.append(
        serialize_artifact(
            f"{protocol.protocol_id}:{protocol.protocol_version}",
            json.loads(protocol.canonical_payload.decode("utf-8")),
        )
    )
    corpus_ref = store.append(
        serialize_artifact(
            f"{corpus.corpus_id}:{corpus.corpus_version}",
            json.loads(corpus.canonical_payload.decode("utf-8")),
        )
    )
    return (
        protocol_ref,
        corpus_ref,
        StoredArtifactRef(
            artifact_id=stored.artifact_id,
            artifact_hash=stored.artifact_hash,
        ),
    )


def _completion_from_text(text: str) -> AssignmentCompletion:
    """Rebuild a stored completion so a receipt can be reread, not rewritten."""

    document = cast(dict[str, Any], json.loads(text))
    counts = cast(dict[str, Any], document["counts"])
    return AssignmentCompletion(
        completion_id=cast(str, document["completion_id"]),
        collection_version=cast(str, document["collection_version"]),
        assignment_id=cast(str, document["assignment_id"]),
        annotator_id=cast(str, document["annotator_id"]),
        corpus_hash=cast(str, document["corpus_hash"]),
        protocol_hash=cast(str, document["protocol_hash"]),
        item_ids=tuple(cast(list[str], document["item_ids"])),
        response_refs=tuple(
            StoredArtifactRef(
                artifact_id=cast(str, item["artifact_id"]),
                artifact_hash=cast(str, item["artifact_hash"]),
            )
            for item in cast(list[dict[str, Any]], document["response_refs"])
        ),
        counts=CollectionCounts(
            total_items=cast(int, counts["total_items"]),
            answered_with_valence=cast(int, counts["answered_with_valence"]),
            abstained=cast(int, counts["abstained"]),
            unanswered=cast(int, counts["unanswered"]),
            superseded_records=cast(int, counts["superseded_records"]),
            notes=cast(str, counts["notes"]),
        ),
        non_claims=tuple(cast(list[str], document["non_claims"])),
        completed_at=cast(str, document["completed_at"]),
    )


def _complete_once(
    store: FileSystemArtifactStore,
    session: AnnotationSession,
) -> tuple[AssignmentCompletion, StoredArtifactRef]:
    """Write the completion exactly once, then reread it on later views.

    ``AnnotationSession.complete`` stamps a fresh ``completed_at``, so calling it
    twice would try to bind a second hash to an append-only artifact ID. Viewing
    a receipt must not rewrite the record it is reporting.
    """

    completion_id = f"{session.assignment.assignment_id}:completion"
    try:
        stored = store.get(completion_id)
    except ArtifactNotFoundError:
        return session.complete()
    return (
        _completion_from_text(stored.text),
        StoredArtifactRef(
            artifact_id=stored.artifact_id,
            artifact_hash=stored.artifact_hash,
        ),
    )


class _AnnotationRequestHandler(BaseHTTPRequestHandler):
    """Translate loopback HTTP into the pure request/response core and back."""

    server_version = "CTRTHumanReferenceAnnotation/0.1"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def _app(self) -> AnnotationWebApp:
        app = getattr(self.server, "annotation_app", None)
        if not isinstance(app, AnnotationWebApp):
            raise AnnotationWebError("server is missing its annotation app")
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

    def _dispatch(self, method: str, body: bytes) -> None:
        self._respond(
            self._app.handle(
                WebRequest(
                    method=method,
                    path=self.path,
                    headers=dict(self.headers.items()),
                    body=body,
                )
            )
        )

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Serve progress, an item, a correction form, or the receipt."""

        self._dispatch("GET", b"")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Record one response, correction, or completion."""

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._respond(
                WebResponse(
                    status=411,
                    body=_message_page(
                        title="Length required",
                        detail="A form submission must declare its Content-Length.",
                    ),
                )
            )
            return
        try:
            length = int(raw_length)
        except ValueError:
            self._respond(
                WebResponse(
                    status=400,
                    body=_message_page(
                        title="Malformed submission",
                        detail="The declared Content-Length was not an integer.",
                    ),
                )
            )
            return
        if length < 0 or length > MAX_REQUEST_BYTES:
            self.close_connection = True
            self._respond(
                WebResponse(
                    status=413 if length > 0 else 400,
                    body=_message_page(
                        title="Submission too large",
                        detail=(
                            f"The request body exceeds the {MAX_REQUEST_BYTES}-byte "
                            "limit for this local surface."
                        ),
                    ),
                )
            )
            return
        self._dispatch("POST", self.rfile.read(length))

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
        """Keep the annotation surface quiet rather than logging responses."""

        return


class _AnnotationServer(ThreadingHTTPServer):
    """Loopback HTTP server carrying one immutable app configuration."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        app: AnnotationWebApp,
    ) -> None:
        self.annotation_app = app
        super().__init__(server_address, _AnnotationRequestHandler)


def validate_loopback_host(host: str) -> str:
    """Return the host only when it is a validated literal loopback address."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise AnnotationWebError(
            f"host must be a literal loopback address, not {host!r}"
        ) from exc
    if not address.is_loopback:
        raise AnnotationWebError(
            f"host must be a literal loopback address, not {host!r}"
        )
    return host


def build_server(
    *,
    app: AnnotationWebApp,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> _AnnotationServer:
    """Bind a loopback-only server, refusing any externally reachable address."""

    validate_loopback_host(host)
    if not 0 <= port <= 65_535:
        raise AnnotationWebError(f"port must be within 0-65535, not {port}")
    return _AnnotationServer((host, port), app)


def local_url(server: _AnnotationServer) -> str:
    """Return the loopback URL an annotator should open."""

    host, port = server.server_address[0], server.server_address[1]
    text = host.decode("ascii") if isinstance(host, bytes | bytearray) else str(host)
    if ":" in text:
        text = f"[{text}]"
    return f"http://{text}:{port}{FORM_PATH}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.human_reference_annotation_web",
        description=(
            "RESEARCH ONLY. Serve a loopback-only blinded surface for one "
            "annotator's human-reference assignment. No instrument, model, "
            "candidate, expected answer, or other annotator's work is shown."
        ),
    )
    parser.add_argument(
        "--annotator-id",
        required=True,
        help="Pseudonymous local label. Not a login and not identity verification.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="Directory containing one append-only store per annotator.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Literal loopback address to bind. Anything else is refused.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the blinded local annotation surface."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        app = AnnotationWebApp(
            workspace=arguments.workspace,
            annotator_id=arguments.annotator_id,
            corpus_path=arguments.corpus,
            protocol_path=arguments.protocol,
        )
        server = build_server(app=app, host=arguments.host, port=arguments.port)
    except (AnnotationWebError, HumanReferenceError, OSError) as exc:
        parser.exit(2, f"annotation surface failed: {exc}\n")
        return 2
    sys.stdout.write(
        f"CTRT human-reference annotation (research only) at {local_url(server)}\n"
        f"Annotator: {app.annotator_id}\n"
        f"Artifact workspace: {app.workspace}\n"
        "Loopback only, no authentication, responses stored unencrypted on this "
        "machine. Press Ctrl+C to stop.\n"
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
    "ALLOWED_METHODS",
    "ANNOTATION_WEB_VERSION",
    "CONTENT_SECURITY_POLICY",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_WORKSPACE",
    "MAX_REQUEST_BYTES",
    "MAX_SPANS",
    "AnnotationWebApp",
    "AnnotationWebError",
    "WebRequest",
    "WebResponse",
    "build_server",
    "local_url",
    "main",
    "parse_supporting_spans",
    "render_item_html",
    "render_progress_html",
    "render_receipt_html",
    "validate_loopback_host",
]
