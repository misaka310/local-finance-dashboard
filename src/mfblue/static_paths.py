from __future__ import annotations

from pathlib import Path


def build_static_file_map(frontend_dir: Path) -> dict[str, Path]:
    """Index real frontend files so request data is used only as a dictionary key.

    The returned paths originate exclusively from the trusted frontend directory;
    no request-controlled string is ever joined into a filesystem path.
    """
    root = frontend_dir.resolve()
    files: dict[str, Path] = {}
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root).as_posix()
        files[f"/{relative}"] = candidate
    index = files.get("/index.html")
    if index is not None:
        files["/"] = index
        files[""] = index
    return files


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Resolve a request only to a trusted, pre-indexed frontend file."""
    path = str(request_path or "").split("?", 1)[0].split("#", 1)[0].replace("\", "/")
    parts: list[str] = []
    for part in path.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    normalized = "/" + "/".join(parts) if parts else "/"
    return build_static_file_map(frontend_dir).get(normalized)
