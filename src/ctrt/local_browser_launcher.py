"""Launch CTRT's two local browser product doors without merging them."""

from __future__ import annotations

import argparse
import html
import ipaddress
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ctrt.content_understanding_web import (
    DEFAULT_PORT as CONTENT_UNDERSTANDING_PORT,
    ContentUnderstandingWebApp,
    build_server as build_content_understanding_server,
    local_url as content_understanding_url,
)
from ctrt.creator_preflight_web import (
    DEFAULT_PORT as CREATOR_PREFLIGHT_PORT,
    CreatorPreflightWebApp,
    build_server as build_creator_preflight_server,
    local_url as creator_preflight_url,
)

LOCAL_BROWSER_LAUNCHER_VERSION = "ctrt-local-browser-launcher@0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8764
DEFAULT_WORKSPACE = Path(".ctrt") / "local-browser-workspace"

HOME_PATH = "/"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
ALLOWED_METHODS = ("GET",)
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'unsafe-inline'; "
    "base-uri 'none'; frame-ancestors 'none'"
)

SYNTHETIC_NOTICE = (
    "Both doors are local synthetic demonstrations. Their fixture analyzers are "
    "not real-world meaning, tone, safety, quality, or publishing instruments."
)
SEPARATION_NOTICE = (
    "The two doors share constitutional infrastructure but not forms, reader or "
    "creator context, run identities, artifact stores, or decisions."
)
LOCAL_NOTICE = (
    "All three servers bind to one literal loopback address. Loopback is not "
    "authentication, and submitted text is stored unencrypted on this machine."
)

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0 auto;
  padding: 2rem 1rem 4rem;
  max-width: 46rem;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.55;
}
h1 { font-size: 1.6rem; margin: 0 0 .5rem; }
h2 { font-size: 1.1rem; margin: 0 0 .35rem; }
p { margin: .4rem 0; }
.note, .door {
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: .8rem;
  margin: .8rem 0;
}
.doors { display: grid; gap: 1rem; margin-top: 1.5rem; }
a {
  display: inline-block;
  margin-top: .55rem;
  padding: .45rem .75rem;
  border: 1px solid currentColor;
  border-radius: 4px;
  color: inherit;
  text-decoration: none;
}
code { font-size: .85rem; word-break: break-all; }
footer { margin-top: 2.5rem; font-size: .875rem; opacity: .85; }
"""


class LocalBrowserLauncherError(ValueError):
    """Raised when the bounded local launcher cannot be configured."""


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _page(*, title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n<style>{_STYLE}</style>\n"
        f"</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_launcher_html(*, creator_url: str, understanding_url: str) -> str:
    """Render a neutral landing page linking the two independent browser doors."""

    body = (
        "<h1>CTRT local browser workspace</h1>"
        "<p>Choose the task you are performing. The launcher does not choose for you.</p>"
        f'<p class="note">{_esc(SYNTHETIC_NOTICE)}</p>'
        f'<p class="note">{_esc(SEPARATION_NOTICE)}</p>'
        f'<p class="note">{_esc(LOCAL_NOTICE)}</p>'
        '<div class="doors">'
        '<section class="door">'
        "<h2>Check before I publish</h2>"
        "<p>Submit your own draft and creator-provided context for reflection before "
        "you decide whether to publish.</p>"
        f'<a href="{_esc(creator_url)}">Open creator preflight</a>'
        "</section>"
        '<section class="door">'
        "<h2>Understand this content</h2>"
        "<p>Submit one content item plus your purpose, known context, and questions "
        "for content-directed inspection.</p>"
        f'<a href="{_esc(understanding_url)}">Open content understanding</a>'
        "</section>"
        "</div>"
        "<footer>"
        f"<p>Launcher contract: <code>{_esc(LOCAL_BROWSER_LAUNCHER_VERSION)}</code></p>"
        "</footer>"
    )
    return _page(title="CTRT local browser workspace", body=body)


@dataclass(frozen=True, slots=True)
class LauncherRequest:
    """One decoded landing-page request, independent of a socket."""

    method: str
    path: str


@dataclass(frozen=True, slots=True)
class LauncherResponse:
    """One protected landing-page response."""

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
    return _page(title=title, body=f"<h1>{_esc(title)}</h1><p>{_esc(detail)}</p>")


@dataclass(frozen=True, slots=True)
class LauncherApp:
    """Stateless landing-page router with immutable child URLs."""

    creator_url: str
    understanding_url: str

    def handle(self, request: LauncherRequest) -> LauncherResponse:
        if request.method not in ALLOWED_METHODS:
            return LauncherResponse(
                status=405,
                body=_message_page(
                    title="Method not allowed",
                    detail="The launcher landing page accepts GET only.",
                ),
                extra_headers=(("Allow", ", ".join(ALLOWED_METHODS)),),
            )
        if request.path != HOME_PATH:
            return LauncherResponse(
                status=404,
                body=_message_page(
                    title="Not found",
                    detail="The launcher serves exactly one landing page.",
                ),
            )
        return LauncherResponse(
            status=200,
            body=render_launcher_html(
                creator_url=self.creator_url,
                understanding_url=self.understanding_url,
            ),
        )


def validate_loopback_host(host: str) -> str:
    """Accept only a literal loopback address before any server is built."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise LocalBrowserLauncherError(
            "host must be a literal loopback IP address"
        ) from exc
    if not address.is_loopback:
        raise LocalBrowserLauncherError("host must be loopback only")
    return str(address)


def _validate_port(port: int, name: str) -> int:
    if not 0 <= port <= 65_535:
        raise LocalBrowserLauncherError(f"{name} must be between 0 and 65535")
    return port


def local_url(host: str, port: int) -> str:
    """Render one validated loopback URL."""

    validated = validate_loopback_host(host)
    display_host = f"[{validated}]" if ":" in validated else validated
    return f"http://{display_host}:{port}/"


def _handler_for(app: LauncherApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str, *, include_body: bool = True) -> None:
            response = app.handle(
                LauncherRequest(method=method, path=self.path.split("?", 1)[0])
            )
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

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve("GET", include_body=False)

        def do_POST(self) -> None:  # noqa: N802
            self._serve("POST")

        def do_PUT(self) -> None:  # noqa: N802
            self._serve("PUT")

        def do_DELETE(self) -> None:  # noqa: N802
            self._serve("DELETE")

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write("local-browser-launcher: " + (format % args) + "\n")

    return Handler


def build_landing_server(
    *,
    host: str,
    port: int,
    app: LauncherApp,
) -> ThreadingHTTPServer:
    """Build, but do not start, the neutral landing-page server."""

    validated = validate_loopback_host(host)
    _validate_port(port, "launcher port")
    return ThreadingHTTPServer((validated, port), _handler_for(app))


def _server_port(server: ThreadingHTTPServer) -> int:
    address = server.server_address
    if not isinstance(address, tuple) or len(address) < 2:
        raise LocalBrowserLauncherError("server did not expose an IP port")
    return int(address[1])


@dataclass(frozen=True, slots=True)
class LocalBrowserWorkspace:
    """Three bound loopback servers with two deliberately separate workspaces."""

    host: str
    workspace_root: Path
    landing_server: ThreadingHTTPServer
    creator_server: ThreadingHTTPServer
    understanding_server: ThreadingHTTPServer
    landing_url: str
    creator_url: str
    understanding_url: str

    @property
    def creator_workspace(self) -> Path:
        return self.workspace_root / "creator-preflight"

    @property
    def understanding_workspace(self) -> Path:
        return self.workspace_root / "content-understanding"


def build_workspace(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    creator_port: int = CREATOR_PREFLIGHT_PORT,
    understanding_port: int = CONTENT_UNDERSTANDING_PORT,
    workspace_root: Path = DEFAULT_WORKSPACE,
) -> LocalBrowserWorkspace:
    """Bind all three servers while preserving each product door unchanged."""

    validated = validate_loopback_host(host)
    _validate_port(port, "launcher port")
    _validate_port(creator_port, "creator-preflight port")
    _validate_port(understanding_port, "content-understanding port")

    creator_server: ThreadingHTTPServer | None = None
    understanding_server: ThreadingHTTPServer | None = None
    landing_server: ThreadingHTTPServer | None = None
    try:
        creator_server = build_creator_preflight_server(
            host=validated,
            port=creator_port,
            app=CreatorPreflightWebApp(
                workspace=workspace_root / "creator-preflight"
            ),
        )
        creator_url = creator_preflight_url(
            validated, _server_port(creator_server)
        )
        understanding_server = build_content_understanding_server(
            host=validated,
            port=understanding_port,
            app=ContentUnderstandingWebApp(
                workspace=workspace_root / "content-understanding"
            ),
        )
        understanding_url = content_understanding_url(
            validated, _server_port(understanding_server)
        )
        landing_server = build_landing_server(
            host=validated,
            port=port,
            app=LauncherApp(
                creator_url=creator_url,
                understanding_url=understanding_url,
            ),
        )
        landing_url = local_url(validated, _server_port(landing_server))
    except Exception:
        for server in (landing_server, understanding_server, creator_server):
            if server is not None:
                server.server_close()
        raise

    return LocalBrowserWorkspace(
        host=validated,
        workspace_root=workspace_root,
        landing_server=landing_server,
        creator_server=creator_server,
        understanding_server=understanding_server,
        landing_url=landing_url,
        creator_url=creator_url,
        understanding_url=understanding_url,
    )


def start_child_servers(
    workspace: LocalBrowserWorkspace,
) -> tuple[threading.Thread, threading.Thread]:
    """Start the two existing product-door servers in background threads."""

    threads = (
        threading.Thread(
            target=workspace.creator_server.serve_forever,
            name="ctrt-creator-preflight-web",
            daemon=True,
        ),
        threading.Thread(
            target=workspace.understanding_server.serve_forever,
            name="ctrt-content-understanding-web",
            daemon=True,
        ),
    )
    for thread in threads:
        thread.start()
    return threads


def stop_child_servers(
    workspace: LocalBrowserWorkspace,
    threads: Sequence[threading.Thread],
) -> None:
    """Stop and close both child servers after the launcher exits."""

    workspace.creator_server.shutdown()
    workspace.understanding_server.shutdown()
    for thread in threads:
        thread.join(timeout=5)
    workspace.creator_server.server_close()
    workspace.understanding_server.server_close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ctrt.local_browser_launcher",
        description="Launch CTRT's two separate local synthetic browser doors.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--creator-port", type=int, default=CREATOR_PREFLIGHT_PORT
    )
    parser.add_argument(
        "--understanding-port", type=int, default=CONTENT_UNDERSTANDING_PORT
    )
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Serve the launcher in front of both unchanged local browser apps."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        workspace = build_workspace(
            host=arguments.host,
            port=arguments.port,
            creator_port=arguments.creator_port,
            understanding_port=arguments.understanding_port,
            workspace_root=arguments.workspace,
        )
    except (LocalBrowserLauncherError, OSError, ValueError) as exc:
        parser.exit(2, f"local browser launcher failed: {exc}\n")

    threads = start_child_servers(workspace)
    sys.stdout.write(f"CTRT local workspace: {workspace.landing_url}\n")
    sys.stdout.write(f"Creator preflight: {workspace.creator_url}\n")
    sys.stdout.write(f"Content understanding: {workspace.understanding_url}\n")
    sys.stdout.flush()
    try:
        workspace.landing_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        workspace.landing_server.server_close()
        stop_child_servers(workspace, threads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
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
