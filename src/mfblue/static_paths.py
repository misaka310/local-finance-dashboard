from __future__ import annotations

from pathlib import Path


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Resolve a frontend asset while enforcing path-component containment.

    String-prefix checks are insufficient because a sibling such as
    ``frontend_backup`` starts with ``frontend``. Resolving both paths and using
    ``relative_to`` makes the directory boundary explicit on Windows and POSIX.
    The caller remains responsible for checking that the returned path exists.
    """
    root = frontend_dir.resolve()
    clean = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
    candidate = (root / clean).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    return candidate
