from __future__ import annotations

from pathlib import Path


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Resolve a requested path without allowing escape from the frontend root."""
    root = frontend_dir.resolve()
    clean = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
    candidate = (root / clean).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate
