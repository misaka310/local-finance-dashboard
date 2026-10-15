"""Asset holdings, prices, trades, snapshots, and performance queries."""

from .db_common import *  # noqa: F401,F403

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
