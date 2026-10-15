from __future__ import annotations

import re
import sqlite3

from .db import (
    CSV_IMPORT_RULE_SOURCE_ID,
    DEFAULT_SUBCATEGORY,
    FUND_MOVEMENT_CATEGORY_ID,
    GLOBAL_RULE_SOURCE_ID,
)

FUND_MOVEMENT_HINTS = [
    "チャージ",
    "charge",
    "残高移動",
    "電子マネー入金",
    "paypay残高",
    "paypay charge",
    "suicaチャージ",
    "pasmoチャージ",
]


def categorize(
    conn: sqlite3.Connection,
    merchant: str,
    description: str | None = None,
    source_id: str | None = None,
) -> tuple[str, str]:
    merchant_text = (merchant or "").strip()
    target = " ".join([merchant_text, description or ""]).strip()
    if not target:
        return "uncategorized", DEFAULT_SUBCATEGORY

    params: list[str] = [GLOBAL_RULE_SOURCE_ID, CSV_IMPORT_RULE_SOURCE_ID]
    where = ["source_id = ?", "source_id = ?"]
    if source_id:
        where.append("source_id = ?")
        params.append(source_id)
    where.append("source_id IS NULL")

    rows = conn.execute(
        f"""
        SELECT pattern, match_type, category_id, subcategory, is_regex, priority, source_id
        FROM category_rules
        WHERE {' OR '.join(where)}
        ORDER BY
            CASE WHEN source_id = ? THEN 0 ELSE 1 END,
            CASE WHEN COALESCE(match_type, 'contains') = 'exact' THEN 0 ELSE 1 END,
            CASE
                WHEN COALESCE(match_type, 'contains') = 'contains' THEN LENGTH(pattern)
                ELSE 0
            END DESC,
            priority DESC,
            id DESC
        """,
        [*params, source_id or ""],
    ).fetchall()

    merchant_lower = merchant_text.lower()
    target_lower = target.lower()

    for row in rows:
        pattern = str(row["pattern"] or "").strip()
        if not pattern:
            continue

        match_type = (row["match_type"] or "contains").lower()
        if row["is_regex"]:
            try:
                if re.search(pattern, target, flags=re.IGNORECASE):
                    return row["category_id"], row["subcategory"] or DEFAULT_SUBCATEGORY
            except re.error:
                continue
            continue

        pattern_lower = pattern.lower()
        if match_type == "exact":
            if merchant_lower == pattern_lower:
                return row["category_id"], row["subcategory"] or DEFAULT_SUBCATEGORY
            continue

        if pattern_lower in merchant_lower or pattern_lower in target_lower:
            return row["category_id"], row["subcategory"] or DEFAULT_SUBCATEGORY

    for hint in FUND_MOVEMENT_HINTS:
        if hint in target_lower:
            return FUND_MOVEMENT_CATEGORY_ID, "チャージ"

    return "uncategorized", DEFAULT_SUBCATEGORY
