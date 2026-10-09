from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".gif": "image/gif",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class StaticAsset:
    path: Path
    content_type: str


def build_static_index(frontend_dir: Path) -> dict[str, StaticAsset]:
    """Index trusted frontend files before handling any request paths."""
    root = frontend_dir.resolve()
    index: dict[str, StaticAsset] = {}
    if not root.is_dir():
        return index

    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        key = "/" + relative.as_posix()
        content_type = _CONTENT_TYPES.get(resolved.suffix.lower(), "application/octet-stream")
        index[key] = StaticAsset(path=resolved, content_type=content_type)
        if relative.as_posix() == "index.html":
            index["/"] = index[key]
    return index


def _normalize_request_key(request_path: str) -> str | None:
    raw = str(request_path or "/").split("?", 1)[0]
    if "\x00" in raw or "\\" in raw:
        return None
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def resolve_static_asset(request_path: str, index: dict[str, StaticAsset]) -> StaticAsset | None:
    key = _normalize_request_key(request_path)
    if key is None:
        return None
    return index.get(key)


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Compatibility wrapper used by existing tests and callers."""
    asset = resolve_static_asset(request_path, build_static_index(frontend_dir))
    return asset.path if asset else None
