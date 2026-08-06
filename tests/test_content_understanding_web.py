from __future__ import annotations

import html
import re
import threading
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ctrt.content_understanding import (
    CONTENT_INSPECTION_PATHS,
    CONTENT_UNDERSTANDING_NOTICES,
    ReaderProvidedContext,
    _unique_refs,
)
from ctrt.content_understanding_local import (
    LocalContentUnderstandingRequest,
    run_local_content_understanding,
)
from ctrt.content_understanding_web import (
    CONTENT_SECURITY_POLICY,
    MAX_CONTENT_CHARACTERS,
    MAX_QUESTIONS,
    MAX_REQUEST_BYTES,
    ContentUnderstandingWebApp,
    ContentUnderstandingWebError,
    WebRequest,
    WebResponse,
    build_server,
    local_url,
    render_content_form_html,
    render_content_understanding_html,
    validate_loopback_host,
)
from ctrt.creator_preflight_local import (
    ABSTENTION_CONTROL_TEXT,
    DISAGREEMENT_CONTROL_TEXT,
)

DISAGREEING_CONTENT = "This plan is good, but the delay feels bad."
AGREEING_CONTENT = "The opening is good and the ending is good."
NO_SIGNAL_CONTENT = "A statement without the fixture vocabulary."

FORBIDDEN_PATTERNS = (
    r"overall score",
    r"overall sentiment",
    r"overall tone",
    r"risk score",
    r"\bverdict:",
    r"\brecommendation:",
    r"we recommend",
    r"safe / unsafe",
    r"safe content",
    r"unsafe content",
    r"should be blocked",
    r"should be restricted",
    r"viewer profile",
    r"child profile",
    r"parent profile",
    r"production-ready",
)


def _form_body(
    *,
    content: str = DISAGREEING_CONTENT,
    purpose: str = "Understand the contrast before discussing it.",
    known_context: str = "It was shared during a project discussion.",
    questions: str = "What source context should be checked?",
) -> bytes:
    return urllib.parse.urlencode(
        {
            "content": content,
            "purpose": purpose,
            "known_context": known_context,
            "questions": questions,
        }
    ).encode("utf-8")


def _app(tmp_path: Path) -> ContentUnderstandingWebApp:
    return ContentUnderstandingWebApp(workspace=tmp_path / "web-runs")


def _post(
    app: ContentUnderstandingWebApp,
    *,
    body: bytes | None = None,
    content_type: str = "application/x-www-form-urlencoded",
    path: str = "/",
) -> WebResponse:
    headers: Mapping[str, str] = {"Content-Type": content_type}
    return app.handle(
        WebRequest(
            method="POST",
            path=path,
            headers=headers,
            body=_form_body() if body is None else body,
        )
    )


def _visible_text(body: str) -> str:
    without_style = re.sub(r"<style>.*?</style>", " ", body, flags=re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_style)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _assert_no_verdict_language(body: str) -> None:
    lowered = _visible_text(body).lower()
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, lowered) is None, pattern


def _classes(body: str) -> set[str]:
    return set(re.findall(r'class="([^"]+)"', body))


def test_get_renders_bounded_form_and_protective_headers(tmp_path: Path) -> None:
    response = _app(tmp_path).handle(WebRequest(method="GET", path="/"))

    assert response.status == 200
    headers = dict(response.headers)
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert headers["X-Content-Type-Options"] == "nosniff"

    body = response.body
    assert 'name="content"' in body
    assert 'name="purpose"' in body
    assert 'name="known_context"' in body
    assert 'name="questions"' in body
    for disallowed in ("viewer", "child", "parent", "risk", "restriction"):
        assert f'name="{disallowed}' not in body
    assert "local synthetic demonstration" in body
    assert "loopback only" in body
    assert "Agreement is not approval." in body
    _assert_no_verdict_language(body)


def test_pages_use_no_script_or_external_resource(tmp_path: Path) -> None:
    pages = (
        _app(tmp_path).handle(WebRequest(method="GET", path="/")).body,
        _post(_app(tmp_path)).body,
    )
    for body in pages:
        lowered = body.lower()
        assert "<script" not in lowered
        assert "https://" not in lowered
        assert "//cdn" not in lowered
        assert "<img" not in lowered
        assert "@import" not in lowered
        assert "url(" not in lowered


def test_successful_post_executes_real_local_path_and_hides_controls(
    tmp_path: Path,
) -> None:
    response = _post(_app(tmp_path))

    assert response.status == 200
    body = response.body
    assert DISAGREEING_CONTENT in body
    assert "extraction:" in body
    assert "content-item:" not in body
    assert DISAGREEMENT_CONTROL_TEXT not in body
    assert ABSTENTION_CONTROL_TEXT not in body
    assert "control-disagreement" not in body
    assert "control-abstention" not in body
    assert tuple((tmp_path / "web-runs").rglob("blobs/sha256/*"))
    _assert_no_verdict_language(body)


def test_reader_context_is_visible_but_labeled_non_evidentiary(tmp_path: Path) -> None:
    body = _post(_app(tmp_path)).body

    assert "Reader-provided purpose, context, and questions are not verified evidence." in body
    assert "Understand the contrast before discussing it." in body
    assert "It was shared during a project discussion." in body
    assert "What source context should be checked?" in body
    assert "never written into canonical evidence" in body


def test_every_structured_view_element_is_preserved(tmp_path: Path) -> None:
    result = run_local_content_understanding(
        LocalContentUnderstandingRequest(
            content_text=DISAGREEING_CONTENT,
            context=ReaderProvidedContext(
                purpose="Inspect the contrast.",
                known_context="The source is incomplete.",
                questions=("What is missing?", "Who is speaking?"),
            ),
            workspace=tmp_path / "direct-runs",
            run_token="webstruct01",
            started_at=datetime(2026, 8, 5, 21, 0, tzinfo=UTC),
        )
    )
    view = result.understanding_view
    visible = _visible_text(render_content_understanding_html(view))

    assert view.evidence.text in visible
    assert view.reader_context.purpose in visible
    assert view.reader_context.known_context in visible
    for question in view.reader_context.questions:
        assert question in visible
    for observation in view.observations:
        assert observation.text in visible
    for prompt in view.reflection_prompts:
        assert prompt.question in visible
    for path in view.inspection_paths:
        assert path in visible
    for notice in view.notices:
        assert notice in visible
    references = _unique_refs(
        (
            *view.completion_refs,
            *view.evidence.artifact_refs,
            *(ref for item in view.observations for ref in item.evidence_refs),
            *(ref for item in view.reflection_prompts for ref in item.evidence_refs),
        )
    )
    for reference in references:
        assert reference.role in visible
        assert reference.artifact_id in visible
        assert reference.artifact_hash in visible


def test_disagreement_and_abstention_remain_separate_and_neutral(tmp_path: Path) -> None:
    disagreement = _visible_text(_post(_app(tmp_path)).body)
    abstention = _visible_text(
        _post(
            _app(tmp_path),
            body=_form_body(content=NO_SIGNAL_CONTENT),
        ).body
    )

    assert "strong-disagreement" in disagreement
    assert "Synthetic analyzers emitted opposite valence signs." in disagreement
    assert "Score combination permitted no" in disagreement
    assert "did not emit a measurement" in abstention
    assert "Combined result withheld yes" in abstention
    assert "Abstention is not proof that no meaningful signal exists." in abstention


def test_outcome_does_not_change_presentation_classes(tmp_path: Path) -> None:
    disagreeing = _post(_app(tmp_path)).body
    agreeing = _post(
        _app(tmp_path),
        body=_form_body(content=AGREEING_CONTENT),
    ).body
    abstaining = _post(
        _app(tmp_path),
        body=_form_body(content=NO_SIGNAL_CONTENT),
    ).body

    assert _classes(disagreeing) == _classes(agreeing) == _classes(abstaining)
    assert "The instruments agreed on this measured dimension" in agreeing
    _assert_no_verdict_language(agreeing)


def test_user_supplied_html_is_escaped_in_form_and_result(tmp_path: Path) -> None:
    hostile = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    body = _post(
        _app(tmp_path),
        body=_form_body(
            content=hostile + " good",
            purpose=hostile,
            known_context=hostile,
            questions="What does <b>this</b> mean?",
        ),
    ).body

    assert hostile not in body
    assert "&lt;script&gt;" in body
    assert "&lt;img" in body
    assert "&lt;b&gt;this&lt;/b&gt;" in body
    assert "<script>alert" not in body
    assert "<img src=x" not in body


def test_invalid_and_oversized_submissions_fail_cleanly(tmp_path: Path) -> None:
    app = _app(tmp_path)

    malformed = _post(app, body=b"not-a-form-field")
    assert malformed.status == 400

    wrong_type = _post(app, content_type="application/json")
    assert wrong_type.status == 415

    too_large = _post(app, body=b"x" * (MAX_REQUEST_BYTES + 1))
    assert too_large.status == 413

    empty = _post(app, body=_form_body(content=" ", purpose=" "))
    assert empty.status == 422
    assert "Content to inspect is required." in empty.body
    assert "A purpose is required." in empty.body

    long_content = _post(
        app,
        body=_form_body(content="x" * (MAX_CONTENT_CHARACTERS + 1)),
    )
    assert long_content.status == 422
    assert "character limit" in long_content.body

    questions = "\n".join(f"Question {index}?" for index in range(MAX_QUESTIONS + 1))
    too_many_questions = _post(app, body=_form_body(questions=questions))
    assert too_many_questions.status == 422
    assert "questions may be submitted" in too_many_questions.body

    invalid_question = _post(app, body=_form_body(questions="This is not a question"))
    assert invalid_question.status == 422
    assert "question mark" in invalid_question.body


def test_routing_and_methods_are_bounded(tmp_path: Path) -> None:
    app = _app(tmp_path)

    missing = app.handle(WebRequest(method="GET", path="/other"))
    assert missing.status == 404

    unsupported = app.handle(WebRequest(method="PUT", path="/"))
    assert unsupported.status == 405
    assert dict(unsupported.headers)["Allow"] == "GET, POST"


def test_loopback_validation_rejects_hostnames_and_non_loopback() -> None:
    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("::1") == "::1"
    assert local_url("127.0.0.1", 8766) == "http://127.0.0.1:8766/"
    assert local_url("::1", 8766) == "http://[::1]:8766/"

    for host in ("0.0.0.0", "192.168.1.10", "localhost", "example.com"):
        with pytest.raises(ContentUnderstandingWebError):
            validate_loopback_host(host)


def _running_server(
    tmp_path: Path,
) -> Iterator[tuple[str, object]]:
    server = build_server(
        host="127.0.0.1",
        port=0,
        app=_app(tmp_path),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(server.server_address[1])
        yield local_url("127.0.0.1", port), server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_loopback_server_serves_form(tmp_path: Path) -> None:
    server_context = _running_server(tmp_path)
    url, _server = next(server_context)
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
            assert "Understand this content" in body
    finally:
        with pytest.raises(StopIteration):
            next(server_context)


def test_fixed_paths_and_notices_are_preserved() -> None:
    assert len(CONTENT_INSPECTION_PATHS) == 4
    assert len(CONTENT_UNDERSTANDING_NOTICES) == 5
    form = render_content_form_html()
    assert "CTRT helps inspect submitted content." in form


def test_module_exports_only_bounded_browser_surface() -> None:
    import ctrt.content_understanding_web as module

    assert module.__all__ == [
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
