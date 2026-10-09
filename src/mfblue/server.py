from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .api_routes import handle_get, handle_patch, handle_post
from .config import load_config
from .db import db, init_db
from .paths import project_path
from .static_paths import resolve_static_asset

FRONTEND_DIR = project_path("frontend")
TRUSTED_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def _normalize_loopback_host(host: str) -> str:
    normalized = str(host or "").strip().lower().rstrip(".")
    if normalized not in TRUSTED_LOOPBACK_HOSTS:
        raise ValueError("UI server host must be loopback-only: 127.0.0.1 or localhost")
    return normalized


def _normalized_hostname(hostname: str | None) -> str:
    return str(hostname or "").strip().lower().rstrip(".")


def _authority_is_trusted(authority: str, expected_port: int) -> bool:
    value = str(authority or "").strip()
    if not value:
        return False
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        return False
    return (
        _normalized_hostname(parsed.hostname) in TRUSTED_LOOPBACK_HOSTS
        and port == expected_port
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _origin_is_trusted(origin: str | None, expected_port: int) -> bool:
    value = str(origin or "").strip()
    if not value:
        return True
    try:
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and _normalized_hostname(parsed.hostname) in TRUSTED_LOOPBACK_HOSTS
        and port == expected_port
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "local-finance-dashboard/0.1"

    def log_message(self, fmt: str, *args):  # type: ignore[override]
        print("[server] " + fmt % args)

    def send_json(self, data, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_error_json(
        self,
        message: str,
        status: int = 400,
        *,
        error_code: str | None = None,
        error_stage: str | None = None,
    ) -> None:
        payload: dict[str, object] = {"error": message}
        if error_code:
            payload["error_code"] = error_code
        if error_stage:
            payload["error_stage"] = error_stage
        self.send_json(payload, status=status)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _server_port(self) -> int:
        return int(self.server.server_address[1])

    def _reject_untrusted_host(self) -> bool:
        if _authority_is_trusted(self.headers.get("Host", ""), self._server_port()):
            return False
        self.send_error_json(
            "Untrusted Host header",
            status=HTTPStatus.MISDIRECTED_REQUEST,
            error_code="untrusted_host",
        )
        return True

    def _reject_untrusted_mutation(self) -> bool:
        if self._reject_untrusted_host():
            return True
        if self.headers.get_content_type().lower() != "application/json":
            self.send_error_json(
                "Content-Type must be application/json",
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                error_code="unsupported_content_type",
            )
            return True
        if not _origin_is_trusted(self.headers.get("Origin"), self._server_port()):
            self.send_error_json(
                "Untrusted Origin header",
                status=HTTPStatus.FORBIDDEN,
                error_code="untrusted_origin",
            )
            return True
        return False

    def do_GET(self):  # noqa: N802
        if self._reject_untrusted_host():
            return
        handle_get(self)

    def do_POST(self):  # noqa: N802
        if self._reject_untrusted_mutation():
            return
        handle_post(self)

    def do_PATCH(self):  # noqa: N802
        if self._reject_untrusted_mutation():
            return
        handle_patch(self)

    def serve_static(self, path: str) -> None:
        asset = resolve_static_asset(path, FRONTEND_DIR)
        if asset is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        raw = asset.path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", asset.content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def bind_server(host: str, base_port: int, max_tries: int = 100) -> tuple[ThreadingHTTPServer, int]:
    host = _normalize_loopback_host(host)
    max_tries = max(1, max_tries)
    last_error: OSError | None = None
    for offset in range(max_tries):
        port = base_port + offset
        try:
            return ThreadingHTTPServer((host, port), Handler), port
        except OSError as e:
            last_error = e
            if e.errno in {13, 48, 98, 10013, 10048}:
                continue
            if "Address already in use" in str(e) or "Only one usage" in str(e):
                continue
            raise
    tried_until = base_port + max_tries - 1
    message = f"No free port found between {base_port} and {tried_until}"
    if last_error is not None:
        raise OSError(message) from last_error
    raise OSError(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run mfblue local UI server")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback only: 127.0.0.1 or localhost")
    parser.add_argument("--max-port-tries", type=int, default=100)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config()
    port = int(cfg["app"].get("ui_port", 8765))
    host = _normalize_loopback_host(args.host)

    with db() as conn:
        init_db(conn)

    server, selected_port = bind_server(host, port, max_tries=args.max_port_tries)
    url = f"http://{host}:{selected_port}"

    print(f"UI_URL={url}")
    print(f"Local UI: {url}")
    if selected_port != port:
        print(f"Port {port} was busy. Using {selected_port} instead.")
    print("Stop with Ctrl+C")

    if args.open_browser:
        try:
            webbrowser.open(url, new=2)
        except Exception as e:
            print(f"Failed to open browser automatically: {e}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
