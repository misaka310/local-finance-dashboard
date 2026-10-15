from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from websocket import (
        WebSocket,
        WebSocketBadStatusException,
        WebSocketTimeoutException,
        create_connection,
    )
except ImportError:  # pragma: no cover - dependency check
    WebSocket = Any  # type: ignore[misc, assignment]
    WebSocketBadStatusException = RuntimeError  # type: ignore[assignment]
    WebSocketTimeoutException = TimeoutError  # type: ignore[assignment]
    create_connection = None


class CodexAppServerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "codex_app_server_error",
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.stage = stage


class CodexAppServerUnavailable(CodexAppServerError):
    pass


@dataclass
class CodexTurnResult:
    result_text: str
    thread_id: str | None
    turn_id: str | None


class CodexAppServerClient:
    def __init__(
        self,
        url: str,
        timeout_seconds: int = 120,
        client_name: str = "local-finance-dashboard",
        client_version: str = "v1",
    ) -> None:
        self.url = url
        self.timeout_seconds = max(5, int(timeout_seconds))
        self.client_name = client_name
        self.client_version = client_version
        self._next_id = 1

    def run_text_turn(self, prompt: str) -> CodexTurnResult:
        ws = self._connect()
        try:
            self._initialize(ws)
            thread_result = self._request(ws, "thread/start", {"ephemeral": True})
            thread_id = self._extract_thread_id(thread_result)
            if not thread_id:
                raise CodexAppServerError(
                    "thread/start response did not include thread id",
                    error_code="protocol_failed",
                    stage="thread/start",
                )

            turn_result = self._request(
                ws,
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                },
            )
            turn_id = self._extract_turn_id(turn_result)
            result_text = self._wait_turn_completed(ws, thread_id=thread_id, turn_id=turn_id)
            return CodexTurnResult(result_text=result_text, thread_id=thread_id, turn_id=turn_id)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _connect(self) -> WebSocket:
        if create_connection is None:
            raise CodexAppServerUnavailable(
                "websocket-client が未インストールです。scripts\\01_setup.ps1 を再実行してください。",
                error_code="dependency_missing",
                stage="websocket",
            )
        try:
            # Codex app-server rejects websocket requests carrying Origin headers.
            ws = create_connection(self.url, timeout=self.timeout_seconds, suppress_origin=True)
            ws.settimeout(min(5, self.timeout_seconds))
            return ws
        except Exception as exc:
            raise self._build_connect_error(exc) from exc

    def _build_connect_error(self, exc: Exception) -> CodexAppServerUnavailable:
        raw = str(exc)
        lower = raw.lower()
        ready_ok, ready_detail = self._check_readyz()

        if (
            "connection refused" in lower
            or "actively refused" in lower
            or "winerror 10061" in lower
            or "errno 111" in lower
            or (ready_ok is False and "timed out" in lower)
        ):
            return CodexAppServerUnavailable(
                f"Codex App Serverが起動していません。readyz={ready_detail}; error={raw}",
                error_code="app_server_not_running",
                stage="websocket",
            )

        status_code = getattr(exc, "status_code", None)
        if status_code == 404 or "handshake status 404" in lower:
            return CodexAppServerUnavailable(
                f"Codex App Serverは起動していますが、WebSocket接続先が不正です。readyz={ready_detail}; error={raw}",
                error_code="websocket_connect_failed",
                stage="websocket",
            )
        if status_code == 403:
            return CodexAppServerUnavailable(
                f"Codex App Serverは起動していますが、WebSocketハンドシェイクが拒否されました。readyz={ready_detail}; error={raw}",
                error_code="websocket_connect_failed",
                stage="websocket",
            )

        if ready_ok is True:
            return CodexAppServerUnavailable(
                f"Codex App Serverは起動していますが、WebSocket接続に失敗しました。readyz={ready_detail}; error={raw}",
                error_code="websocket_connect_failed",
                stage="websocket",
            )

        return CodexAppServerUnavailable(
            f"Codex App Serverに接続できませんでした ({self.url})。readyz={ready_detail}; error={raw}",
            error_code="websocket_connect_failed",
            stage="websocket",
        )

    def _check_readyz(self) -> tuple[bool | None, str]:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"ws", "wss"}:
            return None, "unsupported-url"
        scheme = "http" if parsed.scheme == "ws" else "https"
        readyz_url = f"{scheme}://{parsed.netloc}/readyz"
        req = Request(readyz_url, method="GET")
        try:
            with urlopen(req, timeout=2) as resp:
                return resp.status == 200, f"{readyz_url}:{resp.status}"
        except HTTPError as exc:
            return False, f"{readyz_url}:{exc.code}"
        except URLError as exc:
            return False, f"{readyz_url}:{exc.reason}"
        except Exception as exc:  # pragma: no cover - defensive
            return None, f"{readyz_url}:{exc}"

    def _initialize(self, ws: WebSocket) -> None:
        self._request(
            ws,
            "initialize",
            {
                "protocolVersion": "1",
                "clientInfo": {
                    "name": self.client_name,
                    "title": "Local Finance Dashboard",
                    "version": self.client_version,
                },
            },
        )
        self._notify(ws, "initialized", {})

    def _request(self, ws: WebSocket, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._next_request_id()
        payload = {"id": req_id, "method": method, "params": params}
        self._send_json(ws, payload)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            msg = self._recv_json(ws, deadline=deadline, stage=method)
            if "id" in msg and msg.get("id") == req_id and "method" not in msg:
                if "error" in msg:
                    raise CodexAppServerError(
                        self._format_error(msg["error"], fallback=method),
                        error_code="protocol_failed",
                        stage=method,
                    )
                return msg.get("result", {}) or {}
            if "id" in msg and "method" in msg:
                self._handle_server_request(ws, msg)

    def _wait_turn_completed(self, ws: WebSocket, thread_id: str, turn_id: str | None) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        chunks: list[str] = []
        completed_message = ""
        while True:
            msg = self._recv_json(ws, deadline=deadline, stage="turn/completed")
            method = msg.get("method")
            if "id" in msg and "method" in msg:
                self._handle_server_request(ws, msg)
                continue
            if not method:
                continue

            params = msg.get("params", {}) or {}
            if method == "item/agentMessage/delta":
                delta = params.get("delta")
                if isinstance(delta, str):
                    chunks.append(delta)
                continue
            if method == "item/completed":
                item = params.get("item", {}) or {}
                if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                    completed_message = item["text"]
                continue
            if method == "turn/completed":
                turn = params.get("turn", {}) or {}
                if turn_id and turn.get("id") and turn.get("id") != turn_id:
                    continue
                if thread_id and turn.get("threadId") and turn.get("threadId") != thread_id:
                    continue
                status = str(turn.get("status") or "").lower()
                if status in {"failed", "interrupted", "cancelled"}:
                    error = turn.get("error") or params.get("error")
                    raise CodexAppServerError(
                        self._format_error(error, fallback="Codex App Server turn failed"),
                        error_code="protocol_failed",
                        stage="turn/completed",
                    )
                text = completed_message.strip() or "".join(chunks).strip()
                if not text:
                    raise CodexAppServerError(
                        "Codex App Serverから分析テキストを取得できませんでした。",
                        error_code="protocol_failed",
                        stage="turn/completed",
                    )
                return text
            if method == "error":
                raise CodexAppServerError(
                    self._format_error(params.get("error"), fallback="Codex App Server error"),
                    error_code="protocol_failed",
                    stage="notification",
                )

    def _handle_server_request(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        req_id = msg.get("id")
        if req_id is None:
            return
        method = str(msg.get("method") or "")
        if method.endswith("requestApproval"):
            if method == "item/permissions/requestApproval":
                # Permission requests cannot be answered with {decision:"decline"}.
                # Return no extra permissions so the turn can continue safely.
                self._send_json(ws, {"id": req_id, "result": {"permissions": {}}})
                return
            self._send_json(ws, {"id": req_id, "result": {"decision": "decline"}})
            return
        self._send_json(
            ws,
            {
                "id": req_id,
                "error": {"message": f"unsupported server request: {method}"},
            },
        )

    def _notify(self, ws: WebSocket, method: str, params: dict[str, Any]) -> None:
        self._send_json(ws, {"method": method, "params": params})

    def _recv_json(self, ws: WebSocket, *, deadline: float, stage: str) -> dict[str, Any]:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAppServerError(
                    f"Codex App Serverの応答がタイムアウトしました: stage={stage}",
                    error_code="protocol_failed",
                    stage=stage,
                )
            ws.settimeout(min(5, remaining))
            try:
                raw = ws.recv()
            except WebSocketTimeoutException:
                continue
            except Exception as exc:
                raise CodexAppServerError(
                    f"Codex App Server受信中にエラーが発生しました: stage={stage}; error={exc}",
                    error_code="protocol_failed",
                    stage=stage,
                ) from exc
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    def _send_json(self, ws: WebSocket, payload: dict[str, Any]) -> None:
        try:
            ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            raise CodexAppServerError(
                f"Codex App Server送信に失敗しました: {exc}",
                error_code="protocol_failed",
                stage="send",
            ) from exc

    def _next_request_id(self) -> int:
        current = self._next_id
        self._next_id += 1
        return current

    @staticmethod
    def _extract_thread_id(result: dict[str, Any]) -> str | None:
        thread = result.get("thread")
        if isinstance(thread, dict) and isinstance(thread.get("id"), str):
            return thread["id"]
        if isinstance(result.get("threadId"), str):
            return result["threadId"]
        return None

    @staticmethod
    def _extract_turn_id(result: dict[str, Any]) -> str | None:
        turn = result.get("turn")
        if isinstance(turn, dict) and isinstance(turn.get("id"), str):
            return turn["id"]
        if isinstance(result.get("turnId"), str):
            return result["turnId"]
        return None

    @staticmethod
    def _format_error(error: Any, fallback: str) -> str:
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message
        return fallback
