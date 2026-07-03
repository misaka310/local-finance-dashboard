from __future__ import annotations

import base64
from email.header import decode_header, make_header
from typing import Any

from googleapiclient.discovery import build

from .auth import get_credentials


def gmail_service(allow_interactive: bool = False):
    creds = get_credentials(allow_interactive=allow_interactive)
    return build("gmail", "v1", credentials=creds)


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def headers_to_dict(headers: list[dict[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for h in headers:
        name = h.get("name", "")
        result[name] = _decode_header(h.get("value", ""))
        result[name.lower()] = result[name]
    return result


def _decode_body_data(data: str | None) -> str:
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data.encode("utf-8"))
    for enc in ("utf-8", "iso-2022-jp", "shift_jis", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text_from_payload(payload: dict[str, Any]) -> str:
    texts: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if mime.startswith("text/plain") and data:
            texts.append(_decode_body_data(data))
        elif mime.startswith("text/html") and data and not texts:
            texts.append(_decode_body_data(data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return "\n".join([t for t in texts if t])


def search_message_ids(query: str, max_results: int = 100) -> list[str]:
    service = gmail_service()
    ids: list[str] = []
    request = service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 500))
    while request is not None and len(ids) < max_results:
        response = request.execute()
        ids.extend([m["id"] for m in response.get("messages", [])])
        if len(ids) >= max_results:
            break
        request = service.users().messages().list_next(request, response)
    return ids[:max_results]


def get_message(message_id: str) -> dict[str, Any]:
    service = gmail_service()
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()
