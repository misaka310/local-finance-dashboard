from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import project_path

DEFAULT_CONFIG_PATH = project_path("config", "fund_price_sources.json")


def load_fund_price_sources(config_path: Path | None = None) -> list[dict[str, Any]]:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"fund_price_sources config must be list: {path}")
    result: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        result.append(dict(item))
    return result

