from __future__ import annotations

import ast
import html
import json
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import pytest

from ctrt.artifact_store import FileSystemArtifactStore
from ctrt.human_reference_annotation import (
    DEFAULT_CORPUS,
    DEFAULT_PROTOCOL,
    open_assignment,
)
from ctrt.human_reference_annotation_web import (
    ALLOWED_METHODS,
    ANNOTATION_WEB_VERSION,
    CONTENT_SECURITY_POLICY,
    MAX_REQUEST_BYTES,
    MAX_SPANS,
    AnnotationWebApp,
    AnnotationWebError,
    WebRequest,
    WebResponse,
    build_server,
    local_url,
    main,
    parse_supporting_spans,
    validate_loopback_host,
)
from ctrt.human_reference_protocol import (
    ABSTENTION_LABEL,
    AbstentionReason,
    ContextSufficiency,
    PerceivedAmbiguity,
    SelfReportedCertainty,
    ValenceLabel,
    load_evaluation_corpus,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}

#: Anything an annotator must never be shown or have stored beside them.
BLINDING_LEAKS = (
    "vader",
    "sentimentintensityanalyzer",
    "polarity_scores",
    "compound",
    "analyzer",
    "candidate",
    "characterization",
    "eligible_for_evaluation",
    "majority",
    "consensus",
    "gold",
    "expected label",
    "correct answer",
    "synthesis",
    "concordance",
)


def _app(tmp_path: Path, annotator_id: str = "rater-001") -> AnnotationWebApp:
    return AnnotationWebApp(workspace=tmp_path / "hr", annotator_id=annotator_id)


def _get(app: AnnotationWebApp, path: str) -> WebResponse:
    return app.handle(WebRequest(method="GET", path=path))


def _post(app: AnnotationWebApp, path: str, **fields_: str) -> WebResponse:
    return app.handle(
        WebRequest(
            method="POST",
            path=path,
            headers=FORM_HEADERS,
            body=urllib.parse.urlencode(fields_).encode("utf-8"),
        )
    )


def _next_item(app: AnnotationWebApp) -> tuple[str, WebResponse]:
    response = _get(app, "/annotate")
    match = re.search(r'name="item_id" value="([^"]+)"', response.body)
    assert match is not None
    return match.group(1), response


def _answer(
    app: AnnotationWebApp,
    item_id: str,
    *,
    label: str = "somewhat_favorable",
    **extra: str,
) -> WebResponse:
    payload: dict[str, str] = {
        "item_id": item_id,
        "valence_label": label,
        "context_sufficiency": "sufficient",
        "perceived_ambiguity": "some",
    }
    payload.update(extra)
    return _post(app, "/annotate", **payload)


def _answer_everything(app: AnnotationWebApp) -> None:
    while True:
        response = _get(app, "/annotate")
        match = re.search(r'name="item_id" value="([^"]+)"', response.body)
        if match is None:
            return
        _answer(app, match.group(1))


# --------------------------------------------------------------------------
# Blinding
# --------------------------------------------------------------------------


def test_no_candidate_or_evaluation_module_is_imported() -> None:
    """Structural: the surface cannot reach a candidate or an evaluation."""

    source = (
        REPO_ROOT / "src" / "ctrt" / "human_reference_annotation_web.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        cast(str, node.module)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    for banned in (
        "vader",
        "characterization",
        "candidate_reference",
        "human_reference_synthesis",
        "creator_preflight",
        "content_understanding",
        "synthetic",
    ):
        assert not any(banned in item.lower() for item in imported), banned
    assert "vaderSentiment" not in sys.modules


def test_every_rendered_page_is_blinded(tmp_path: Path) -> None:
    """Behavioral: walk the whole surface and assert no leak on any page."""

    app = _app(tmp_path)
    pages: list[str] = [_get(app, "/").body]

    item_id, item_page = _next_item(app)
    pages.append(item_page.body)
    pages.append(_answer(app, item_id).body)
    pages.append(_get(app, f"/correct?item={item_id}").body)
    pages.append(
        _post(
            app,
            "/correct",
            item_id=item_id,
            supersession_reason="Reread the passage.",
            valence_label="neither_clearly_favorable_nor_unfavorable",
            context_sufficiency="unsure",
            perceived_ambiguity="high",
        ).body
    )
    _answer_everything(app)
    pages.append(_post(app, "/complete").body)
    pages.append(_get(app, "/receipt").body)

    for index, page in enumerate(pages):
        lowered = page.lower()
        for leak in BLINDING_LEAKS:
            assert leak not in lowered, (index, leak)


def test_stored_artifacts_beside_the_annotator_carry_no_candidate_field(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    _answer_everything(app)
    _post(app, "/complete")

    from ctrt.human_reference_protocol import FORBIDDEN_CANDIDATE_KEYS

    store_root = tmp_path / "hr" / "rater-001" / "artifacts"
    stored = b"\n".join(
        path.read_bytes() for path in store_root.rglob("*") if path.is_file()
    )
    keys = {key.decode() for key in re.findall(rb'"([a-z_]+)":', stored)}
    assert not keys & FORBIDDEN_CANDIDATE_KEYS
    assert b"vader" not in stored.lower()


def test_no_cross_annotator_information_is_exposed(tmp_path: Path) -> None:
    workspace = tmp_path / "hr"
    first = AnnotationWebApp(workspace=workspace, annotator_id="rater-001")
    second = AnnotationWebApp(workspace=workspace, annotator_id="rater-002")

    item_id, _ = _next_item(first)
    _answer(first, item_id, label="strongly_favorable", rationale="unmistakable")

    for path in ("/", "/annotate"):
        body = _get(second, path).body
        assert "rater-001" not in body
        assert "unmistakable" not in body
        assert "strongly_favorable" not in body or path == "/annotate"
    # The second annotator's own progress reflects only their own work.
    assert "<dt>Answered with a judgement</dt><dd>0</dd>" in _get(second, "/").body


# --------------------------------------------------------------------------
# One item at a time, exact protocol options
# --------------------------------------------------------------------------


def test_item_page_offers_the_exact_frozen_scale(tmp_path: Path) -> None:
    app = _app(tmp_path)
    _, page = _next_item(app)

    for label in ValenceLabel:
        assert f'value="{label.value}"' in page.body
    for reason in AbstentionReason:
        assert f'value="{reason.value}"' in page.body
    for value in ContextSufficiency:
        assert f'value="{value.value}"' in page.body
    for value in PerceivedAmbiguity:
        assert f'value="{value.value}"' in page.body
    for value in SelfReportedCertainty:
        assert f'value="{value.value}"' in page.body
    assert 'name="rationale"' in page.body
    assert 'name="supporting_spans"' in page.body


def test_one_item_is_shown_at_a_time_and_matches_the_frozen_corpus(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    corpus = load_evaluation_corpus(
        cast(dict[str, Any], json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8")))
    )
    item_id, page = _next_item(app)
    shown = [item.item_id for item in corpus.items if item.item_id in page.body]

    assert shown == [item_id]
    # The passage appears escaped, never as raw markup.
    assert html.escape(corpus.item(item_id).text, quote=True) in page.body


# --------------------------------------------------------------------------
# Delegation to the merged collection contract
# --------------------------------------------------------------------------


def test_responses_are_written_through_the_real_collection_contract(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(
        app,
        item_id,
        label="somewhat_unfavorable",
        self_reported_certainty="high",
        rationale="The qualifier carried the weight.",
        supporting_spans="0-4",
    )

    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    stored = session.current_response(item_id)
    assert stored is not None
    assert stored.valence_label is ValenceLabel.SOMEWHAT_UNFAVORABLE
    assert stored.self_reported_certainty is SelfReportedCertainty.HIGH
    assert stored.rationale == "The qualifier carried the weight."
    assert len(stored.supporting_spans) == 1
    assert stored.supporting_spans[0].start == 0
    assert stored.supporting_spans[0].end == 4
    assert stored.abstained is False


def test_certainty_and_spans_are_reachable_that_the_terminal_path_omits(
    tmp_path: Path,
) -> None:
    """These two contract fields had no operator surface before this one."""

    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(
        app,
        item_id,
        self_reported_certainty="low",
        supporting_spans="1-5\n0-3",
    )

    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    stored = session.current_response(item_id)
    assert stored is not None
    assert stored.self_reported_certainty is SelfReportedCertainty.LOW
    assert len(stored.supporting_spans) == 2


def test_abstention_is_first_class_with_a_preserved_reason(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    response = _answer(
        app,
        item_id,
        label=ABSTENTION_LABEL.value,
        abstention_reason="insufficient_context",
        perceived_ambiguity="high",
        context_sufficiency="insufficient",
    )

    assert response.status == 200
    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    stored = session.current_response(item_id)
    assert stored is not None
    assert stored.abstained is True
    assert stored.abstention_reason is AbstentionReason.INSUFFICIENT_CONTEXT
    assert "<dt>Explicitly abstained</dt><dd>1</dd>" in response.body


def test_abstention_without_a_reason_is_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    response = _answer(app, item_id, label=ABSTENTION_LABEL.value)

    assert response.status == 400
    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    assert session.current_response(item_id) is None


def test_a_judgement_may_not_carry_an_abstention_reason(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    response = _answer(app, item_id, abstention_reason="insufficient_context")

    assert response.status == 400
    assert "applies only to" in response.body


def test_unanswered_stays_distinct_from_explicit_abstention(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(
        app,
        item_id,
        label=ABSTENTION_LABEL.value,
        abstention_reason="ambiguous_between_readings",
    )
    body = _get(app, "/").body

    assert "<dt>Explicitly abstained</dt><dd>1</dd>" in body
    assert "<dt>Answered with a judgement</dt><dd>0</dd>" in body
    assert "<dt>Not yet answered</dt><dd>47</dd>" in body
    assert "different state" in body


# --------------------------------------------------------------------------
# Append-only behavior
# --------------------------------------------------------------------------


def test_recording_twice_is_refused_without_changing_the_stored_response(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(app, item_id, label="strongly_favorable")

    refused = _answer(app, item_id, label="strongly_unfavorable")
    assert refused.status == 400

    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    stored = session.current_response(item_id)
    assert stored is not None
    assert stored.valence_label is ValenceLabel.STRONGLY_FAVORABLE
    assert len(session.responses_for(item_id)) == 1


def test_correction_supersedes_and_preserves_the_original(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(app, item_id, label="strongly_favorable")

    response = _post(
        app,
        "/correct",
        item_id=item_id,
        supersession_reason="Misread the negation.",
        valence_label="somewhat_unfavorable",
        context_sufficiency="sufficient",
        perceived_ambiguity="none",
    )
    assert response.status == 200

    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    chain = session.responses_for(item_id)
    assert len(chain) == 2
    assert chain[0].valence_label is ValenceLabel.STRONGLY_FAVORABLE
    assert chain[1].valence_label is ValenceLabel.SOMEWHAT_UNFAVORABLE
    assert chain[1].supersedes_response_id == chain[0].response_id
    assert chain[1].supersession_reason == "Misread the negation."
    assert "<dt>Corrections preserved</dt><dd>1</dd>" in response.body


def test_correction_requires_a_reason(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(app, item_id)

    response = _post(
        app,
        "/correct",
        item_id=item_id,
        supersession_reason="   ",
        valence_label="neither_clearly_favorable_nor_unfavorable",
        context_sufficiency="sufficient",
        perceived_ambiguity="none",
    )
    assert response.status == 400
    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    assert len(session.responses_for(item_id)) == 1


def test_correcting_an_unanswered_item_is_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)
    remaining = _get(app, "/annotate")
    match = re.search(r'name="item_id" value="([^"]+)"', remaining.body)
    assert match is not None

    response = _get(app, f"/correct?item={match.group(1)}")
    assert response.status == 400
    assert "nothing to supersede" in response.body


def test_progress_and_resumption_come_from_stored_artifacts(tmp_path: Path) -> None:
    app = _app(tmp_path)
    first, _ = _next_item(app)
    _answer(app, first)
    second, _ = _next_item(app)
    _answer(app, second)

    # A brand new app object over the same workspace resumes exactly.
    resumed = _app(tmp_path)
    body = _get(resumed, "/").body
    assert "<dt>Answered with a judgement</dt><dd>2</dd>" in body
    third, _ = _next_item(resumed)
    assert third not in {first, second}


# --------------------------------------------------------------------------
# Completion and receipt
# --------------------------------------------------------------------------


def test_completion_requires_every_item_and_then_verifies(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    _answer(app, item_id)

    early = _post(app, "/complete")
    assert early.status == 400
    assert "still have no recorded response" in early.body

    _answer_everything(app)
    completed = _post(app, "/complete")
    assert completed.status == 200
    assert "Assignment complete" in completed.body
    assert "<dt>Verified responses</dt><dd>48</dd>" in completed.body

    # The receipt identifier is a real stored artifact.
    match = re.search(r"<p><code>(assignment\.[^<]+:completion)</code></p>", completed.body)
    assert match is not None
    store = FileSystemArtifactStore(tmp_path / "hr" / "rater-001" / "artifacts")
    store.get(match.group(1))


def test_receipt_before_completion_is_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)
    response = _get(app, "/receipt")
    assert response.status == 400
    assert "no recorded response" in response.body


def test_repeated_requests_do_not_break_append_only_storage(tmp_path: Path) -> None:
    """Every request reopens the assignment; none may rebind an artifact ID."""

    app = _app(tmp_path)
    for _ in range(5):
        assert _get(app, "/").status == 200
        assert _get(app, "/annotate").status == 200
    _answer_everything(app)
    assert _post(app, "/complete").status == 200
    assert _get(app, "/receipt").status == 200
    assert _get(app, "/receipt").status == 200


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------


def test_submitted_text_is_escaped(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    hostile = '"><script>alert(1)</script>'
    _answer(app, item_id)
    response = _post(
        app,
        "/correct",
        item_id=item_id,
        supersession_reason=hostile,
        valence_label="not_a_real_option",
        context_sufficiency="sufficient",
        perceived_ambiguity="none",
    )

    assert response.status == 400
    assert "<script>" not in response.body
    assert "alert(1)" not in response.body or "&lt;script&gt;" in response.body


def test_stored_item_text_is_escaped_when_rendered(tmp_path: Path) -> None:
    app = _app(tmp_path)
    corpus = load_evaluation_corpus(
        cast(dict[str, Any], json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8")))
    )
    seen = set()
    for _ in range(6):
        item_id, page = _next_item(app)
        seen.add(item_id)
        text = corpus.item(item_id).text
        if "<" in text or "&" in text or '"' in text:
            assert text not in page.body
        _answer(app, item_id)
    assert len(seen) == 6


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0-4", 1), ("0-4\n5-9", 2), ("", 0)],
)
def test_valid_spans_parse(raw: str, expected: int) -> None:
    errors: list[str] = []
    assert len(parse_supporting_spans(raw, errors)) == expected
    assert errors == []


@pytest.mark.parametrize("raw", ["4-0", "abc", "1-2-3", "5-5", "-1-4"])
def test_malformed_spans_are_reported(raw: str) -> None:
    errors: list[str] = []
    parse_supporting_spans(raw, errors)
    assert errors


def test_too_many_spans_are_refused() -> None:
    errors: list[str] = []
    raw = "\n".join(f"{index}-{index + 1}" for index in range(MAX_SPANS + 1))
    assert parse_supporting_spans(raw, errors) == ()
    assert any(str(MAX_SPANS) in item for item in errors)


def test_spans_outside_the_item_text_are_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)
    item_id, _ = _next_item(app)
    response = _answer(app, item_id, supporting_spans="0-9999")

    assert response.status == 400
    session, _ = open_assignment(workspace=tmp_path / "hr", annotator_id="rater-001")
    assert session.current_response(item_id) is None


def test_oversized_and_malformed_requests_fail_cleanly(tmp_path: Path) -> None:
    app = _app(tmp_path)

    oversized = app.handle(
        WebRequest(
            method="POST",
            path="/annotate",
            headers=FORM_HEADERS,
            body=b"x" * (MAX_REQUEST_BYTES + 1),
        )
    )
    assert oversized.status == 413

    wrong_type = app.handle(
        WebRequest(
            method="POST",
            path="/annotate",
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )
    )
    assert wrong_type.status == 415

    not_utf8 = app.handle(
        WebRequest(
            method="POST",
            path="/annotate",
            headers=FORM_HEADERS,
            body=b"item_id=\xff\xfe",
        )
    )
    assert not_utf8.status == 400

    too_many = app.handle(
        WebRequest(
            method="POST",
            path="/annotate",
            headers=FORM_HEADERS,
            body="&".join(f"f{index}=1" for index in range(64)).encode("utf-8"),
        )
    )
    assert too_many.status == 400


def test_an_item_outside_the_assignment_is_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)
    response = _answer(app, "hr-999")
    assert response.status == 400
    assert "not part of your assignment" in response.body


def test_unknown_paths_and_methods_are_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)

    assert _get(app, "/other").status == 404
    assert _post(app, "/other", item_id="x").status == 404
    for method in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE"):
        response = app.handle(WebRequest(method=method, path="/"))
        assert response.status == 405, method
        assert dict(response.headers)["Allow"] == ", ".join(ALLOWED_METHODS)


# --------------------------------------------------------------------------
# Identity, binding, headers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["person@example.com", "Jane Doe", "+15555550123", "../escape", "R1", ""],
)
def test_unsafe_or_identifying_annotator_ids_are_refused(
    tmp_path: Path, value: str
) -> None:
    from ctrt.human_reference_protocol import HumanReferenceError

    with pytest.raises(HumanReferenceError, match="annotator_id"):
        AnnotationWebApp(workspace=tmp_path, annotator_id=value)


def test_no_personal_information_field_exists_on_the_surface(
    tmp_path: Path,
) -> None:
    """Structural: the app carries no field that could hold personal data."""

    names = {item.name for item in fields(AnnotationWebApp)}
    for banned in ("name", "email", "phone", "address", "demographic", "age", "ip"):
        assert banned not in names

    app = _app(tmp_path)
    page = _get(app, "/annotate").body
    for banned in ('name="email"', 'name="full_name"', 'type="password"'):
        assert banned not in page


def test_non_loopback_binding_is_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)
    for host in ("0.0.0.0", "192.168.1.10", "::", "example.com", "localhost", ""):
        with pytest.raises(AnnotationWebError, match="loopback"):
            validate_loopback_host(host)
        with pytest.raises(AnnotationWebError, match="loopback"):
            build_server(app=app, host=host, port=0)

    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("::1") == "::1"


def test_protective_headers_are_present_on_every_response(tmp_path: Path) -> None:
    app = _app(tmp_path)
    for response in (_get(app, "/"), _get(app, "/annotate"), _get(app, "/nope")):
        headers = dict(response.headers)
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
        assert headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["X-Frame-Options"] == "DENY"


def test_pages_load_no_external_resource_and_no_script(tmp_path: Path) -> None:
    app = _app(tmp_path)
    _, item_page = _next_item(app)
    for body in (_get(app, "/").body, item_page.body):
        lowered = body.lower()
        assert "<script" not in lowered
        assert "http://" not in body.replace('href="/"', "")
        assert "https://" not in body
        assert "<img" not in lowered
        assert "@import" not in body
        assert "url(" not in body


def test_notices_state_the_operational_limits(tmp_path: Path) -> None:
    body = _get(_app(tmp_path), "/").body
    assert "not a login" in body
    assert "not authentication" in body
    assert "unencrypted" in body
    assert "loopback only" in body
    assert "blinded" in body.lower()


# --------------------------------------------------------------------------
# Server and CLI
# --------------------------------------------------------------------------


@pytest.fixture
def running_server(tmp_path: Path) -> Iterator[str]:
    server = build_server(app=_app(tmp_path), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield local_url(server)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_bounded_end_to_end_loopback_request(running_server: str) -> None:
    with urllib.request.urlopen(running_server, timeout=30) as response:  # noqa: S310
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"
        body = response.read().decode("utf-8")
    assert "Your annotation assignment" in body
    assert "vader" not in body.lower()

    with urllib.request.urlopen(  # noqa: S310
        running_server.rstrip("/") + "/annotate", timeout=30
    ) as response:
        item_page = response.read().decode("utf-8")
    item_id = re.search(r'name="item_id" value="([^"]+)"', item_page)
    assert item_id is not None

    request = urllib.request.Request(  # noqa: S310
        running_server.rstrip("/") + "/annotate",
        data=urllib.parse.urlencode(
            {
                "item_id": item_id.group(1),
                "valence_label": "somewhat_favorable",
                "context_sufficiency": "sufficient",
                "perceived_ambiguity": "none",
            }
        ).encode("utf-8"),
        headers=FORM_HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        assert "<dt>Answered with a judgement</dt><dd>1</dd>" in response.read().decode()

    hostile = urllib.request.Request(  # noqa: S310
        running_server, data=b"{}", headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(hostile, timeout=30)  # noqa: S310
    assert excinfo.value.code == 405


def test_cli_refuses_a_non_loopback_host(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--annotator-id",
                "rater-001",
                "--workspace",
                str(tmp_path),
                "--host",
                "0.0.0.0",
                "--port",
                "0",
            ]
        )
    assert excinfo.value.code == 2
    assert "loopback" in capsys.readouterr().err


def test_cli_refuses_an_unsafe_annotator_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--annotator-id",
                "person@example.com",
                "--workspace",
                str(tmp_path),
                "--port",
                "0",
            ]
        )
    assert excinfo.value.code == 2
    assert "annotator_id" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_the_surface_is_not_linked_from_the_product_launcher() -> None:
    """A blinded research instrument must not sit beside the product doors."""

    source = (REPO_ROOT / "src" / "ctrt" / "local_browser_launcher.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {
        cast(str, node.module)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("human_reference" in item for item in imported)


def test_no_merged_module_imports_this_surface() -> None:
    for path in (REPO_ROOT / "src" / "ctrt").glob("*.py"):
        if path.name == "human_reference_annotation_web.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            cast(str, node.module)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(
            "human_reference_annotation_web" in item for item in imported
        ), path.name


def test_surface_never_runs_synthesis_or_evaluation(tmp_path: Path) -> None:
    """Behavioral: a full assignment writes no synthesis or evaluation artifact."""

    app = _app(tmp_path)
    _answer_everything(app)
    _post(app, "/complete")

    store_root = tmp_path / "hr" / "rater-001" / "artifacts"
    ids = {
        json.loads(path.read_text(encoding="utf-8"))["artifact_id"]
        for path in (store_root / "ids").rglob("*.json")
    }
    for identifier in ids:
        lowered = identifier.lower()
        for banned in ("synthesis", "evaluation", "candidate", "vader"):
            assert banned not in lowered, identifier
    assert any(":completion" in identifier for identifier in ids)


def test_public_exports_remain_bounded() -> None:
    import ctrt
    import ctrt.human_reference_annotation_web as module

    assert module.__all__ == [
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
    assert ANNOTATION_WEB_VERSION == "ctrt-human-reference-annotation-web@0.1.0"
    assert not [name for name in ctrt.__all__ if "annotation_web" in name.lower()]


def test_the_collection_contract_itself_is_unchanged() -> None:
    """This PR adds a surface; it must not alter the merged collection API."""

    import ctrt.human_reference_annotation as collection

    assert collection.__all__ == [
        "ASSIGNMENT_METHOD",
        "ASSIGNMENT_METHOD_VERSION",
        "COLLECTION_NON_CLAIMS",
        "COLLECTION_VERSION",
        "DEFAULT_CORPUS",
        "DEFAULT_PROTOCOL",
        "AnnotationPacket",
        "AnnotationResponse",
        "AnnotationSession",
        "AnnotatorAssignment",
        "AssignmentCompletion",
        "CollectionCounts",
        "VerifiedCollectionReceipt",
        "assignment_order",
        "main",
        "open_assignment",
        "persist_collection_inputs",
        "render_collection_report_markdown",
        "run_collection_session",
        "verify_collection",
    ]
    assert DEFAULT_PROTOCOL.is_file()
    assert DEFAULT_CORPUS.is_file()
