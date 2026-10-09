from __future__ import annotations

import mimetypes
import posixpath
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticAsset:
    path: Path
    content_type: str


def _static_asset_index(frontend_dir: Path) -> dict[str, StaticAsset]:
    """Build a trusted URL-to-file index without using request data in paths."""
    root = frontend_dir.resolve()
    assets: dict[str, StaticAsset] = {}
    if not root.is_dir():
        return assets

    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        resolved = entry.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:  # pragma: no cover - requires an OS-level escaping symlink
            # Never expose symlinks or entries resolving outside the frontend root.
            continue
        key = "/" + relative.as_posix()
        content_type = mimetypes.guess_type(relative.name)[0] or "application/octet-stream"
        assets[key] = StaticAsset(path=resolved, content_type=content_type)

    index_asset = assets.get("/index.html")
    if index_asset is not None:
        assets["/"] = index_asset
    return assets


def _normalize_request_key(request_path: str) -> str | None:
    value = str(request_path or "").replace("\\", "/")
    if "\x00" in value:
        return None
    normalized = posixpath.normpath("/" + value.lstrip("/"))
    return "/" if normalized in {"/", "/."} else normalized


def resolve_static_asset(request_path: str, frontend_dir: Path) -> StaticAsset | None:
    """Resolve request data only as a lookup key into a trusted file index."""
    key = _normalize_request_key(request_path)
    if key is None:
        return None
    return _static_asset_index(frontend_dir).get(key)


def resolve_static_path(request_path: str, frontend_dir: Path) -> Path | None:
    """Compatibility wrapper returning only the resolved safe path."""
    asset = resolve_static_asset(request_path, frontend_dir)
    return asset.path if asset is not None else None
