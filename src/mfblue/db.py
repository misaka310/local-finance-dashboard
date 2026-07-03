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


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _has_column(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_asset_snapshot_source_generated(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'asset_snapshots'"
    ).fetchone()
    sql = str(row["sql"] or "") if row else ""
    if not sql or "generated" in sql:
        return
    conn.execute("ALTER TABLE asset_snapshots RENAME TO asset_snapshots_old")
    conn.execute(
        """
        CREATE TABLE asset_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL REFERENCES asset_products(id),
            valuation_date TEXT NOT NULL,
            period_month TEXT NOT NULL,
            quantity REAL,
            base_price REAL,
            acquisition_price REAL,
            current_value_yen INTEGER NOT NULL DEFAULT 0,
            invested_amount_yen INTEGER,
            profit_loss_yen INTEGER,
            profit_loss_rate REAL,
            daily_change_yen INTEGER,
            daily_change_rate REAL,
            dividend_method TEXT,
            source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual', 'csv', 'generated')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(asset_id, period_month)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO asset_snapshots(
            id, asset_id, valuation_date, period_month, quantity, base_price, acquisition_price,
            current_value_yen, invested_amount_yen, profit_loss_yen, profit_loss_rate,
            daily_change_yen, daily_change_rate, dividend_method, source, created_at, updated_at
        )
        SELECT
            id, asset_id, valuation_date, period_month, quantity, base_price, acquisition_price,
            current_value_yen, invested_amount_yen, profit_loss_yen, profit_loss_rate,
            daily_change_yen, daily_change_rate, dividend_method, source, created_at, updated_at
        FROM asset_snapshots_old
        """
    )
    conn.execute("DROP TABLE asset_snapshots_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_snapshots_period ON asset_snapshots(period_month, asset_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_snapshots_valuation_date ON asset_snapshots(valuation_date DESC, id DESC)"
    )


def _ensure_fund_price_source_type_values(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'fund_price_sources'"
    ).fetchone()
    sql = str(row["sql"] or "") if row else ""
    if not sql:
        return
    if "official_api" in sql and "official_public_data" in sql:
        return

    conn.execute("ALTER TABLE fund_price_sources RENAME TO fund_price_sources_old")
    conn.execute(
        """
        CREATE TABLE fund_price_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_name TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK(source_type IN ('official_api', 'official_public_data', 'official_csv', 'manual_csv')),
            parser_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(fund_name, provider_name, source_url)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fund_price_sources(
            id, fund_name, provider_name, source_url, source_type, parser_name, is_active, created_at, updated_at
        )
        SELECT
            id,
            fund_name,
            provider_name,
            source_url,
            CASE source_type
                WHEN 'official_html' THEN 'official_public_data'
                ELSE source_type
            END AS source_type,
            parser_name,
            is_active,
            created_at,
            updated_at
        FROM fund_price_sources_old
        """
    )
    conn.execute("DROP TABLE fund_price_sources_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fund_price_sources_active ON fund_price_sources(is_active, fund_name)")


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_system INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS subcategories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id TEXT NOT NULL REFERENCES categories(id),
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                UNIQUE(category_id, name)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'credit_card',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                match_type TEXT NOT NULL DEFAULT 'contains',
                category_id TEXT NOT NULL REFERENCES categories(id),
                subcategory TEXT NOT NULL DEFAULT '未分類',
                priority INTEGER NOT NULL DEFAULT 0,
                is_regex INTEGER NOT NULL DEFAULT 0,
                source_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(pattern, source_id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                external_id TEXT NOT NULL,
                thread_id TEXT,
                direction TEXT NOT NULL CHECK(direction IN ('expense', 'income')),
                occurred_at TEXT NOT NULL,
                posted_at TEXT,
                merchant TEXT NOT NULL,
                raw_description TEXT,
                amount_yen INTEGER NOT NULL CHECK(amount_yen >= 0),
                category_id TEXT NOT NULL REFERENCES categories(id),
                subcategory TEXT NOT NULL DEFAULT '未分類',
                note TEXT,
                imported_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_id, external_id)
            );

            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                fetched_count INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS import_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES import_runs(id),
                source_id TEXT NOT NULL,
                external_id TEXT,
                subject TEXT,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_type TEXT NOT NULL CHECK(period_type IN ('month', 'year')),
                period TEXT NOT NULL,
                account_id TEXT NOT NULL,
                direction TEXT NOT NULL CHECK(direction IN ('expense', 'income')),
                input_hash TEXT NOT NULL,
                analyzer TEXT NOT NULL,
                analyzer_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('success', 'failed')),
                result_text TEXT,
                result_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS asset_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                asset_type TEXT NOT NULL CHECK(asset_type IN ('investment_trust', 'stock', 'cash', 'other')),
                institution TEXT NOT NULL,
                account_type TEXT NOT NULL,
                memo TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, institution, account_type)
            );

            CREATE TABLE IF NOT EXISTS asset_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL REFERENCES asset_products(id),
                valuation_date TEXT NOT NULL,
                period_month TEXT NOT NULL,
                quantity REAL,
                base_price REAL,
                acquisition_price REAL,
                current_value_yen INTEGER NOT NULL DEFAULT 0,
                invested_amount_yen INTEGER,
                profit_loss_yen INTEGER,
                profit_loss_rate REAL,
                daily_change_yen INTEGER,
                daily_change_rate REAL,
                dividend_method TEXT,
                source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual', 'csv', 'generated')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(asset_id, period_month)
            );

            CREATE TABLE IF NOT EXISTS asset_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL REFERENCES asset_products(id),
                purchase_date TEXT NOT NULL,
                period_month TEXT NOT NULL,
                amount_yen INTEGER NOT NULL CHECK(amount_yen > 0),
                quantity REAL,
                unit_price REAL,
                settlement_date TEXT,
                memo TEXT,
                source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual', 'csv')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fund_price_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_name TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK(source_type IN ('official_api', 'official_public_data', 'official_csv', 'manual_csv')),
                parser_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(fund_name, provider_name, source_url)
            );

            CREATE TABLE IF NOT EXISTS fund_nav_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_name TEXT NOT NULL,
                price_date TEXT NOT NULL,
                base_price REAL NOT NULL,
                provider_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(fund_name, price_date, provider_name)
            );

            CREATE TABLE IF NOT EXISTS asset_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                settlement_date TEXT,
                fund_name TEXT NOT NULL,
                institution TEXT NOT NULL,
                account_type TEXT NOT NULL,
                trade_type TEXT NOT NULL CHECK(trade_type IN ('buy', 'sell', 'dividend_reinvest', 'other')),
                quantity REAL,
                unit_price REAL,
                amount_yen INTEGER,
                source TEXT NOT NULL CHECK(source IN ('csv', 'manual')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_category_rules_source ON category_rules(source_id);
            CREATE INDEX IF NOT EXISTS idx_category_rules_priority ON category_rules(priority DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_lookup
                ON analysis_runs(period_type, period, account_id, direction, input_hash, analyzer, analyzer_version, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_status
                ON analysis_runs(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_asset_snapshots_period ON asset_snapshots(period_month, asset_id);
            CREATE INDEX IF NOT EXISTS idx_asset_snapshots_valuation_date ON asset_snapshots(valuation_date DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_asset_purchases_period ON asset_purchases(period_month, asset_id);
            CREATE INDEX IF NOT EXISTS idx_fund_nav_prices_lookup ON fund_nav_prices(fund_name, price_date DESC);
            CREATE INDEX IF NOT EXISTS idx_fund_price_sources_active ON fund_price_sources(is_active, fund_name);
            CREATE INDEX IF NOT EXISTS idx_asset_trades_lookup ON asset_trades(fund_name, account_type, trade_date, id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_trades_dedup
                ON asset_trades(
                    trade_date,
                    COALESCE(settlement_date, ''),
                    fund_name,
                    institution,
                    account_type,
                    trade_type,
                    COALESCE(quantity, 0),
                    COALESCE(unit_price, 0),
                    COALESCE(amount_yen, 0),
                    source
                );
            """
        )
        _ensure_asset_snapshot_source_generated(conn)
        _ensure_fund_price_source_type_values(conn)

        _ensure_column(conn, "category_rules", "match_type", "TEXT NOT NULL DEFAULT 'contains'")
        conn.execute(
            """
            UPDATE category_rules
            SET match_type = 'contains'
            WHERE match_type IS NULL OR match_type NOT IN ('exact', 'contains')
            """
        )
        conn.execute(
            """
            DELETE FROM category_rules
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM category_rules
                GROUP BY pattern, COALESCE(source_id, ?)
            )
            """,
            (GLOBAL_RULE_SOURCE_ID,),
        )
        conn.execute(
            "UPDATE category_rules SET source_id = ? WHERE source_id IS NULL",
            (GLOBAL_RULE_SOURCE_ID,),
        )

        seed_defaults(conn)
        normalize_system_accounts(conn)
        normalize_stats = normalize_negative_transactions(conn)
        if normalize_stats["normalized_count"] > 0:
            print(
                "[db] normalized negative amount rows: "
                f"{normalize_stats['normalized_count']} (direction updated: {normalize_stats['direction_updated_count']})"
            )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def seed_defaults(conn: sqlite3.Connection) -> None:
    for i, (category_id, name, subcategories) in enumerate(DEFAULT_CATEGORIES):
        conn.execute(
            "INSERT OR IGNORE INTO categories(id, name, sort_order, is_system) VALUES (?, ?, ?, 1)",
            (category_id, name, i),
        )
        for j, sub in enumerate(subcategories):
            conn.execute(
                "INSERT OR IGNORE INTO subcategories(category_id, name, sort_order) VALUES (?, ?, ?)",
                (category_id, sub, j),
            )
    conn.execute(
        "INSERT OR IGNORE INTO categories(id, name, sort_order, is_system) VALUES (?, ?, ?, 1)",
        (FUND_MOVEMENT_CATEGORY_ID, FUND_MOVEMENT_CATEGORY_NAME, len(DEFAULT_CATEGORIES)),
    )
    for i, sub in enumerate(FUND_MOVEMENT_SUBCATEGORIES):
        conn.execute(
            "INSERT OR IGNORE INTO subcategories(category_id, name, sort_order) VALUES (?, ?, ?)",
            (FUND_MOVEMENT_CATEGORY_ID, sub, i),
        )

    now = utc_now_iso()
    conn.execute(
        "INSERT OR IGNORE INTO accounts(id, name, kind, created_at) VALUES (?, ?, ?, ?)",
        ("paypay-card", "PayPayカード", "credit_card", now),
    )

    for pattern, category_id, subcategory, priority in DEFAULT_RULES:
        conn.execute(
            """
            INSERT OR IGNORE INTO category_rules(pattern, match_type, category_id, subcategory, priority, is_regex, source_id, created_at, updated_at)
            VALUES (?, 'contains', ?, ?, ?, 0, ?, ?, ?)
            """,
            (pattern, category_id, subcategory, priority, GLOBAL_RULE_SOURCE_ID, now, now),
        )
    for pattern, subcategory, priority in FUND_MOVEMENT_DEFAULT_RULES:
        conn.execute(
            """
            INSERT OR IGNORE INTO category_rules(pattern, match_type, category_id, subcategory, priority, is_regex, source_id, created_at, updated_at)
            VALUES (?, 'contains', ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                pattern,
                FUND_MOVEMENT_CATEGORY_ID,
                subcategory,
                priority,
                GLOBAL_RULE_SOURCE_ID,
                now,
                now,
            ),
        )


def is_fund_movement_category(category_id: str | None) -> bool:
    return str(category_id or "").strip() == FUND_MOVEMENT_CATEGORY_ID


def normalize_system_accounts(conn: sqlite3.Connection) -> None:
    now = utc_now_iso()
    for account_id, label in SYSTEM_ACCOUNT_NAMES.items():
        conn.execute(
            "INSERT OR IGNORE INTO accounts(id, name, kind, created_at) VALUES (?, ?, 'credit_card', ?)",
            (account_id, label, now),
        )
        conn.execute(
            "UPDATE accounts SET name = ? WHERE id = ? AND name <> ?",
            (label, account_id, label),
        )


def ensure_account(conn: sqlite3.Connection, account_id: str, name: str, kind: str = "credit_card") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO accounts(id, name, kind, created_at) VALUES (?, ?, ?, ?)",
        (account_id, name, kind, utc_now_iso()),
    )


def list_categories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, name FROM categories ORDER BY sort_order, name").fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        subs = conn.execute(
            "SELECT name FROM subcategories WHERE category_id = ? ORDER BY sort_order, name",
            (row["id"],),
        ).fetchall()
        result.append({"id": row["id"], "name": row["name"], "subcategories": [s["name"] for s in subs]})
    return result


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = [int(x) for x in month.split("-")]
    start = datetime(year, mon, 1)
    if mon == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, mon + 1, 1)
    return start.date().isoformat(), end.date().isoformat()


def year_bounds(year: str) -> tuple[str, str]:
    y = int(year)
    start = datetime(y, 1, 1)
    end = datetime(y + 1, 1, 1)
    return start.date().isoformat(), end.date().isoformat()


def period_bounds(month: str | None = None, year: str | None = None) -> tuple[str, str, str, str]:
    if year:
        start, end = year_bounds(year)
        return start, end, year, "year"
    if month:
        start, end = month_bounds(month)
        return start, end, month, "month"
    raise ValueError("month or year is required")


def available_period_bounds(conn: sqlite3.Connection) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT
            MIN(substr(occurred_at, 1, 7)) AS min_month,
            MAX(substr(occurred_at, 1, 7)) AS max_month,
            MIN(substr(occurred_at, 1, 4)) AS min_year,
            MAX(substr(occurred_at, 1, 4)) AS max_year
        FROM transactions
        """
    ).fetchone()
    today = date.today()
    default_month = f"{today.year:04d}-{today.month:02d}"
    default_year = f"{today.year:04d}"
    return {
        "min_month": row["min_month"] or default_month,
        "max_month": row["max_month"] or default_month,
        "min_year": row["min_year"] or default_year,
        "max_year": row["max_year"] or default_year,
    }


def normalize_negative_transactions(conn: sqlite3.Connection) -> dict[str, int]:
    stats = {"normalized_count": 0, "direction_updated_count": 0}
    rows = conn.execute("SELECT id, amount_yen, direction FROM transactions WHERE amount_yen < 0").fetchall()
    if not rows:
        return stats
    now = utc_now_iso()
    for row in rows:
        amount = abs(int(row["amount_yen"] or 0))
        direction = "income"
        conn.execute(
            "UPDATE transactions SET amount_yen = ?, direction = ?, updated_at = ? WHERE id = ?",
            (amount, direction, now, row["id"]),
        )
        stats["normalized_count"] += 1
        if row["direction"] != direction:
            stats["direction_updated_count"] += 1
    return stats


def summary_for_month(conn: sqlite3.Connection, month: str, show_subcategories: bool = False) -> dict[str, Any]:
    return summary_for_period(conn, month=month, direction="expense", show_subcategories=show_subcategories)


def summary_for_period(
    conn: sqlite3.Connection,
    month: str | None = None,
    year: str | None = None,
    direction: str = "expense",
    show_subcategories: bool = False,
    account_id: str | None = None,
    account_ids: list[str] | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    if direction not in {"expense", "income"}:
        raise ValueError("direction must be 'expense' or 'income'")
    start, end, period, period_type = period_bounds(month=month, year=year)
    base_where = ["occurred_at >= ?", "occurred_at < ?"]
    base_params: list[Any] = [start, end]
    if account_ids:
        placeholders = ", ".join(["?"] * len(account_ids))
        base_where.append(f"account_id IN ({placeholders})")
        base_params.extend(account_ids)
    elif account_id:
        base_where.append("account_id = ?")
        base_params.append(account_id)
    if source_id:
        base_where.append("source_id = ?")
        base_params.append(source_id)

    totals = conn.execute(
        f"""
        SELECT direction, COALESCE(SUM(amount_yen), 0) AS total
        FROM transactions
        WHERE {' AND '.join(base_where)}
        GROUP BY direction
        """,
        base_params,
    ).fetchall()
    total_by_direction = {row["direction"]: int(row["total"] or 0) for row in totals}
    fund_movement_row = conn.execute(
        f"""
        SELECT COALESCE(SUM(amount_yen), 0) AS total, COUNT(*) AS count
        FROM transactions
        WHERE {' AND '.join(base_where)} AND direction = 'expense' AND category_id = ?
        """,
        [*base_params, FUND_MOVEMENT_CATEGORY_ID],
    ).fetchone()
    fund_movement_total = int((fund_movement_row["total"] if fund_movement_row else 0) or 0)
    fund_movement_count = int((fund_movement_row["count"] if fund_movement_row else 0) or 0)
    raw_expense_total = total_by_direction.get("expense", 0)
    expense_total = max(0, raw_expense_total - fund_movement_total)
    selected_total = expense_total if direction == "expense" else total_by_direction.get(direction, 0)

    group_cols = "c.id, c.name, t.subcategory" if show_subcategories else "c.id, c.name"
    select_cols = (
        "c.id AS category_id, c.name AS category_name, t.subcategory AS subcategory"
        if show_subcategories
        else "c.id AS category_id, c.name AS category_name, NULL AS subcategory"
    )
    tx_where = ["t.direction = ?", "t.occurred_at >= ?", "t.occurred_at < ?"]
    tx_params: list[Any] = [direction, start, end]
    if account_ids:
        placeholders = ", ".join(["?"] * len(account_ids))
        tx_where.append(f"t.account_id IN ({placeholders})")
        tx_params.extend(account_ids)
    elif account_id:
        tx_where.append("t.account_id = ?")
        tx_params.append(account_id)
    if source_id:
        tx_where.append("t.source_id = ?")
        tx_params.append(source_id)
    if direction == "expense":
        tx_where.append("t.category_id <> ?")
        tx_params.append(FUND_MOVEMENT_CATEGORY_ID)

    rows = conn.execute(
        f"""
        SELECT {select_cols}, SUM(t.amount_yen) AS total, COUNT(*) AS count
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        WHERE {' AND '.join(tx_where)}
        GROUP BY {group_cols}
        ORDER BY total DESC, c.name
        """,
        tx_params,
    ).fetchall()
    categories = []
    for row in rows:
        total = int(row["total"] or 0)
        percent = (total / selected_total * 100.0) if selected_total > 0 else 0.0
        categories.append(
            dict(row)
            | {
                "total": total,
                "count": int(row["count"] or 0),
                "percent": round(percent, 1),
            }
        )
    return {
        period_type: period,
        "period_type": period_type,
        "direction": direction,
        "income_total": total_by_direction.get("income", 0),
        "expense_total": expense_total,
        "expense_total_including_fund_movement": raw_expense_total,
        "fund_movement_total": fund_movement_total,
        "fund_movement_count": fund_movement_count,
        "balance": total_by_direction.get("income", 0) - expense_total,
        "categories": categories,
    }


def transactions_for_month(
    conn: sqlite3.Connection,
    month: str,
    category_id: str | None = None,
    subcategory: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    return transactions_for_period(
        conn,
        month=month,
        category_id=category_id,
        subcategory=subcategory,
        limit=limit,
    )


def transactions_for_period(
    conn: sqlite3.Connection,
    month: str | None = None,
    year: str | None = None,
    category_id: str | None = None,
    subcategory: str | None = None,
    direction: str | None = None,
    account_id: str | None = None,
    account_ids: list[str] | None = None,
    source_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    if direction is not None and direction not in {"expense", "income"}:
        raise ValueError("direction must be 'expense' or 'income'")
    start, end, _, _ = period_bounds(month=month, year=year)
    params: list[Any] = [start, end]
    where = ["t.occurred_at >= ?", "t.occurred_at < ?"]
    if direction:
        where.append("t.direction = ?")
        params.append(direction)
    if category_id:
        where.append("t.category_id = ?")
        params.append(category_id)
    if subcategory:
        where.append("t.subcategory = ?")
        params.append(subcategory)
    if account_ids:
        placeholders = ", ".join(["?"] * len(account_ids))
        where.append(f"t.account_id IN ({placeholders})")
        params.extend(account_ids)
    elif account_id:
        where.append("t.account_id = ?")
        params.append(account_id)
    if source_id:
        where.append("t.source_id = ?")
        params.append(source_id)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT t.*, c.name AS category_name, a.name AS account_name,
               CASE WHEN t.category_id = ? THEN 1 ELSE 0 END AS is_fund_movement
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        JOIN accounts a ON a.id = t.account_id
        WHERE {' AND '.join(where)}
        ORDER BY t.occurred_at DESC, t.id DESC
        LIMIT ?
        """,
        [FUND_MOVEMENT_CATEGORY_ID, *params],
    ).fetchall()
    return [dict(row) for row in rows]


def list_available_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.name,
            a.kind,
            a.is_active,
            COUNT(t.id) AS transaction_count
        FROM accounts a
        LEFT JOIN transactions t ON t.account_id = a.id
        GROUP BY a.id, a.name, a.kind, a.is_active
        HAVING a.is_active = 1 OR COUNT(t.id) > 0
        ORDER BY
            CASE a.id
                WHEN 'paypay-card' THEN 0
                WHEN 'amazon-order-history' THEN 1
                WHEN 'amazon-order' THEN 2
                ELSE 3
            END,
            a.name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_transaction(conn: sqlite3.Connection, tx: dict[str, Any]) -> str:
    now = utc_now_iso()
    exists = conn.execute(
        "SELECT id FROM transactions WHERE source_id = ? AND external_id = ?",
        (tx["source_id"], tx["external_id"]),
    ).fetchone()
    if exists:
        conn.execute(
            """
            UPDATE transactions
            SET thread_id = ?, occurred_at = ?, posted_at = ?, merchant = ?, raw_description = ?,
                direction = ?, amount_yen = ?, updated_at = ?
            WHERE source_id = ? AND external_id = ?
            """,
            (
                tx.get("thread_id"),
                tx["occurred_at"],
                tx.get("posted_at"),
                tx["merchant"],
                tx.get("raw_description"),
                tx.get("direction", "expense"),
                tx["amount_yen"],
                now,
                tx["source_id"],
                tx["external_id"],
            ),
        )
        return "updated"

    conn.execute(
        """
        INSERT INTO transactions(
            source_id, account_id, external_id, thread_id, direction, occurred_at, posted_at,
            merchant, raw_description, amount_yen, category_id, subcategory, note, imported_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx["source_id"],
            tx["account_id"],
            tx["external_id"],
            tx.get("thread_id"),
            tx.get("direction", "expense"),
            tx["occurred_at"],
            tx.get("posted_at"),
            tx["merchant"],
            tx.get("raw_description"),
            tx["amount_yen"],
            tx["category_id"],
            tx.get("subcategory", DEFAULT_SUBCATEGORY),
            tx.get("note"),
            now,
            now,
        ),
    )
    return "inserted"


def update_transaction_category(
    conn: sqlite3.Connection,
    transaction_id: int,
    category_id: str,
    subcategory: str,
    learn_rule: bool = True,
    apply_to_existing: bool = False,
) -> dict[str, Any]:
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if tx is None:
        raise KeyError(f"transaction not found: {transaction_id}")

    normalized_subcategory = (subcategory or "").strip() or DEFAULT_SUBCATEGORY
    conn.execute(
        "INSERT OR IGNORE INTO subcategories(category_id, name, sort_order) VALUES (?, ?, 999)",
        (category_id, normalized_subcategory),
    )
    conn.execute(
        "UPDATE transactions SET category_id = ?, subcategory = ?, updated_at = ? WHERE id = ?",
        (category_id, normalized_subcategory, utc_now_iso(), transaction_id),
    )

    applied_count = 1
    now = utc_now_iso()
    if apply_to_existing and tx["merchant"]:
        cur = conn.execute(
            """
            UPDATE transactions
            SET category_id = ?, subcategory = ?, updated_at = ?
            WHERE merchant = ? AND source_id = ?
            """,
            (category_id, normalized_subcategory, now, tx["merchant"], tx["source_id"]),
        )
        applied_count = max(1, int(cur.rowcount))

    if learn_rule and tx["merchant"]:
        conn.execute(
            """
            INSERT INTO category_rules(pattern, match_type, category_id, subcategory, priority, is_regex, source_id, created_at, updated_at)
            VALUES (?, 'exact', ?, ?, 200, 0, ?, ?, ?)
            ON CONFLICT(pattern, source_id) DO UPDATE SET
                match_type = excluded.match_type,
                category_id = excluded.category_id,
                subcategory = excluded.subcategory,
                priority = excluded.priority,
                updated_at = excluded.updated_at
            """,
            (tx["merchant"], category_id, normalized_subcategory, tx["source_id"], now, now),
        )
    return dict(tx) | {"applied_count": applied_count}


def normalize_period_month(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 7:
        year = int(text[0:4])
        month = int(text[5:7])
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    raise ValueError(f"invalid period month: {value}")


def period_month_from_date(date_value: str) -> str:
    value = str(date_value or "").strip()
    if len(value) < 10:
        raise ValueError(f"invalid date: {date_value}")
    return normalize_period_month(value[0:7])


def _normalize_asset_type(value: str | None) -> str:
    asset_type = str(value or "other").strip().lower()
    if asset_type not in ASSET_TYPES:
        return "other"
    return asset_type


def _normalize_asset_source(value: str | None) -> str:
    source = str(value or "manual").strip().lower()
    if source not in ASSET_SOURCES:
        return "manual"
    return source


def _asset_source_priority(source: str | None) -> int:
    return 0 if str(source or "").strip().lower() in {"csv", "manual"} else 1


def _is_better_snapshot_row(candidate: sqlite3.Row, existing: sqlite3.Row) -> bool:
    cand_priority = _asset_source_priority(candidate["source"])
    existing_priority = _asset_source_priority(existing["source"])
    if cand_priority != existing_priority:
        return cand_priority < existing_priority
    cand_valuation = str(candidate["valuation_date"] or "")
    existing_valuation = str(existing["valuation_date"] or "")
    if cand_valuation != existing_valuation:
        return cand_valuation > existing_valuation
    cand_updated = str(candidate["updated_at"] or "")
    existing_updated = str(existing["updated_at"] or "")
    if cand_updated != existing_updated:
        return cand_updated > existing_updated
    return int(candidate["id"]) > int(existing["id"])


def _effective_asset_snapshot_rows(
    conn: sqlite3.Connection,
    *,
    period_month: str | None = None,
) -> list[sqlite3.Row]:
    where: list[str] = []
    params: list[Any] = []
    if period_month:
        where.append("s.period_month = ?")
        params.append(period_month)
    sql = """
        SELECT
            s.id,
            s.asset_id,
            s.valuation_date,
            s.period_month,
            s.quantity,
            s.base_price,
            s.acquisition_price,
            s.current_value_yen,
            s.invested_amount_yen,
            s.profit_loss_yen,
            s.profit_loss_rate,
            s.daily_change_yen,
            s.daily_change_rate,
            s.dividend_method,
            s.source,
            s.created_at,
            s.updated_at,
            p.name,
            p.asset_type,
            p.institution,
            p.account_type
        FROM asset_snapshots s
        JOIN asset_products p ON p.id = s.asset_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.period_month, p.institution, p.account_type, p.name, s.id"
    rows = conn.execute(sql, params).fetchall()
    measured_account_months = {
        (
            str(row["period_month"]),
            str(row["institution"] or ""),
            str(row["account_type"] or ""),
        )
        for row in rows
        if _asset_source_priority(str(row["source"] or "")) == 0
    }
    measured_months = {item[0] for item in measured_account_months}
    selected: dict[tuple[str, str, str, str], sqlite3.Row] = {}
    for row in rows:
        period = str(row["period_month"])
        if _asset_source_priority(str(row["source"] or "")) > 0 and period in measured_months:
            continue
        account_month = (
            period,
            str(row["institution"] or ""),
            str(row["account_type"] or ""),
        )
        if _asset_source_priority(str(row["source"] or "")) > 0 and account_month in measured_account_months:
            continue
        key = (
            str(row["period_month"]),
            account_month[1],
            account_month[2],
            normalize_asset_fund_name(str(row["name"] or "")),
        )
        existing = selected.get(key)
        if existing is None or _is_better_snapshot_row(row, existing):
            selected[key] = row
    return list(selected.values())


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(round(float(text)))


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def list_asset_products(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, name, asset_type, institution, account_type, memo, created_at, updated_at
        FROM asset_products
        ORDER BY institution, account_type, name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def ensure_asset_product(
    conn: sqlite3.Connection,
    *,
    name: str,
    asset_type: str = "other",
    institution: str = "SBI証券",
    account_type: str = "",
    memo: str | None = None,
) -> tuple[int, str]:
    display_name = str(name or "").strip()
    if not display_name:
        raise ValueError("name is required")
    normalized_name_key = normalize_asset_fund_name(display_name)
    if not normalized_name_key:
        raise ValueError("name is required")
    normalized_institution = str(institution or "").strip() or "SBI証券"
    normalized_account_type = str(account_type or "").strip() or "未分類"
    normalized_asset_type = _normalize_asset_type(asset_type)
    normalized_memo = str(memo or "").strip() or None
    now = utc_now_iso()

    existing = conn.execute(
        """
        SELECT id, asset_type, memo
        FROM asset_products
        WHERE name = ? AND institution = ? AND account_type = ?
        """,
        (display_name, normalized_institution, normalized_account_type),
    ).fetchone()
    if existing is None:
        candidates = conn.execute(
            """
            SELECT id, name, asset_type, memo
            FROM asset_products
            WHERE institution = ? AND account_type = ?
            ORDER BY id
            """,
            (normalized_institution, normalized_account_type),
        ).fetchall()
        for row in candidates:
            if normalize_asset_fund_name(str(row["name"] or "")) == normalized_name_key:
                existing = row
                break
    if existing:
        updates: list[str] = []
        params: list[Any] = []
        if str(existing["asset_type"] or "") != normalized_asset_type:
            updates.append("asset_type = ?")
            params.append(normalized_asset_type)
        if (existing["memo"] or None) != normalized_memo:
            updates.append("memo = ?")
            params.append(normalized_memo)
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(int(existing["id"]))
            conn.execute(f"UPDATE asset_products SET {', '.join(updates)} WHERE id = ?", params)
            return int(existing["id"]), "updated"
        return int(existing["id"]), "skipped"

    cur = conn.execute(
        """
        INSERT INTO asset_products(name, asset_type, institution, account_type, memo, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            display_name,
            normalized_asset_type,
            normalized_institution,
            normalized_account_type,
            normalized_memo,
            now,
            now,
        ),
    )
    return int(cur.lastrowid), "inserted"


def upsert_asset_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> str:
    asset_id = int(snapshot["asset_id"])
    valuation_date = str(snapshot["valuation_date"]).strip()
    if not valuation_date:
        raise ValueError("valuation_date is required")
    period_month = normalize_period_month(str(snapshot.get("period_month") or period_month_from_date(valuation_date)))
    source = _normalize_asset_source(snapshot.get("source"))
    now = utc_now_iso()

    payload = {
        "valuation_date": valuation_date,
        "period_month": period_month,
        "quantity": _to_float_or_none(snapshot.get("quantity")),
        "base_price": _to_float_or_none(snapshot.get("base_price")),
        "acquisition_price": _to_float_or_none(snapshot.get("acquisition_price")),
        "current_value_yen": _to_int_or_none(snapshot.get("current_value_yen")) or 0,
        "invested_amount_yen": _to_int_or_none(snapshot.get("invested_amount_yen")),
        "profit_loss_yen": _to_int_or_none(snapshot.get("profit_loss_yen")),
        "profit_loss_rate": _to_float_or_none(snapshot.get("profit_loss_rate")),
        "daily_change_yen": _to_int_or_none(snapshot.get("daily_change_yen")),
        "daily_change_rate": _to_float_or_none(snapshot.get("daily_change_rate")),
        "dividend_method": (str(snapshot.get("dividend_method") or "").strip() or None),
        "source": source,
    }
    if payload["current_value_yen"] < 0:
        raise ValueError("current_value_yen must be >= 0")

    existing = conn.execute(
        "SELECT * FROM asset_snapshots WHERE asset_id = ? AND period_month = ?",
        (asset_id, period_month),
    ).fetchone()
    if existing:
        changed = False
        for key, value in payload.items():
            if (existing[key] if key in existing.keys() else None) != value:
                changed = True
                break
        if not changed:
            return "skipped"
        conn.execute(
            """
            UPDATE asset_snapshots
            SET valuation_date = ?, quantity = ?, base_price = ?, acquisition_price = ?,
                current_value_yen = ?, invested_amount_yen = ?, profit_loss_yen = ?, profit_loss_rate = ?,
                daily_change_yen = ?, daily_change_rate = ?, dividend_method = ?, source = ?, updated_at = ?
            WHERE asset_id = ? AND period_month = ?
            """,
            (
                payload["valuation_date"],
                payload["quantity"],
                payload["base_price"],
                payload["acquisition_price"],
                payload["current_value_yen"],
                payload["invested_amount_yen"],
                payload["profit_loss_yen"],
                payload["profit_loss_rate"],
                payload["daily_change_yen"],
                payload["daily_change_rate"],
                payload["dividend_method"],
                payload["source"],
                now,
                asset_id,
                period_month,
            ),
        )
        return "updated"

    conn.execute(
        """
        INSERT INTO asset_snapshots(
            asset_id, valuation_date, period_month, quantity, base_price, acquisition_price,
            current_value_yen, invested_amount_yen, profit_loss_yen, profit_loss_rate,
            daily_change_yen, daily_change_rate, dividend_method, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            payload["valuation_date"],
            payload["period_month"],
            payload["quantity"],
            payload["base_price"],
            payload["acquisition_price"],
            payload["current_value_yen"],
            payload["invested_amount_yen"],
            payload["profit_loss_yen"],
            payload["profit_loss_rate"],
            payload["daily_change_yen"],
            payload["daily_change_rate"],
            payload["dividend_method"],
            payload["source"],
            now,
            now,
        ),
    )
    return "inserted"


def add_asset_purchase(conn: sqlite3.Connection, purchase: dict[str, Any]) -> dict[str, Any]:
    asset_id = int(purchase["asset_id"])
    purchase_date = str(purchase["purchase_date"]).strip()
    if not purchase_date:
        raise ValueError("purchase_date is required")
    period_month = normalize_period_month(str(purchase.get("period_month") or period_month_from_date(purchase_date)))
    amount_yen = _to_int_or_none(purchase.get("amount_yen"))
    if amount_yen is None or amount_yen <= 0:
        raise ValueError("amount_yen must be greater than zero")
    source = _normalize_asset_source(purchase.get("source"))
    now = utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO asset_purchases(
            asset_id, purchase_date, period_month, amount_yen, quantity, unit_price, settlement_date, memo, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            purchase_date,
            period_month,
            amount_yen,
            _to_float_or_none(purchase.get("quantity")),
            _to_float_or_none(purchase.get("unit_price")),
            (str(purchase.get("settlement_date") or "").strip() or None),
            (str(purchase.get("memo") or "").strip() or None),
            source,
            now,
            now,
        ),
    )
    return {"id": int(cur.lastrowid), "asset_id": asset_id, "period_month": period_month, "amount_yen": amount_yen}


def upsert_fund_price_source(conn: sqlite3.Connection, source: dict[str, Any]) -> str:
    fund_name = str(source.get("fund_name") or "").strip()
    normalized_fund_name = normalize_asset_fund_name(fund_name)
    provider_name = str(source.get("provider_name") or "").strip()
    source_url = str(source.get("source_url") or "").strip()
    source_type = str(source.get("source_type") or "").strip()
    if source_type == "official_html":
        source_type = "official_public_data"
    parser_name = str(source.get("parser_name") or "").strip()
    if not normalized_fund_name:
        raise ValueError("fund_name is required")
    if not provider_name:
        raise ValueError("provider_name is required")
    if not source_url:
        raise ValueError("source_url is required")
    if source_type not in FUND_PRICE_SOURCE_TYPES:
        raise ValueError("source_type is invalid")
    if not parser_name:
        raise ValueError("parser_name is required")
    is_active = 1 if bool(source.get("is_active", True)) else 0
    now = utc_now_iso()
    existing = conn.execute(
        """
        SELECT id, source_type, parser_name, is_active
        FROM fund_price_sources
        WHERE fund_name = ? AND provider_name = ? AND source_url = ?
        """,
        (fund_name, provider_name, source_url),
    ).fetchone()
    if existing is None:
        rows = conn.execute(
            """
            SELECT id, fund_name, source_type, parser_name, is_active
            FROM fund_price_sources
            WHERE provider_name = ? AND source_url = ?
            ORDER BY id
            """,
            (provider_name, source_url),
        ).fetchall()
        for row in rows:
            if normalize_asset_fund_name(str(row["fund_name"] or "")) == normalized_fund_name:
                existing = row
                break
    if existing:
        if (
            str(existing["source_type"]) == source_type
            and str(existing["parser_name"]) == parser_name
            and int(existing["is_active"]) == is_active
        ):
            return "skipped"
        conn.execute(
            """
            UPDATE fund_price_sources
            SET source_type = ?, parser_name = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (source_type, parser_name, is_active, now, int(existing["id"])),
        )
        return "updated"
    conn.execute(
        """
        INSERT INTO fund_price_sources(
            fund_name, provider_name, source_url, source_type, parser_name, is_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (fund_name, provider_name, source_url, source_type, parser_name, is_active, now, now),
    )
    return "inserted"


def list_fund_price_sources(conn: sqlite3.Connection, *, active_only: bool = True) -> list[dict[str, Any]]:
    sql = """
        SELECT id, fund_name, provider_name, source_url, source_type, parser_name, is_active, created_at, updated_at
        FROM fund_price_sources
    """
    params: list[Any] = []
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY fund_name, id"
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def upsert_fund_nav_price(conn: sqlite3.Connection, price: dict[str, Any]) -> str:
    fund_name = str(price.get("fund_name") or "").strip()
    normalized_fund_name = normalize_asset_fund_name(fund_name)
    price_date = str(price.get("price_date") or "").strip()
    provider_name = str(price.get("provider_name") or "").strip()
    source_url = str(price.get("source_url") or "").strip()
    if not normalized_fund_name:
        raise ValueError("fund_name is required")
    if not price_date:
        raise ValueError("price_date is required")
    if not provider_name:
        raise ValueError("provider_name is required")
    if not source_url:
        raise ValueError("source_url is required")
    base_price = _to_float_or_none(price.get("base_price"))
    if base_price is None or base_price <= 0:
        raise ValueError("base_price must be greater than zero")
    now = utc_now_iso()
    fetched_at = str(price.get("fetched_at") or now).strip() or now
    existing = conn.execute(
        """
        SELECT id, base_price, source_url
        FROM fund_nav_prices
        WHERE fund_name = ? AND price_date = ? AND provider_name = ?
        """,
        (fund_name, price_date, provider_name),
    ).fetchone()
    if existing is None:
        rows = conn.execute(
            """
            SELECT id, fund_name, base_price, source_url
            FROM fund_nav_prices
            WHERE price_date = ? AND provider_name = ?
            ORDER BY id
            """,
            (price_date, provider_name),
        ).fetchall()
        for row in rows:
            if normalize_asset_fund_name(str(row["fund_name"] or "")) == normalized_fund_name:
                existing = row
                break
    if existing:
        if float(existing["base_price"]) == float(base_price) and str(existing["source_url"] or "") == source_url:
            return "skipped"
        conn.execute(
            """
            UPDATE fund_nav_prices
            SET base_price = ?, source_url = ?, fetched_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (base_price, source_url, fetched_at, now, int(existing["id"])),
        )
        return "updated"
    conn.execute(
        """
        INSERT INTO fund_nav_prices(
            fund_name, price_date, base_price, provider_name, source_url, fetched_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (fund_name, price_date, base_price, provider_name, source_url, fetched_at, now, now),
    )
    return "inserted"


def list_fund_nav_prices(
    conn: sqlite3.Connection,
    *,
    fund_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if fund_name:
        where.append("fund_name = ?")
        params.append(str(fund_name).strip())
    if date_from:
        where.append("price_date >= ?")
        params.append(str(date_from).strip())
    if date_to:
        where.append("price_date <= ?")
        params.append(str(date_to).strip())
    sql = """
        SELECT id, fund_name, price_date, base_price, provider_name, source_url, fetched_at, created_at, updated_at
        FROM fund_nav_prices
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY fund_name, price_date"
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def add_asset_trade(conn: sqlite3.Connection, trade: dict[str, Any]) -> dict[str, Any]:
    trade_date = str(trade.get("trade_date") or "").strip()
    fund_name = str(trade.get("fund_name") or "").strip()
    if fund_name:
        if not normalize_asset_fund_name(fund_name):
            raise ValueError("fund_name is required")
    institution = str(trade.get("institution") or "").strip()
    account_type = str(trade.get("account_type") or "").strip()
    trade_type = str(trade.get("trade_type") or "").strip()
    source = str(trade.get("source") or "").strip() or "manual"
    if not trade_date:
        raise ValueError("trade_date is required")
    if not fund_name:
        raise ValueError("fund_name is required")
    if not institution:
        raise ValueError("institution is required")
    if not account_type:
        raise ValueError("account_type is required")
    if trade_type not in {"buy", "sell", "dividend_reinvest", "other"}:
        raise ValueError("trade_type is invalid")
    if source not in {"csv", "manual"}:
        raise ValueError("source is invalid")
    now = utc_now_iso()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO asset_trades(
            trade_date, settlement_date, fund_name, institution, account_type, trade_type,
            quantity, unit_price, amount_yen, source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade_date,
            str(trade.get("settlement_date") or "").strip() or None,
            fund_name,
            institution,
            account_type,
            trade_type,
            _to_float_or_none(trade.get("quantity")),
            _to_float_or_none(trade.get("unit_price")),
            _to_int_or_none(trade.get("amount_yen")),
            source,
            now,
            now,
        ),
    )
    if cur.lastrowid:
        return {"id": int(cur.lastrowid), "status": "inserted"}
    return {"id": None, "status": "skipped"}


def list_asset_trades(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if date_from:
        where.append("trade_date >= ?")
        params.append(str(date_from).strip())
    if date_to:
        where.append("trade_date <= ?")
        params.append(str(date_to).strip())
    sql = """
        SELECT
            id, trade_date, settlement_date, fund_name, institution, account_type, trade_type,
            quantity, unit_price, amount_yen, source, created_at, updated_at
        FROM asset_trades
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY trade_date, id"
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def asset_period_bounds(conn: sqlite3.Connection) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT
            MIN(period_month) AS min_month,
            MAX(period_month) AS max_month
        FROM asset_snapshots
        """
    ).fetchone()
    today = date.today()
    default_month = f"{today.year:04d}-{today.month:02d}"
    min_month = str(row["min_month"] or default_month)
    max_month = str(row["max_month"] or default_month)
    return {
        "min_month": min_month,
        "max_month": max_month,
        "min_year": min_month[0:4],
        "max_year": max_month[0:4],
    }


def asset_monthly_series(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    snapshot_rows = _effective_asset_snapshot_rows(conn)
    by_month: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in snapshot_rows:
        by_month[str(row["period_month"])].append(row)

    purchase_rows = conn.execute(
        """
        SELECT period_month, SUM(amount_yen) AS purchase_amount_yen
        FROM (
            SELECT period_month, amount_yen
            FROM asset_purchases
            UNION ALL
            SELECT substr(trade_date, 1, 7) AS period_month, COALESCE(amount_yen, 0) AS amount_yen
            FROM asset_trades
            WHERE trade_type IN ('buy', 'dividend_reinvest')
        ) x
        GROUP BY period_month
        """
    ).fetchall()
    purchase_by_month = {str(row["period_month"]): int(row["purchase_amount_yen"] or 0) for row in purchase_rows}

    result: list[dict[str, Any]] = []
    previous_value: int | None = None
    for period_month in sorted(by_month.keys()):
        month_rows = by_month[period_month]
        valuation_date = max(str(row["valuation_date"] or "") for row in month_rows)
        current_value = sum(int(row["current_value_yen"] or 0) for row in month_rows)
        invested_amount = sum(int(row["invested_amount_yen"] or 0) for row in month_rows)
        profit_loss = sum(int(row["profit_loss_yen"] or (int(row["current_value_yen"] or 0) - int(row["invested_amount_yen"] or 0))) for row in month_rows)
        purchase_amount = purchase_by_month.get(period_month, 0)
        profit_loss_rate = (profit_loss / invested_amount * 100.0) if invested_amount > 0 else None

        month_change_yen: int | None = None
        month_change_rate: float | None = None
        operation_change_yen: int | None = None
        operation_change_rate: float | None = None
        if previous_value is not None and previous_value > 0:
            month_change_yen = current_value - previous_value
            month_change_rate = month_change_yen / previous_value * 100.0
            operation_change_yen = month_change_yen - purchase_amount
            operation_change_rate = operation_change_yen / previous_value * 100.0

        measured_count = sum(1 for row in month_rows if _asset_source_priority(str(row["source"] or "")) == 0)
        generated_count = len(month_rows) - measured_count
        result.append(
            {
                "period_month": period_month,
                "valuation_date": valuation_date,
                "current_value_yen": current_value,
                "invested_amount_yen": invested_amount,
                "profit_loss_yen": profit_loss,
                "profit_loss_rate": round(profit_loss_rate, 4) if profit_loss_rate is not None else None,
                "previous_value_yen": previous_value,
                "month_change_yen": month_change_yen,
                "month_change_rate": round(month_change_rate, 4) if month_change_rate is not None else None,
                "purchase_amount_yen": purchase_amount,
                "operation_change_yen": operation_change_yen,
                "operation_change_rate": round(operation_change_rate, 4) if operation_change_rate is not None else None,
                "holding_count": len(month_rows),
                "measured_count": measured_count,
                "generated_count": generated_count,
            }
        )
        previous_value = current_value
    return result


def _build_axis_ticks(values: list[int]) -> list[int]:
    if not values:
        return [0, 0, 0, 0, 0]
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        span = max(1, abs(maximum))
        minimum -= span
        maximum += span
    step = (maximum - minimum) / 4.0
    ticks = [int(round(minimum + step * idx)) for idx in range(5)]
    ticks[0] = minimum
    ticks[-1] = maximum
    return ticks


def asset_monthly_chart_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    monthly = asset_monthly_series(conn)
    axis = {
        "value": _build_axis_ticks([int(row["current_value_yen"]) for row in monthly]),
        "change": _build_axis_ticks([int(row["month_change_yen"] or 0) for row in monthly]),
        "purchase": _build_axis_ticks([int(row["purchase_amount_yen"] or 0) for row in monthly]),
        "operation": _build_axis_ticks([int(row["operation_change_yen"] or 0) for row in monthly]),
    }
    return {"monthly": monthly, "axis": axis}


def asset_summary_for_month(conn: sqlite3.Connection, period_month: str | None = None) -> dict[str, Any]:
    series = asset_monthly_series(conn)
    bounds = asset_period_bounds(conn)
    if not series:
        target = period_month or bounds["max_month"]
        return {
            "period_month": target,
            "has_data": False,
            "valuation_date": "",
            "current_value_yen": 0,
            "invested_amount_yen": 0,
            "profit_loss_yen": 0,
            "profit_loss_rate": None,
            "previous_value_yen": None,
            "month_change_yen": None,
            "month_change_rate": None,
            "purchase_amount_yen": 0,
            "operation_change_yen": None,
            "operation_change_rate": None,
            "holding_count": 0,
            "measured_count": 0,
            "generated_count": 0,
            "bounds": bounds,
        }
    target_period = normalize_period_month(period_month) if period_month else series[-1]["period_month"]
    selected = next((row for row in series if row["period_month"] == target_period), None)
    if selected is None:
        selected = series[-1]
    return dict(selected) | {"has_data": True, "bounds": bounds}


def _percent_display_flags(start_value: int, start_period_month: str, *, required_start_month: int) -> tuple[bool, str | None]:
    if start_value < MIN_BASE_VALUE_FOR_PERCENT:
        return (False, "base_too_small")
    month = int(start_period_month[5:7])
    if month != required_start_month:
        return (False, "incomplete_start_period")
    return (True, None)


def _bucket_period_rows(
    series: list[dict[str, Any]],
    *,
    period_kind: str,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in series:
        period_month = str(row["period_month"])
        year = int(period_month[0:4])
        month = int(period_month[5:7])
        if period_kind == "fiscal":
            label = str(year if month >= FISCAL_YEAR_START_MONTH else year - 1)
        else:
            label = str(year)
        buckets.setdefault(label, []).append(row)
    return buckets


def _summarize_period_bucket(
    label: str,
    rows: list[dict[str, Any]],
    *,
    latest_period: str,
    period_kind: str,
) -> dict[str, Any]:
    start_period = str(rows[0]["period_month"])
    end_period = str(rows[-1]["period_month"])
    start_value = int(rows[0]["current_value_yen"])
    end_value = int(rows[-1]["current_value_yen"])
    total_purchase = sum(int(row["purchase_amount_yen"]) for row in rows)
    total_change = end_value - start_value
    total_operation = total_change - total_purchase

    required_start_month = FISCAL_YEAR_START_MONTH if period_kind == "fiscal" else 1
    percent_available, percent_unavailable_reason = _percent_display_flags(
        start_value,
        start_period,
        required_start_month=required_start_month,
    )
    total_change_rate = (total_change / start_value * 100.0) if percent_available and start_value > 0 else None
    total_operation_rate = (total_operation / start_value * 100.0) if percent_available and start_value > 0 else None

    latest_year = int(latest_period[0:4])
    latest_month = int(latest_period[5:7])
    if period_kind == "fiscal":
        latest_label = str(latest_year if latest_month >= FISCAL_YEAR_START_MONTH else latest_year - 1)
        is_ytd = label == latest_label and latest_month != 3
    else:
        is_ytd = label == str(latest_year) and latest_month != 12

    return {
        "period_kind": period_kind,
        "label": label,
        "year": label,
        "start_period_month": start_period,
        "end_period_month": end_period,
        "start_value_yen": start_value,
        "end_value_yen": end_value,
        "purchase_amount_yen": total_purchase,
        "total_change_yen": total_change,
        "total_change_rate": round(total_change_rate, 4) if total_change_rate is not None else None,
        "operation_change_yen": total_operation,
        "operation_change_rate": round(total_operation_rate, 4) if total_operation_rate is not None else None,
        "percent_available": percent_available,
        "percent_unavailable_reason": percent_unavailable_reason,
        "is_ytd": is_ytd,
    }


def _asset_period_performance(conn: sqlite3.Connection, *, period_kind: str) -> list[dict[str, Any]]:
    series = asset_monthly_series(conn)
    if not series:
        return []
    by_period = _bucket_period_rows(series, period_kind=period_kind)
    latest_period = str(series[-1]["period_month"])
    items: list[dict[str, Any]] = []
    for label in sorted(by_period.keys()):
        rows = by_period[label]
        items.append(
            _summarize_period_bucket(
                label,
                rows,
                latest_period=latest_period,
                period_kind=period_kind,
            )
        )
    return sorted(items, key=lambda row: row["label"], reverse=True)


def asset_yearly_performance(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _asset_period_performance(conn, period_kind="calendar")


def asset_fiscal_year_performance(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _asset_period_performance(conn, period_kind="fiscal")


def previous_period_month(period_month: str) -> str:
    year, month = [int(x) for x in period_month.split("-")]
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def asset_holdings_for_month(conn: sqlite3.Connection, period_month: str | None = None) -> dict[str, Any]:
    target_period = normalize_period_month(period_month) if period_month else None
    if target_period is None:
        row = conn.execute("SELECT MAX(period_month) AS period_month FROM asset_snapshots").fetchone()
        target_period = str(row["period_month"] or "")
    if not target_period:
        target_period = asset_period_bounds(conn)["max_month"]
    prev_period = previous_period_month(target_period)
    rows = _effective_asset_snapshot_rows(conn, period_month=target_period)
    prev_rows = _effective_asset_snapshot_rows(conn, period_month=prev_period)
    prev_by_key: dict[tuple[str, str, str], int] = {}
    for row in prev_rows:
        prev_key = (
            normalize_asset_fund_name(str(row["name"] or "")),
            str(row["institution"] or ""),
            str(row["account_type"] or ""),
        )
        prev_by_key[prev_key] = int(row["current_value_yen"] or 0)

    purchase_by_key: dict[tuple[str, str, str], int] = {}
    purchase_rows = conn.execute(
        """
        SELECT p.name, p.institution, p.account_type, SUM(a.amount_yen) AS purchase_amount_yen
        FROM asset_purchases a
        JOIN asset_products p ON p.id = a.asset_id
        WHERE a.period_month = ?
        GROUP BY p.name, p.institution, p.account_type
        """,
        (target_period,),
    ).fetchall()
    for row in purchase_rows:
        purchase_key = (
            normalize_asset_fund_name(str(row["name"] or "")),
            str(row["institution"] or ""),
            str(row["account_type"] or ""),
        )
        purchase_by_key[purchase_key] = int(row["purchase_amount_yen"] or 0)

    trade_rows = conn.execute(
        """
        SELECT fund_name, institution, account_type, SUM(amount_yen) AS purchase_amount_yen
        FROM asset_trades
        WHERE substr(trade_date, 1, 7) = ?
          AND trade_type IN ('buy', 'dividend_reinvest')
        GROUP BY fund_name, institution, account_type
        """,
        (target_period,),
    ).fetchall()
    for row in trade_rows:
        purchase_key = (
            normalize_asset_fund_name(str(row["fund_name"] or "")),
            str(row["institution"] or ""),
            str(row["account_type"] or ""),
        )
        purchase_by_key[purchase_key] = purchase_by_key.get(purchase_key, 0) + int(row["purchase_amount_yen"] or 0)

    holdings: list[dict[str, Any]] = []
    for row in rows:
        current_value = int(row["current_value_yen"] or 0)
        invested_amount = int(row["invested_amount_yen"] or 0)
        profit_loss = int(row["profit_loss_yen"] or (current_value - invested_amount))
        profit_loss_rate = (
            float(row["profit_loss_rate"])
            if row["profit_loss_rate"] is not None
            else (profit_loss / invested_amount * 100.0 if invested_amount > 0 else None)
        )
        row_key = (
            normalize_asset_fund_name(str(row["name"] or "")),
            str(row["institution"] or ""),
            str(row["account_type"] or ""),
        )
        previous_value = prev_by_key.get(row_key)
        purchase_amount = int(purchase_by_key.get(row_key, 0))
        month_change = (current_value - previous_value) if previous_value is not None else None
        month_change_rate = (month_change / previous_value * 100.0) if previous_value else None
        operation_change = (month_change - purchase_amount) if month_change is not None else None
        source = str(row["source"] or "")
        holdings.append(
            {
                "asset_id": int(row["asset_id"]),
                "name": str(row["name"] or ""),
                "asset_type": str(row["asset_type"] or ""),
                "institution": str(row["institution"] or ""),
                "account_type": str(row["account_type"] or ""),
                "valuation_date": str(row["valuation_date"] or ""),
                "quantity": _to_float_or_none(row["quantity"]),
                "base_price": _to_float_or_none(row["base_price"]),
                "acquisition_price": _to_float_or_none(row["acquisition_price"]),
                "current_value_yen": current_value,
                "previous_value_yen": previous_value,
                "month_change_yen": month_change,
                "month_change_rate": round(month_change_rate, 4) if month_change_rate is not None else None,
                "purchase_amount_yen": purchase_amount,
                "operation_change_yen": operation_change,
                "invested_amount_yen": invested_amount,
                "profit_loss_yen": profit_loss,
                "profit_loss_rate": round(profit_loss_rate, 4) if profit_loss_rate is not None else None,
                "source": source,
                "source_label": "実測" if _asset_source_priority(source) == 0 else "生成",
                "normalized_name": row_key[0],
            }
        )
    holdings.sort(
        key=lambda item: (
            -int(item["current_value_yen"]),
            str(item["normalized_name"]),
            str(item["account_type"]),
        )
    )
    for item in holdings:
        item.pop("normalized_name", None)
    return {"period_month": target_period, "previous_period_month": prev_period, "holdings": holdings}
