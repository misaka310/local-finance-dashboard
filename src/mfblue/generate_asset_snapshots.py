from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .asset_fund_names import normalize_asset_fund_name
from .db import (
    connect,
    ensure_asset_product,
    init_db,
    list_asset_trades,
    upsert_asset_snapshot,
)


@dataclass
class HoldingState:
    quantity: float = 0.0
    invested_amount: float = 0.0


def _source_priority(source: str | None) -> int:
    return 0 if str(source or "").strip().lower() in {"manual", "csv"} else 1


def parse_iso_date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def month_token(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def iter_months(start_month: date, end_month: date) -> list[date]:
    months: list[date] = []
    y, m = start_month.year, start_month.month
    while (y, m) <= (end_month.year, end_month.month):
        months.append(date(y, m, 1))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return months


def select_nav_price(
    nav_rows: list[dict[str, Any]],
    *,
    target_month_end: date,
) -> tuple[str, float] | None:
    selected: tuple[str, float] | None = None
    month_prefix = month_token(target_month_end)
    for row in nav_rows:
        price_date = str(row["price_date"])
        if not price_date.startswith(month_prefix):
            continue
        if price_date <= target_month_end.isoformat():
            selected = (price_date, float(row["base_price"]))
    return selected


def apply_trade(state: HoldingState, trade: dict[str, Any]) -> None:
    trade_type = str(trade.get("trade_type") or "")
    quantity = float(trade.get("quantity") or 0.0)
    amount = float(trade.get("amount_yen") or 0.0)
    if trade_type in {"buy", "dividend_reinvest"}:
        if quantity <= 0:
            return
        state.quantity += quantity
        if amount > 0:
            state.invested_amount += amount
        return
    if trade_type == "sell":
        if quantity <= 0 or state.quantity <= 0:
            return
        sell_qty = min(quantity, state.quantity)
        avg_cost_per_unit = state.invested_amount / state.quantity if state.quantity > 0 else 0
        state.quantity -= sell_qty
        state.invested_amount -= avg_cost_per_unit * sell_qty
        if state.quantity <= 0:
            state.quantity = 0.0
            state.invested_amount = 0.0
        if state.invested_amount < 0:
            state.invested_amount = 0.0


def generate_snapshots(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    force_generated: bool = False,
    db_path: Path | None = None,
) -> dict[str, int]:
    now = date.today()
    output_from = month_start(parse_iso_date(date_from)) if date_from else None
    output_to_date = parse_iso_date(date_to) if date_to else now
    output_to = month_start(output_to_date)
    totals = {
        "months": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "protected": 0,
        "errors": 0,
    }

    conn = connect(db_path)
    try:
        init_db(conn)
        trades = list_asset_trades(conn, date_to=output_to_date.isoformat())
        if not trades:
            return totals
        trades.sort(key=lambda row: (str(row["trade_date"]), int(row["id"])))

        first_trade_date = parse_iso_date(str(trades[0]["trade_date"]))
        calc_from = month_start(first_trade_date)
        calc_to = output_to
        if output_from and output_from < calc_from:
            calc_from = output_from
        if calc_to < calc_from:
            calc_to = calc_from

        output_from = output_from or calc_from
        months = iter_months(calc_from, calc_to)
        totals["months"] = len([m for m in months if m >= output_from])

        nav_rows = conn.execute(
            """
            SELECT fund_name, price_date, base_price
            FROM fund_nav_prices
            WHERE price_date <= ?
            ORDER BY price_date ASC, id ASC
            """,
            (month_end(calc_to).isoformat(),),
        ).fetchall()
        nav_by_fund: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in nav_rows:
            nav_by_fund[normalize_asset_fund_name(str(row["fund_name"] or ""))].append(dict(row))

        existing_snapshot_rows = conn.execute(
            """
            SELECT
                s.period_month,
                p.name,
                p.institution,
                p.account_type,
                s.source
            FROM asset_snapshots s
            JOIN asset_products p ON p.id = s.asset_id
            """
        ).fetchall()
        existing_sources: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
        measured_account_months: set[tuple[str, str, str]] = set()
        measured_months: set[str] = set()
        for row in existing_snapshot_rows:
            period = str(row["period_month"] or "")
            institution = str(row["institution"] or "")
            account_type = str(row["account_type"] or "")
            source = str(row["source"] or "")
            existing_sources[
                (
                    period,
                    normalize_asset_fund_name(str(row["name"] or "")),
                    institution,
                    account_type,
                )
            ].add(source)
            if _source_priority(source) == 0:
                measured_account_months.add((period, institution, account_type))
                measured_months.add(period)

        states: dict[tuple[str, str, str], HoldingState] = {}
        display_name_by_key: dict[tuple[str, str, str], str] = {}
        trade_idx = 0
        for month in months:
            end_of_month = month_end(month)
            while trade_idx < len(trades):
                trade_date = parse_iso_date(str(trades[trade_idx]["trade_date"]))
                if trade_date > end_of_month:
                    break
                trade = trades[trade_idx]
                normalized_fund_name = normalize_asset_fund_name(str(trade["fund_name"] or ""))
                if not normalized_fund_name:
                    trade_idx += 1
                    continue
                key = (
                    normalized_fund_name,
                    str(trade["institution"]),
                    str(trade["account_type"]),
                )
                state = states.setdefault(key, HoldingState())
                display_name_by_key.setdefault(key, str(trade["fund_name"] or "").strip())
                apply_trade(state, trade)
                trade_idx += 1

            if month < output_from:
                continue
            period = month_token(month)
            for (fund_name_key, institution, account_type), state in states.items():
                if state.quantity <= 0:
                    continue
                nav = select_nav_price(nav_by_fund.get(fund_name_key, []), target_month_end=end_of_month)
                if not nav:
                    totals["skipped"] += 1
                    continue
                valuation_date, base_price = nav
                current_value = int(round(state.quantity * base_price / 10000.0))
                invested_amount = int(round(state.invested_amount))
                profit_loss = current_value - invested_amount
                profit_loss_rate = (profit_loss / invested_amount * 100.0) if invested_amount > 0 else None
                acquisition_price = (state.invested_amount * 10000.0 / state.quantity) if state.quantity > 0 else None

                source_key = (period, fund_name_key, institution, account_type)
                if period in measured_months:
                    totals["protected"] += 1
                    continue
                if (period, institution, account_type) in measured_account_months:
                    totals["protected"] += 1
                    continue
                source_set = existing_sources.get(source_key, set())
                if any(_source_priority(source) == 0 for source in source_set):
                    totals["protected"] += 1
                    continue
                if "generated" in source_set and not force_generated:
                    totals["skipped"] += 1
                    continue

                asset_id, _ = ensure_asset_product(
                    conn,
                    name=display_name_by_key.get((fund_name_key, institution, account_type), fund_name_key),
                    asset_type="investment_trust",
                    institution=institution,
                    account_type=account_type,
                )

                status = upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": valuation_date,
                        "period_month": period,
                        "quantity": round(state.quantity, 4),
                        "base_price": base_price,
                        "acquisition_price": acquisition_price,
                        "current_value_yen": current_value,
                        "invested_amount_yen": invested_amount,
                        "profit_loss_yen": profit_loss,
                        "profit_loss_rate": profit_loss_rate,
                        "source": "generated",
                    },
                )
                totals[status] += 1
                existing_sources[source_key].add("generated")
        conn.commit()
    finally:
        conn.close()
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate monthly asset snapshots from asset_trades + fund_nav_prices.")
    parser.add_argument("--from", dest="date_from", help="from date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="to date (YYYY-MM-DD)")
    parser.add_argument("--force-generated", action="store_true", help="update existing generated snapshots")
    parser.add_argument("--db-path", help="override sqlite path")
    args = parser.parse_args(argv)
    result = generate_snapshots(
        date_from=args.date_from,
        date_to=args.date_to,
        force_generated=args.force_generated,
        db_path=Path(args.db_path) if args.db_path else None,
    )
    print("Asset snapshot generation completed.")
    print(
        f"months: {result['months']} / inserted: {result['inserted']} / updated: {result['updated']} / "
        f"skipped: {result['skipped']} / protected: {result['protected']} / errors: {result['errors']}"
    )
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
