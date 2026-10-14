from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import project_path

PUBLIC_CONFIG_PATH = project_path("config", "app.json")
LOCAL_CONFIG_PATH = project_path("config", "local.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "name": "local-finance-dashboard",
        "ui_port": 8765,
        "database_path": "data/mfblue.sqlite3",
    },
    "gmail": {
        "max_results": 100,
        "timezone": "Asia/Tokyo",
        "sources": [],
    },
    "privacy": {
        "store_email_body": False,
        "store_raw_snippet": False,
    },
    "analysis": {
        "enabled": False,
        "codex_app_server_url": "",
        "analyzer": "codex-app-server",
        "analyzer_version": "v2",
        "timeout_seconds": 120,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config must be object: {path}")
    return data


def load_config() -> dict[str, Any]:
    result = _deep_merge(DEFAULT_CONFIG, _load_json_object(PUBLIC_CONFIG_PATH))
    # Machine/user-specific values belong in this ignored file so they never
    # need to be committed to the public repository.
    return _deep_merge(result, _load_json_object(LOCAL_CONFIG_PATH))


def database_path() -> Path:
    cfg = load_config()
    raw = cfg["app"]["database_path"]
    path = Path(raw)
    if not path.is_absolute():
        path = project_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
