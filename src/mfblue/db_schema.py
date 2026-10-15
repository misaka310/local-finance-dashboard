"""SQLite schema initialization and migrations."""

from .db_common import *  # noqa: F401,F403
from .db_budget import (
    normalize_negative_transactions,
    normalize_system_accounts,
)

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


