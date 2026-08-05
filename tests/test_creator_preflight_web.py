from __future__ import annotations

import html
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ctrt.creator_preflight import (
    CREATOR_CONTROLLED_ACTIONS,
    CREATOR_PREFLIGHT_NOTICES,
    CreatorProvidedContext,
    _unique_refs,
)
from ctrt.creator_preflight_local import (
    ABSTENTION_CONTROL_TEXT,
    DISAGREEMENT_CONTROL_TEXT,
    LocalCreatorPreflightRequest,
    run_local_creator_preflight,
)
from ctrt.creator_preflight_web import (
    CONTENT_SECURITY_POLICY,
    MAX_CONCERNS,
    MAX_DRAFT_CHARACTERS,
    MAX_REQUEST_BYTES,
    CreatorPreflightWebApp,
    CreatorPreflightWebError,
    WebRequest,
    WebResponse,
    build_server,
    local_url,
    main,
    render_creator_form_html,
    render_creator_preflight_html,
    validate_loopback_host,
)

DISAGREEING_DRAFT = "This plan is good, but the delay feels bad."
AGREEING_DRAFT = "The opening is good and the ending is good."
NO_SIGNAL_DRAFT = "A draft without the fixture vocabulary."

# Affirmative labels the browser surface must never introduce. The constitutional
# notices legitimately *deny* several of these, so each pattern is written as the
# affirmative form a verdict-style interface would use.
FORBIDDEN_PATTERNS = (
    r"overall score",
    r"overall sentiment",
    r"overall tone",
    r"aggregate confidence",
    r"confidence score",
    r"\bverdict:",
    r"\brecommendation:",
    r"we recommend",
    r"publish-ready",
    r"ready to publish",
    r"safe to publish",
    r"production-ready",
    r"\bapproved\b",
    r"\bprohibited\b",
    r"safe / unsafe",
    r"suggested rewrite",
    r"rewritten draft",
)


def _form_body(
    *,
    draft: str = DISAGREEING_DRAFT,
    intent: str = "Explain both the promise and the concern.",
    audience: str = "Project collaborators",
    concerns: str = "The contrast may be stronger than intended.",
) -> bytes:
    return urllib.parse.urlencode(
        {
            "draft": draft,
            "intent": intent,
            "audience": audience,
            "concerns": concerns,
        }
    ).encode("utf-8")


def _post(
    app: CreatorPreflightWebApp,
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


def _app(tmp_path: Path) -> CreatorPreflightWebApp:
    return CreatorPreflightWebApp(workspace=tmp_path / "web-runs")


def _visible_text(body: str) -> str:
    """Recover the reader-visible text: drop the stylesheet, tags, and escaping."""

    without_style = re.sub(r"<style>.*?</style>", " ", body, flags=re.DOTALL)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", without_style)))


def _assert_no_verdict_language(body: str) -> None:
    lowered = _visible_text(body).lower()
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, lowered) is None, pattern


def test_get_renders_the_creator_form_and_synthetic_boundary(tmp_path: Path) -> None:
    response = _app(tmp_path).handle(WebRequest(method="GET", path="/"))

    assert response.status == 200
    assert dict(response.headers)["Content-Type"] == "text/html; charset=utf-8"
    assert dict(response.headers)["Cache-Control"] == "no-store"
    assert dict(response.headers)["Content-Security-Policy"] == CONTENT_SECURITY_POLICY

    body = response.body
    assert 'name="draft"' in body
    assert 'name="intent"' in body
    assert 'name="audience"' in body
    assert 'name="concerns"' in body
    assert "CTRT does not decide whether this draft should be published." in body
    assert "local synthetic demonstration" in body
    assert "loopback only" in body
    assert "Agreement between instruments is not approval." in body
    _assert_no_verdict_language(body)


def test_form_requests_no_external_resource_and_no_script(tmp_path: Path) -> None:
    pages = (
        _app(tmp_path).handle(WebRequest(method="GET", path="/")).body,
        _post(_app(tmp_path)).body,
    )
    for body in pages:
        assert "<script" not in body.lower()
        assert "http://" not in body.replace('href="/"', "")
        assert "https://" not in body
        assert "//cdn" not in body
        assert "<img" not in body.lower()
        assert "@import" not in body
        assert "url(" not in body


def test_successful_post_runs_the_real_preflight_and_shows_only_the_draft(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    response = _post(app)

    assert response.status == 200
    body = response.body
    assert DISAGREEING_DRAFT in body

    # The real extraction-backed path ran: an append-only per-run artifact
    # workspace exists and holds content-addressed blobs.
    blobs = tuple((tmp_path / "web-runs").rglob("blobs/sha256/*"))
    assert blobs
    assert "extraction:" in body
    assert "content-item:" not in body
    _assert_no_verdict_language(body)


def test_synthetic_control_text_never_reaches_the_creator_page(
    tmp_path: Path,
) -> None:
    body = _post(_app(tmp_path)).body

    assert DISAGREEMENT_CONTROL_TEXT not in body
    assert ABSTENTION_CONTROL_TEXT not in body
    assert "control-disagreement" not in body
    assert "control-abstention" not in body


def test_creator_context_is_labeled_as_non_evidentiary(tmp_path: Path) -> None:
    body = _post(_app(tmp_path)).body

    assert "Creator-provided context is not verified evidence." in body
    assert "never written into the canonical" in body
    assert "Explain both the promise and the concern." in body
    assert "Project collaborators" in body
    assert "The contrast may be stronger than intended." in body


def test_disagreement_is_preserved_separately_and_without_judgement(
    tmp_path: Path,
) -> None:
    body = _post(_app(tmp_path)).body
    text = _visible_text(body)

    assert "strong-disagreement" in text
    assert "Synthetic analyzers emitted opposite valence signs." in text
    assert "Preserved disagreements" in text
    # Both original instrument records survive beside the comparison.
    assert "synthetic.sentiment.first-signal" in text
    assert "synthetic.sentiment.last-signal" in text
    assert "Score combination permitted no" in text
    # Disagreement is never dressed as a fault. The neutrality notice states this
    # explicitly, and no fault label or alarm glyph is attached to the record.
    assert "Disagreement is not a warning or a failure." in text
    lowered = text.lower()
    for pattern in (
        r"\bwarning:",
        r"\berror:",
        r"\bcaution\b",
        r"invalid draft",
        r"problem detected",
        r"needs attention",
    ):
        assert re.search(pattern, lowered) is None, pattern
    for glyph in ("⚠", "❌", "✅", "✔", "✗"):
        assert glyph not in body


def test_styling_does_not_encode_the_analytical_outcome(tmp_path: Path) -> None:
    disagreeing = _post(_app(tmp_path / "a")).body
    agreeing = _post(_app(tmp_path / "b"), body=_form_body(draft=AGREEING_DRAFT)).body

    classes = tuple(
        frozenset(re.findall(r'class="([^"]+)"', page))
        for page in (disagreeing, agreeing)
    )
    assert classes[0] == classes[1]
    # No colour is used at all, so no status can be rendered as good or bad.
    for page in (disagreeing, agreeing):
        assert "color:" not in page.replace("color-scheme:", "").replace(
            "color: inherit", ""
        )


def test_analyzer_and_comparison_abstention_remain_visible(tmp_path: Path) -> None:
    response = _post(_app(tmp_path), body=_form_body(draft=NO_SIGNAL_DRAFT))
    text = _visible_text(response.body)

    assert response.status == 200
    assert "Abstention withheld a measurement yes" in text
    assert "Comparison withheld a combined result yes" in text
    assert "did not emit a measurement" in text
    assert "no-fixture-token-match" in text or "agreement-abstain" in text
    _assert_no_verdict_language(response.body)


def test_reflection_questions_and_all_neutral_actions_are_rendered(
    tmp_path: Path,
) -> None:
    body = _post(_app(tmp_path)).body
    text = _visible_text(body)

    for action in CREATOR_CONTROLLED_ACTIONS:
        assert action in text
    for notice in CREATOR_PREFLIGHT_NOTICES:
        assert notice in text
    assert "Questions for you" in text
    assert text.count("?") >= 5
    assert "CTRT does not select among these creator-controlled actions" in text


def test_every_structured_view_element_is_preserved(tmp_path: Path) -> None:
    """Nothing the structured view carries may be dropped by the HTML layer."""

    result = run_local_creator_preflight(
        LocalCreatorPreflightRequest(
            draft_text=DISAGREEING_DRAFT,
            context=CreatorProvidedContext(
                intent="Explain both the promise and the concern.",
                intended_audience="Project collaborators",
                concerns=("The contrast may be stronger than intended.",),
            ),
            workspace=tmp_path / "view-runs",
            run_token="webviewtest01",
            started_at=datetime(2026, 8, 5, 16, 0, tzinfo=UTC),
        )
    )
    view = result.preflight_view
    text = _visible_text(render_creator_preflight_html(view))

    assert view.evidence.text in text
    for observation in view.observations:
        assert observation.text in text, observation.observation_id
    for prompt in view.reflection_prompts:
        assert prompt.question in text, prompt.prompt_id
    for action in view.creator_controlled_actions:
        assert action in text
    for notice in view.notices:
        assert notice in text
    for measurement in view.evidence.measurements:
        assert measurement.analyzer_id in text
        for span in measurement.evidence_spans:
            assert span.excerpt in text
    for limitation in view.evidence.comparison.limitations:
        assert limitation in text
    for disagreement in view.evidence.comparison.disagreements:
        assert disagreement.description in text

    references = _unique_refs(
        (
            *view.completion_refs,
            *view.evidence.artifact_refs,
            *(ref for item in view.observations for ref in item.evidence_refs),
            *(ref for item in view.reflection_prompts for ref in item.evidence_refs),
        )
    )
    assert references
    for reference in references:
        assert reference.artifact_id in text
        assert reference.artifact_hash in text


def test_immutable_evidence_references_are_present(tmp_path: Path) -> None:
    body = _post(_app(tmp_path)).body

    assert "<details>" in body
    assert "Immutable evidence references" in body
    for role in (
        "source-artifact",
        "extraction-manifest",
        "extracted-content",
        "session-receipt",
        "eligible-extraction-completion",
        "extraction-bound-completion",
        "experiment-completion",
        "extraction-method-registry",
        "extraction-method-eligibility",
    ):
        assert role in body
    assert body.count("sha256:") >= 9


def test_submitted_html_and_script_text_is_escaped(tmp_path: Path) -> None:
    hostile_draft = "<script>alert('x')</script> and this is good."
    hostile_intent = '"><img src=x onerror=alert(1)>'
    response = _post(
        _app(tmp_path),
        body=_form_body(
            draft=hostile_draft,
            intent=hostile_intent,
            audience="</textarea><b>bold</b>",
            concerns="<i>italic concern</i>",
        ),
    )

    assert response.status == 200
    body = response.body
    # No submitted text may re-enter the document as markup: every angle bracket
    # and quote from the creator is escaped, so no tag or attribute is formed.
    assert "<script" not in body.lower()
    assert "<img" not in body.lower()
    assert "<b>bold</b>" not in body
    assert "<i>italic concern</i>" not in body
    assert "</textarea><b>" not in body
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in body
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in body
    assert "&lt;/textarea&gt;&lt;b&gt;bold&lt;/b&gt;" in body
    assert "&lt;i&gt;italic concern&lt;/i&gt;" in body


def test_escaped_input_is_preserved_when_the_form_is_re_rendered(
    tmp_path: Path,
) -> None:
    response = _post(
        _app(tmp_path),
        body=_form_body(draft="<script>bad</script>", intent=""),
    )

    assert response.status == 400
    assert "<script>" not in response.body
    assert "&lt;script&gt;bad&lt;/script&gt;" in response.body
    assert "This draft was not run" in response.body


def test_oversized_request_body_is_refused(tmp_path: Path) -> None:
    response = _post(_app(tmp_path), body=b"draft=" + b"a" * MAX_REQUEST_BYTES)

    assert response.status == 413
    assert "exceeds" in response.body


def test_oversized_single_field_is_refused_cleanly(tmp_path: Path) -> None:
    response = _post(
        _app(tmp_path),
        body=_form_body(draft="good " * (MAX_DRAFT_CHARACTERS // 2)),
    )

    assert response.status == 400
    assert f"{MAX_DRAFT_CHARACTERS}-character limit" in response.body


def test_too_many_concerns_are_refused(tmp_path: Path) -> None:
    concerns = "\n".join(f"Concern number {index}." for index in range(MAX_CONCERNS + 1))
    response = _post(_app(tmp_path), body=_form_body(concerns=concerns))

    assert response.status == 400
    assert f"At most {MAX_CONCERNS} concerns" in response.body


def test_duplicate_concerns_are_refused(tmp_path: Path) -> None:
    response = _post(_app(tmp_path), body=_form_body(concerns="Same line\nSame line"))

    assert response.status == 400
    assert "Each concern must be different" in response.body


def test_empty_draft_and_empty_intent_fail_closed(tmp_path: Path) -> None:
    blank_draft = _post(_app(tmp_path), body=_form_body(draft="   "))
    blank_intent = _post(_app(tmp_path), body=_form_body(intent="  "))

    assert blank_draft.status == 400
    assert "draft_text" in blank_draft.body
    assert blank_intent.status == 400
    assert "creator intent" in blank_intent.body


def test_malformed_bodies_and_media_types_fail_cleanly(tmp_path: Path) -> None:
    app = _app(tmp_path)

    wrong_type = _post(app, content_type="application/json")
    assert wrong_type.status == 415

    not_utf8 = _post(app, body=b"draft=\xff\xfe")
    assert not_utf8.status == 400

    too_many_fields = _post(
        app,
        body="&".join(f"field{index}=1" for index in range(64)).encode("utf-8"),
    )
    assert too_many_fields.status == 400

    repeated = _post(app, body=b"draft=one&draft=two&intent=x")
    assert repeated.status == 400
    assert "submitted more than once" in repeated.body


def test_unknown_paths_and_unsupported_methods_are_refused(tmp_path: Path) -> None:
    app = _app(tmp_path)

    missing = app.handle(WebRequest(method="GET", path="/other"))
    assert missing.status == 404

    for method in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE"):
        response = app.handle(WebRequest(method=method, path="/"))
        assert response.status == 405, method
        assert dict(response.headers)["Allow"] == "GET, POST"


def test_non_loopback_binding_is_rejected(tmp_path: Path) -> None:
    for host in ("0.0.0.0", "192.168.1.10", "::", "example.com", ""):
        with pytest.raises(CreatorPreflightWebError, match="loopback"):
            validate_loopback_host(host)
        with pytest.raises(CreatorPreflightWebError, match="loopback"):
            build_server(app=_app(tmp_path), host=host, port=0)

    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("::1") == "::1"
    assert validate_loopback_host("localhost") == "localhost"


def test_out_of_range_port_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CreatorPreflightWebError, match="port"):
        build_server(app=_app(tmp_path), host="127.0.0.1", port=70_000)


def test_main_refuses_a_non_loopback_host(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--host", "0.0.0.0", "--port", "0", "--workspace", str(tmp_path)])

    assert excinfo.value.code == 2
    assert "loopback" in capsys.readouterr().err


def test_rendered_form_never_carries_verdict_language() -> None:
    _assert_no_verdict_language(render_creator_form_html())


def test_module_exports_remain_bounded() -> None:
    import ctrt
    import ctrt.creator_preflight_web as web_module

    assert web_module.__all__ == [
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
    # Phase 1B interaction surfaces stay out of the top-level contract package.
    assert not {name for name in ctrt.__all__ if "preflight" in name.lower()}


@pytest.fixture
def running_server(tmp_path: Path) -> Iterator[str]:
    server = build_server(
        app=CreatorPreflightWebApp(workspace=tmp_path / "socket-runs"),
        host="127.0.0.1",
        port=0,
    )
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
        assert response.headers["Content-Type"] == "text/html; charset=utf-8"
        assert response.headers["Cache-Control"] == "no-store"
        assert 'name="draft"' in response.read().decode("utf-8")

    request = urllib.request.Request(  # noqa: S310
        running_server,
        data=_form_body(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        body = response.read().decode("utf-8")
    assert DISAGREEING_DRAFT in body
    assert DISAGREEMENT_CONTROL_TEXT not in body
    _assert_no_verdict_language(body)

    hostile = urllib.request.Request(  # noqa: S310
        running_server,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(hostile, timeout=30)  # noqa: S310
    assert excinfo.value.code == 405
    assert excinfo.value.headers["Allow"] == "GET, POST"
