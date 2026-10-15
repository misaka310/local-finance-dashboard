from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from websocket import WebSocket, WebSocketTimeoutException, create_connection


def readyz_status(ws_url: str) -> tuple[bool, str]:
    parsed = urlparse(ws_url)
    scheme = "http" if parsed.scheme == "ws" else "https"
    readyz = f"{scheme}://{parsed.netloc}/readyz"
    req = Request(readyz, method="GET")
    try:
        with urlopen(req, timeout=3) as resp:
            return resp.status == 200, f"{readyz} -> {resp.status}"
    except URLError as exc:
        return False, f"{readyz} -> {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"{readyz} -> {exc}"


def send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    ws.send(json.dumps(payload, ensure_ascii=False))


def recv_json(ws: WebSocket, *, deadline: float, last_messages: list[str]) -> dict[str, Any]:
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("timeout waiting for server message")
        try:
            raw = ws.recv()
        except WebSocketTimeoutException:
            continue
        if not raw:
            continue
        last_messages.append(raw)
        if len(last_messages) > 10:
            last_messages.pop(0)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload


def handle_server_request(ws: WebSocket, msg: dict[str, Any]) -> None:
    req_id = msg.get("id")
    method = str(msg.get("method") or "")
    if req_id is None:
        return
    if method == "item/permissions/requestApproval":
        send_json(ws, {"id": req_id, "result": {"permissions": {}}})
        return
    if method.endswith("requestApproval"):
        send_json(ws, {"id": req_id, "result": {"decision": "decline"}})
        return
    send_json(ws, {"id": req_id, "error": {"message": f"unsupported server request: {method}"}})


def request(ws: WebSocket, method: str, params: dict[str, Any], *, req_id: int, timeout: int, last_messages: list[str]) -> dict[str, Any]:
    send_json(ws, {"id": req_id, "method": method, "params": params})
    deadline = time.monotonic() + timeout
    while True:
        msg = recv_json(ws, deadline=deadline, last_messages=last_messages)
        if msg.get("id") == req_id and "method" not in msg:
            if "error" in msg:
                raise RuntimeError(f"{method} error: {msg['error']}")
            return msg.get("result", {}) or {}
        if "id" in msg and "method" in msg:
            handle_server_request(ws, msg)


def wait_turn_completed(
    ws: WebSocket,
    *,
    thread_id: str,
    turn_id: str | None,
    timeout: int,
    last_messages: list[str],
) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[str] = []
    final_text = ""
    while True:
        msg = recv_json(ws, deadline=deadline, last_messages=last_messages)
        if "id" in msg and "method" in msg:
            handle_server_request(ws, msg)
            continue
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
            continue
        if method == "item/completed":
            item = params.get("item") or {}
            if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                final_text = item["text"]
            continue
        if method == "turn/completed":
            turn = params.get("turn") or {}
            current_turn_id = turn.get("id")
            current_thread_id = turn.get("threadId") or params.get("threadId")
            if turn_id and current_turn_id and current_turn_id != turn_id:
                continue
            if thread_id and current_thread_id and current_thread_id != thread_id:
                continue
            status = str(turn.get("status") or "").lower()
            if status in {"failed", "interrupted", "cancelled"}:
                raise RuntimeError(f"turn/completed status={status} payload={msg}")
            return final_text.strip() or "".join(chunks).strip()


def run_probe(url: str, timeout: int, skip_turn: bool) -> int:
    last_messages: list[str] = []

    ok, detail = readyz_status(url)
    if ok:
        print(f"readyz: OK ({detail})")
    else:
        print(f"readyz: NG ({detail})")

    ws: WebSocket | None = None
    try:
        ws = create_connection(url, timeout=timeout, suppress_origin=True)
        ws.settimeout(min(5, timeout))
        print("websocket: OK")

        next_id = 1
        init_result = request(
            ws,
            "initialize",
            {
                "protocolVersion": "1",
                "clientInfo": {
                    "name": "mfblue-probe",
                    "title": "Local Finance Dashboard Probe",
                    "version": "v1",
                },
            },
            req_id=next_id,
            timeout=timeout,
            last_messages=last_messages,
        )
        print("initialize: OK")
        print(f"initialize.result: {json.dumps(init_result, ensure_ascii=False)}")
        next_id += 1

        send_json(ws, {"method": "initialized", "params": {}})
        print("initialized notification: sent")

        thread_result = request(
            ws,
            "thread/start",
            {"ephemeral": True},
            req_id=next_id,
            timeout=timeout,
            last_messages=last_messages,
        )
        thread_id = (thread_result.get("thread") or {}).get("id") or thread_result.get("threadId")
        if not thread_id:
            raise RuntimeError(f"thread/start response did not include thread id: {thread_result}")
        print(f"thread/start: OK thread_id={thread_id}")
        next_id += 1

        if skip_turn:
            print("turn/start: SKIPPED")
            return 0

        turn_result = request(
            ws,
            "turn/start",
            {
                "threadId": thread_id,
                "input": [
                    {
                        "type": "text",
                        "text": "このテストに対して『疎通OK』とだけ回答してください。",
                    }
                ],
            },
            req_id=next_id,
            timeout=timeout,
            last_messages=last_messages,
        )
        turn_id = (turn_result.get("turn") or {}).get("id") or turn_result.get("turnId")
        print(f"turn/start: OK turn_id={turn_id}")

        text = wait_turn_completed(
            ws,
            thread_id=thread_id,
            turn_id=turn_id,
            timeout=timeout,
            last_messages=last_messages,
        )
        print("turn/completed: OK")
        print(f"result: {text}")
        return 0
    except Exception as exc:
        print(f"probe: FAILED ({type(exc).__name__}) {exc}")
        if last_messages:
            print("recent-messages:")
            for raw in last_messages[-10:]:
                print(raw)
        return 1
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Codex App Server JSON-RPC connectivity")
    parser.add_argument("--url", default="ws://127.0.0.1:8787")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--skip-turn", action="store_true")
    args = parser.parse_args()
    return run_probe(url=args.url, timeout=max(10, args.timeout), skip_turn=args.skip_turn)


if __name__ == "__main__":
    raise SystemExit(main())
