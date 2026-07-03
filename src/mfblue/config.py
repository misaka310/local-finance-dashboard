from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import project_path

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "name": "mfblue-local-budget",
        "ui_port": 8765,
        "database_path": "data/mfblue.sqlite3",
    },
    "gmail": {
        "query": 'newer_than:180d (from:(paypay-card.co.jp) OR subject:(PayPayカード) OR "PayPayカード")',
        "max_results": 100,
        "source_id": "paypay-card",
        "account_name": "PayPayカード",
        "timezone": "Asia/Tokyo",
    },
    "privacy": {
        "store_email_body": False,
        "store_raw_snippet": False,
    },
    "analysis": {
        "enabled": True,
        "codex_app_server_url": "ws://127.0.0.1:8787",
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


def load_config() -> dict[str, Any]:
    path = project_path("config", "app.json")
    if not path.exists():
        return DEFAULT_CONFIG
    data = json.loads(path.read_text(encoding="utf-8"))
    return _deep_merge(DEFAULT_CONFIG, data)


def database_path() -> Path:
    cfg = load_config()
    raw = cfg["app"]["database_path"]
    path = Path(raw)
    if not path.is_absolute():
        path = project_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
