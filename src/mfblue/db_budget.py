"""Budget transaction persistence and aggregation."""

from .db_common import *  # noqa: F401,F403

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


