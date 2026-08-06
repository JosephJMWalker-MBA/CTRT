from __future__ import annotations

import html
import re
import threading
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from ctrt.local_browser_launcher import (
    CONTENT_SECURITY_POLICY,
    LauncherApp,
    LauncherRequest,
    LocalBrowserLauncherError,
    LocalBrowserWorkspace,
    build_workspace,
    local_url,
    render_launcher_html,
    start_child_servers,
    stop_child_servers,
    validate_loopback_host,
)


def _visible_text(body: str) -> str:
    without_style = re.sub(r"<style>.*?</style>", " ", body, flags=re.DOTALL)
    return re.sub(
        r"\s+",
        " ",
        html.unescape(re.sub(r"<[^>]+>", " ", without_style)),
    ).strip()


def test_landing_page_presents_two_distinct_neutral_doors() -> None:
    body = render_launcher_html(
        creator_url="http://127.0.0.1:9101/",
        understanding_url="http://127.0.0.1:9102/",
    )
    text = _visible_text(body)

    assert "CTRT local browser workspace" in text
    assert "Check before I publish" in text
    assert "Understand this content" in text
    assert "launcher does not choose for you" in text
    assert "not forms, reader or creator context, run identities" in text
    assert 'href="http://127.0.0.1:9101/"' in body
    assert 'href="http://127.0.0.1:9102/"' in body
    assert "<form" not in body
    assert "<script" not in body.lower()
    assert "https://" not in body
    assert "//cdn" not in body
    assert "<img" not in body.lower()
    assert "@import" not in body
    assert "url(" not in body


def test_landing_renderer_escapes_urls() -> None:
    body = render_launcher_html(
        creator_url='http://127.0.0.1:1/" onmouseover="alert(1)',
        understanding_url="http://127.0.0.1:2/<script>",
    )

    assert 'onmouseover="alert(1)' not in body
    assert "&quot; onmouseover=&quot;alert(1)" in body
    assert "&lt;script&gt;" in body
    assert "<script>" not in body


def test_launcher_app_is_get_only_and_one_path() -> None:
    app = LauncherApp(
        creator_url="http://127.0.0.1:9101/",
        understanding_url="http://127.0.0.1:9102/",
    )

    success = app.handle(LauncherRequest(method="GET", path="/"))
    assert success.status == 200
    headers = dict(success.headers)
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert headers["X-Content-Type-Options"] == "nosniff"

    missing = app.handle(LauncherRequest(method="GET", path="/other"))
    assert missing.status == 404

    unsupported = app.handle(LauncherRequest(method="POST", path="/"))
    assert unsupported.status == 405
    assert dict(unsupported.headers)["Allow"] == "GET"


def test_loopback_and_port_validation_fail_closed(tmp_path: Path) -> None:
    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("::1") == "::1"
    assert local_url("127.0.0.1", 8764) == "http://127.0.0.1:8764/"
    assert local_url("::1", 8764) == "http://[::1]:8764/"

    for host in ("0.0.0.0", "192.168.1.20", "localhost", "example.com"):
        with pytest.raises(LocalBrowserLauncherError):
            validate_loopback_host(host)

    for port, creator_port, understanding_port in (
        (-1, 0, 0),
        (65_536, 0, 0),
        (0, -1, 0),
        (0, 0, 65_536),
    ):
        with pytest.raises(LocalBrowserLauncherError):
            build_workspace(
                host="127.0.0.1",
                port=port,
                creator_port=creator_port,
                understanding_port=understanding_port,
                workspace_root=tmp_path,
            )


def test_workspace_binds_three_distinct_servers_and_separate_roots(
    tmp_path: Path,
) -> None:
    workspace = build_workspace(
        host="127.0.0.1",
        port=0,
        creator_port=0,
        understanding_port=0,
        workspace_root=tmp_path / "workspace",
    )
    try:
        assert workspace.host == "127.0.0.1"
        assert workspace.landing_url != workspace.creator_url
        assert workspace.landing_url != workspace.understanding_url
        assert workspace.creator_url != workspace.understanding_url
        assert workspace.creator_workspace == tmp_path / "workspace" / "creator-preflight"
        assert (
            workspace.understanding_workspace
            == tmp_path / "workspace" / "content-understanding"
        )
        assert workspace.creator_workspace != workspace.understanding_workspace
    finally:
        workspace.landing_server.server_close()
        workspace.creator_server.server_close()
        workspace.understanding_server.server_close()


@contextmanager
def _running_workspace(tmp_path: Path) -> Iterator[LocalBrowserWorkspace]:
    workspace = build_workspace(
        host="127.0.0.1",
        port=0,
        creator_port=0,
        understanding_port=0,
        workspace_root=tmp_path / "workspace",
    )
    child_threads = start_child_servers(workspace)
    landing_thread = threading.Thread(
        target=workspace.landing_server.serve_forever,
        name="ctrt-launcher-test",
        daemon=True,
    )
    landing_thread.start()
    try:
        yield workspace
    finally:
        workspace.landing_server.shutdown()
        landing_thread.join(timeout=5)
        workspace.landing_server.server_close()
        stop_child_servers(workspace, child_threads)


def _post(url: str, values: dict[str, str]) -> str:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def test_real_launcher_links_to_both_unchanged_forms(tmp_path: Path) -> None:
    with _running_workspace(tmp_path) as workspace:
        with urllib.request.urlopen(workspace.landing_url, timeout=5) as response:
            landing = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
        with urllib.request.urlopen(workspace.creator_url, timeout=5) as response:
            creator = response.read().decode("utf-8")
        with urllib.request.urlopen(workspace.understanding_url, timeout=5) as response:
            understanding = response.read().decode("utf-8")

        assert workspace.creator_url in landing
        assert workspace.understanding_url in landing
        assert "Check before I publish" in creator
        assert 'name="draft"' in creator
        assert 'name="intent"' in creator
        assert "Understand this content" in understanding
        assert 'name="content"' in understanding
        assert 'name="purpose"' in understanding
        assert 'name="draft"' not in understanding
        assert 'name="content"' not in creator


def test_real_submissions_write_only_to_their_own_workspace(tmp_path: Path) -> None:
    with _running_workspace(tmp_path) as workspace:
        creator_body = _post(
            workspace.creator_url,
            {
                "draft": "The opening is good and the ending is bad.",
                "intent": "Describe a mixed reaction.",
                "audience": "Project collaborators",
                "concerns": "The contrast may be too sharp.",
            },
        )
        understanding_body = _post(
            workspace.understanding_url,
            {
                "content": "The opening is good and the ending is bad.",
                "purpose": "Understand the contrast.",
                "known_context": "It came from a project discussion.",
                "questions": "What surrounding context should be checked?",
            },
        )

        assert "Check before I publish" in creator_body
        assert "Understand this content" in understanding_body
        assert tuple(workspace.creator_workspace.rglob("blobs/sha256/*"))
        assert tuple(workspace.understanding_workspace.rglob("blobs/sha256/*"))
        assert not tuple(
            workspace.creator_workspace.rglob("*content-understanding*")
        )
        assert not tuple(
            workspace.understanding_workspace.rglob("*creator-preflight*")
        )


def test_child_server_threads_stop_cleanly(tmp_path: Path) -> None:
    workspace = build_workspace(
        host="127.0.0.1",
        port=0,
        creator_port=0,
        understanding_port=0,
        workspace_root=tmp_path,
    )
    threads = start_child_servers(workspace)
    try:
        assert all(thread.is_alive() for thread in threads)
    finally:
        workspace.landing_server.server_close()
        stop_child_servers(workspace, threads)
    assert all(not thread.is_alive() for thread in threads)


def test_module_exports_only_launcher_surface() -> None:
    import ctrt.local_browser_launcher as module

    assert module.__all__ == [
        "ALLOWED_METHODS",
        "CONTENT_SECURITY_POLICY",
        "DEFAULT_HOST",
        "DEFAULT_PORT",
        "DEFAULT_WORKSPACE",
        "LOCAL_BROWSER_LAUNCHER_VERSION",
        "LauncherApp",
        "LauncherRequest",
        "LauncherResponse",
        "LocalBrowserLauncherError",
        "LocalBrowserWorkspace",
        "build_landing_server",
        "build_workspace",
        "local_url",
        "main",
        "render_launcher_html",
        "start_child_servers",
        "stop_child_servers",
        "validate_loopback_host",
    ]
