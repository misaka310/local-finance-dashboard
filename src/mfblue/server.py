from __future__ import annotations

import argparse
import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .api_routes import handle_get, handle_patch, handle_post
from .config import load_config
from .db import db, init_db
from .paths import project_path

FRONTEND_DIR = project_path("frontend")




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

    def do_GET(self):  # noqa: N802
        handle_get(self)

    def do_POST(self):  # noqa: N802
        handle_post(self)

    def do_PATCH(self):  # noqa: N802
        handle_patch(self)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            file_path = FRONTEND_DIR / "index.html"
        else:
            clean = path.lstrip("/")
            file_path = (FRONTEND_DIR / clean).resolve()
            if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        raw = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def bind_server(host: str, base_port: int, max_tries: int = 100) -> tuple[ThreadingHTTPServer, int]:
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--max-port-tries", type=int, default=100)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config()
    port = int(cfg["app"].get("ui_port", 8765))

    with db() as conn:
        init_db(conn)

    server, selected_port = bind_server(args.host, port, max_tries=args.max_port_tries)
    url = f"http://{args.host}:{selected_port}"

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
