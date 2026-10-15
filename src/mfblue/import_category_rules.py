from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from .db import CSV_IMPORT_RULE_SOURCE_ID, db, init_db, utc_now_iso
from .paths import project_path

INPUT_PATH = project_path("data", "classification", "category_rules.csv")


class CategoryRuleImportError(Exception):
    pass


@dataclass
class RuleRow:
    merchant_pattern: str
    match_type: str
    category: str
    subcategory: str


def _sorted_rules(rules: list[RuleRow]) -> list[RuleRow]:
    return sorted(
        rules,
        key=lambda r: (
            0 if r.match_type == "exact" else 1,
            -len(r.merchant_pattern) if r.match_type == "contains" else 0,
        ),
    )


def _match_rule(tx_merchant: str, tx_description: str | None, rules: list[RuleRow]) -> RuleRow | None:
    merchant = (tx_merchant or "").strip()
    target = f"{merchant} {tx_description or ''}".strip()
    merchant_lower = merchant.lower()
    target_lower = target.lower()
    for rule in rules:
        pattern = rule.merchant_pattern.strip()
        if not pattern:
            continue
        pattern_lower = pattern.lower()
        if rule.match_type == "exact":
            if merchant_lower == pattern_lower:
                return rule
            continue
        if pattern_lower in merchant_lower or pattern_lower in target_lower:
            return rule
    return None


def _read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "cp932", "shift_jis", "utf-8"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise CategoryRuleImportError(f"Could not read CSV encoding: {path}")


def _read_rows(path: Path) -> list[RuleRow]:
    if not path.exists():
        raise CategoryRuleImportError(f"Input CSV not found: {path}")

    text = _read_text(path)
    reader = csv.DictReader(text.splitlines())
    required = {"merchant_pattern", "match_type", "category", "subcategory"}
    if not reader.fieldnames:
        raise CategoryRuleImportError("CSV header is missing")

    headers = {h.strip() for h in reader.fieldnames if h is not None}
    if not required.issubset(headers):
        missing = ", ".join(sorted(required - headers))
        raise CategoryRuleImportError(f"CSV columns are missing: {missing}")

    rows: list[RuleRow] = []
    for row in reader:
        merchant_pattern = (row.get("merchant_pattern") or "").strip()
        if not merchant_pattern or merchant_pattern.startswith("#"):
            continue

        match_type = (row.get("match_type") or "").strip().lower()
        if match_type not in {"exact", "contains"}:
            raise CategoryRuleImportError("match_type must be 'exact' or 'contains'")

        category = (row.get("category") or "").strip()
        subcategory = (row.get("subcategory") or "").strip() or "未分類"
        if not category:
            raise CategoryRuleImportError("category is required")

        rows.append(
            RuleRow(
                merchant_pattern=merchant_pattern,
                match_type=match_type,
                category=category,
                subcategory=subcategory,
            )
        )

    if not rows:
        raise CategoryRuleImportError("No valid rules found in CSV")

    return rows


def import_rules(path: Path = INPUT_PATH) -> tuple[int, int]:
    rules = _read_rows(path)
    ordered_rules = _sorted_rules(rules)

    with db() as conn:
        init_db(conn)
        categories = {
            row["name"]: row["id"]
            for row in conn.execute("SELECT id, name FROM categories").fetchall()
        }

        unknown_categories = sorted({r.category for r in rules if r.category not in categories})
        if unknown_categories:
            names = ", ".join(unknown_categories)
            raise CategoryRuleImportError(f"Unknown category name in CSV: {names}")

        seen_patterns: set[str] = set()
        for rule in rules:
            key = rule.merchant_pattern.casefold()
            if key in seen_patterns:
                raise CategoryRuleImportError(
                    "Duplicate merchant_pattern is not allowed in category_rules.csv"
                )
            seen_patterns.add(key)

        now = utc_now_iso()
        conn.execute("DELETE FROM category_rules WHERE source_id = ?", (CSV_IMPORT_RULE_SOURCE_ID,))

        for rule in rules:
            category_id = categories[rule.category]
            priority = 1000 + len(rule.merchant_pattern) if rule.match_type == "exact" else 100 + len(rule.merchant_pattern)
            conn.execute(
                """
                INSERT INTO category_rules(
                    pattern, match_type, category_id, subcategory, priority, is_regex, source_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    rule.merchant_pattern,
                    rule.match_type,
                    category_id,
                    rule.subcategory,
                    priority,
                    CSV_IMPORT_RULE_SOURCE_ID,
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO subcategories(category_id, name, sort_order) VALUES (?, ?, 999)",
                (category_id, rule.subcategory),
            )

        updated_count = 0
        tx_rows = conn.execute(
            "SELECT id, merchant, raw_description, source_id, category_id, subcategory FROM transactions"
        ).fetchall()
        for tx in tx_rows:
            matched = _match_rule(tx["merchant"], tx["raw_description"], ordered_rules)
            if matched is None:
                continue
            next_category_id = categories[matched.category]
            normalized_subcategory = (matched.subcategory or "").strip() or "未分類"
            if tx["category_id"] == next_category_id and (tx["subcategory"] or "") == normalized_subcategory:
                continue

            conn.execute(
                "UPDATE transactions SET category_id = ?, subcategory = ?, updated_at = ? WHERE id = ?",
                (next_category_id, normalized_subcategory, utc_now_iso(), tx["id"]),
            )
            conn.execute(
                "INSERT OR IGNORE INTO subcategories(category_id, name, sort_order) VALUES (?, ?, 999)",
                (next_category_id, normalized_subcategory),
            )
            updated_count += 1

    return len(rules), updated_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import category rules from CSV and apply them to existing transactions")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    args = parser.parse_args(argv)

    loaded, updated = import_rules(args.input)
    print(f"Rules loaded: {loaded}")
    print(f"Transactions updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
