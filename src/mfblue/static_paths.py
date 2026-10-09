from __future__ import annotations

import posixpath
from pathlib import Path


def _normalize_request_key(request_path: str) -> str | None:
    """Convert a URL path to a canonical lookup key without touching the filesystem."""
    raw = str(request_path or "").replace("\\", "/")
    if "\x00" in raw:
        return None
    if raw in ("", "/"):
        return "/index.html"

    normalized = posixpath.normpath("/" + raw.lstrip("/"))
    if normalized == "/.." or normalized.startswith("/../"):
        return None
    return normalized


def _static_file_index(frontend_dir: Path) -> dict[str, Path]:
    """Build a URL-to-file allowlist from files already present under frontend_dir."""
    root = frontend_dir.resolve()
    if not root.is_dir():
        return {}

    result: dict[str, Path] = {}
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        resolved = file_path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        result["/" + relative.as_posix()] = resolved
    return result


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Resolve a frontend asset through an explicit file allowlist.

    Request-controlled text is used only as a dictionary key. Filesystem paths are
    created exclusively while enumerating the trusted frontend directory, so a URL
    cannot inject an arbitrary filesystem path.
    """
    key = _normalize_request_key(request_path)
    if key is None:
        return None
    return _static_file_index(frontend_dir).get(key)
