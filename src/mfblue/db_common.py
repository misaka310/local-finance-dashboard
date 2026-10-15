from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .asset_fund_names import normalize_asset_fund_name
from .config import database_path
from .defaults import DEFAULT_CATEGORIES, DEFAULT_RULES

GLOBAL_RULE_SOURCE_ID = "__global__"
CSV_IMPORT_RULE_SOURCE_ID = "__csv_import__"
DEFAULT_SUBCATEGORY = "未分類"
FUND_MOVEMENT_CATEGORY_ID = "fund_movement"
FUND_MOVEMENT_CATEGORY_NAME = "資金移動"
FUND_MOVEMENT_SUBCATEGORIES = [
    "チャージ",
    "電子マネー入金",
    "残高移動",
    "口座振替",
    "未分類",
]
FUND_MOVEMENT_DEFAULT_RULES = [
    ("PayPayチャージ", "チャージ", 180),
    ("PAYPAYチャージ", "チャージ", 180),
    ("PayPay残高", "チャージ", 170),
    ("SUICAチャージ", "チャージ", 170),
    ("PASMOチャージ", "チャージ", 170),
    ("nanacoチャージ", "チャージ", 170),
    ("WAONチャージ", "チャージ", 170),
    ("楽天Edyチャージ", "チャージ", 170),
    ("電子マネー入金", "電子マネー入金", 170),
    ("残高移動", "残高移動", 160),
    ("チャージ", "チャージ", 120),
]
SYSTEM_ACCOUNT_NAMES = {
    "paypay-card": "PayPayカード",
    "amazon-order-history": "Amazon注文履歴",
    "amazon-order": "Amazonメール",
}
ASSET_TYPES = {"investment_trust", "stock", "cash", "other"}
ASSET_SOURCES = {"manual", "csv", "generated"}
MIN_BASE_VALUE_FOR_PERCENT = 100000
FISCAL_YEAR_START_MONTH = 4
FUND_PRICE_SOURCE_TYPES = {
    "official_api",
    "official_public_data",
    "official_csv",
    "manual_csv",
    "official_html",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
