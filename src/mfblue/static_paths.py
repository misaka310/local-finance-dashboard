from __future__ import annotations

import posixpath
from pathlib import Path


def _static_path_index(frontend_dir: Path) -> dict[str, Path]:
    """Build a URL-path index from trusted files already inside the frontend tree."""
    root = frontend_dir.resolve()
    index: dict[str, Path] = {}
    if not root.is_dir():
        return index

    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        index[f"/{relative}"] = resolved

    index["/"] = index.get("/index.html", root / "index.html")
    return index


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Resolve a frontend asset without constructing filesystem paths from input.

    Request input is normalized only as a POSIX URL path and then used as a key
    into an index built exclusively from files discovered under ``frontend_dir``.
    The request therefore never becomes part of a filesystem path expression.
    """
    raw = str(request_path or "/")
    if "\\" in raw or "\x00" in raw:
        return None

    normalized = posixpath.normpath("/" + raw.lstrip("/"))
    if raw.endswith("/") and normalized != "/":
        normalized += "/"
    return _static_path_index(frontend_dir).get(normalized)
