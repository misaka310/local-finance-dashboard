from __future__ import annotations

import traceback
from datetime import date
from urllib.parse import parse_qs, urlparse

from .account_groups import resolve_account_filter
from .analysis import AnalysisError, get_analysis_if_exists, resolve_period, run_or_reuse_analysis
from .config import load_config
from .db import (
    MIN_BASE_VALUE_FOR_PERCENT,
    add_asset_purchase,
    asset_fiscal_year_performance,
    asset_holdings_for_month,
    asset_monthly_chart_payload,
    asset_summary_for_month,
    asset_yearly_performance,
    available_period_bounds,
    db,
    init_db,
    list_asset_products,
    list_available_accounts,
    list_categories,
    summary_for_period,
    transactions_for_period,
    update_transaction_category,
)
from .fetch_fund_nav_prices import fetch_nav_prices
from .generate_asset_snapshots import generate_snapshots
from .repair_asset_snapshot_duplicates import repair_asset_snapshot_duplicates

def current_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def handle_get(self):  # noqa: N802
    parsed = urlparse(self.path)
    path = parsed.path
    qs = parse_qs(parsed.query)
    try:
        if path in {"/api/summary", "/api/year-summary"}:
            month = qs.get("month", [None])[0]
            year = qs.get("year", [None])[0]
            direction = qs.get("direction", ["expense"])[0]
            show_sub = qs.get("show_subcategories", ["false"])[0].lower() == "true"
            account_id = qs.get("account_id", [None])[0] or None
            account_group = qs.get("account_group", [None])[0] or None
            source_id = qs.get("source_id", [None])[0] or None
            resolved_account_id, account_ids = resolve_account_filter(
                account_id=account_id,
                account_group=account_group,
            )
            with db() as conn:
                init_db(conn)
                if path == "/api/year-summary" and not year:
                    self.send_error_json("year is required", status=400)
                    return
                if not year and not month:
                    month = current_month()
                self.send_json(
                    summary_for_period(
                        conn,
                        month=None if year else month,
                        year=year,
                        direction=direction,
                        show_subcategories=show_sub,
                        account_id=None if resolved_account_id == "all" else resolved_account_id,
                        account_ids=account_ids,
                        source_id=source_id,
                    )
                )
            return
        if path == "/api/transactions":
            month = qs.get("month", [None])[0]
            year = qs.get("year", [None])[0]
            direction = qs.get("direction", [None])[0]
            category_id = qs.get("category_id", [None])[0]
            subcategory = qs.get("subcategory", [None])[0]
            account_id = qs.get("account_id", [None])[0] or None
            account_group = qs.get("account_group", [None])[0] or None
            source_id = qs.get("source_id", [None])[0] or None
            resolved_account_id, account_ids = resolve_account_filter(
                account_id=account_id,
                account_group=account_group,
            )
            with db() as conn:
                init_db(conn)
                if not year and not month:
                    month = current_month()
                if year:
                    txs = transactions_for_period(
                        conn,
                        year=year,
                        category_id=category_id,
                        subcategory=subcategory,
                        direction=direction,
                        account_id=None if resolved_account_id == "all" else resolved_account_id,
                        account_ids=account_ids,
                        source_id=source_id,
                    )
                else:
                    txs = transactions_for_period(
                        conn,
                        month=month,
                        category_id=category_id,
                        subcategory=subcategory,
                        direction=direction,
                        account_id=None if resolved_account_id == "all" else resolved_account_id,
                        account_ids=account_ids,
                        source_id=source_id,
                    )
                self.send_json({"transactions": txs})
            return
        if path == "/api/accounts":
            with db() as conn:
                init_db(conn)
                self.send_json({"accounts": list_available_accounts(conn)})
            return
        if path == "/api/assets/products":
            with db() as conn:
                init_db(conn)
                self.send_json({"products": list_asset_products(conn)})
            return
        if path == "/api/assets/summary":
            period_month = qs.get("period_month", [None])[0]
            with db() as conn:
                init_db(conn)
                self.send_json(asset_summary_for_month(conn, period_month=period_month))
            return
        if path == "/api/assets/monthly":
            with db() as conn:
                init_db(conn)
                self.send_json(asset_monthly_chart_payload(conn))
            return
        if path == "/api/assets/yearly":
            with db() as conn:
                init_db(conn)
                self.send_json(
                    {
                        "yearly": asset_yearly_performance(conn),
                        "fiscal_yearly": asset_fiscal_year_performance(conn),
                        "percent_rules": {
                            "min_base_value_for_percent": MIN_BASE_VALUE_FOR_PERCENT,
                            "calendar_start_month": 1,
                            "fiscal_start_month": 4,
                        },
                    }
                )
            return
        if path == "/api/assets/holdings":
            period_month = qs.get("period_month", [None])[0]
            with db() as conn:
                init_db(conn)
                self.send_json(asset_holdings_for_month(conn, period_month=period_month))
            return
        if path == "/api/analysis":
            period_type = qs.get("period_type", [None])[0]
            month = qs.get("month", [None])[0]
            year = qs.get("year", [None])[0]
            account_id = qs.get("account_id", ["all"])[0] or "all"
            account_group = qs.get("account_group", [None])[0] or None
            direction = qs.get("direction", ["expense"])[0] or "expense"
            resolved_account_id, account_ids = resolve_account_filter(
                account_id=account_id,
                account_group=account_group,
            )
            if period_type not in {"month", "year"}:
                period_type = "year" if year else "month"
            with db() as conn:
                init_db(conn)
                period = resolve_period(period_type, month=month, year=year)
                result = get_analysis_if_exists(
                    conn,
                    config=load_config(),
                    period_type=period_type,
                    period=period,
                    account_id=resolved_account_id,
                    account_ids=account_ids,
                    direction=direction,
                )
                self.send_json(result)
            return
        if path == "/api/period-bounds":
            with db() as conn:
                init_db(conn)
                self.send_json(available_period_bounds(conn))
            return
        if path == "/api/categories":
            with db() as conn:
                init_db(conn)
                self.send_json({"categories": list_categories(conn)})
            return
        if path == "/api/status":
            cfg = load_config()
            with db() as conn:
                init_db(conn)
                row = conn.execute("SELECT * FROM import_runs ORDER BY id DESC LIMIT 1").fetchone()
                counts = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()
                self.send_json(
                    {
                        "app": cfg["app"]["name"],
                        "transaction_count": int(counts["n"]),
                        "last_import": dict(row) if row else None,
                    }
                )
            return
        self.serve_static(path)
    except AnalysisError as e:
        self.send_error_json(str(e), status=400)
    except ValueError as e:
        self.send_error_json(str(e), status=400)
    except Exception as e:
        self.send_error_json(str(e), status=500)

def handle_post(self):  # noqa: N802
    parsed = urlparse(self.path)
    try:
        if parsed.path == "/api/sync":
            from .sync_gmail import sync_once

            result = sync_once()
            self.send_json(result)
            return
        if parsed.path == "/api/analysis/run":
            payload = self.read_json()
            period_type = str(payload.get("period_type") or "")
            month = payload.get("month")
            year = payload.get("year")
            account_id = str(payload.get("account_id") or "all")
            account_group = payload.get("account_group")
            direction = str(payload.get("direction") or "expense")
            force = bool(payload.get("force", False))
            resolved_account_id, account_ids = resolve_account_filter(
                account_id=account_id,
                account_group=str(account_group) if account_group is not None else None,
            )
            if period_type not in {"month", "year"}:
                self.send_error_json("period_type must be month or year", status=400)
                return

            with db() as conn:
                init_db(conn)
                period = resolve_period(period_type, month=month, year=year)
                result = run_or_reuse_analysis(
                    conn,
                    config=load_config(),
                    period_type=period_type,
                    period=period,
                    account_id=resolved_account_id,
                    account_ids=account_ids,
                    direction=direction,
                    force=force,
                )
            response = {
                "status": result.get("status", "success"),
                "reused": bool(result.get("reused", False)),
                "stale": bool(result.get("stale", False)),
                "period_type": period_type,
                "period": period,
                "account_id": resolved_account_id,
                "direction": direction,
                "input_hash": result.get("input_hash"),
                "result_text": result.get("result_text"),
                "created_at": result.get("created_at"),
                "updated_at": result.get("updated_at"),
                "error_message": result.get("error_message"),
                "error_code": result.get("error_code"),
                "error_stage": result.get("error_stage"),
            }
            if response["status"] == "failed":
                self.send_json(response, status=503)
            else:
                self.send_json(response)
            return
        if parsed.path == "/api/assets/purchases":
            payload = self.read_json()
            asset_id = payload.get("asset_id")
            purchase_date = payload.get("purchase_date")
            amount_yen = payload.get("amount_yen")
            if asset_id is None:
                self.send_error_json("asset_id is required", status=400)
                return
            if not purchase_date:
                self.send_error_json("purchase_date is required", status=400)
                return
            if amount_yen is None:
                self.send_error_json("amount_yen is required", status=400)
                return
            with db() as conn:
                init_db(conn)
                saved = add_asset_purchase(
                    conn,
                    {
                        "asset_id": asset_id,
                        "purchase_date": purchase_date,
                        "period_month": payload.get("period_month"),
                        "amount_yen": amount_yen,
                        "quantity": payload.get("quantity"),
                        "unit_price": payload.get("unit_price"),
                        "settlement_date": payload.get("settlement_date"),
                        "memo": payload.get("memo"),
                        "source": payload.get("source") or "manual",
                    },
                )
            self.send_json({"status": "ok", "purchase": saved}, status=201)
            return
        if parsed.path == "/api/assets/refresh-prices":
            payload = self.read_json()
            requested_month = payload.get("period_month")
            date_from = payload.get("date_from")
            date_to = payload.get("date_to")
            force = bool(payload.get("force", False))

            verify_month: str | None = None
            with db() as conn:
                init_db(conn)
                before = asset_summary_for_month(conn, period_month=requested_month)
                verify_month = str(before.get("period_month") or requested_month or "")

            nav_result = fetch_nav_prices(
                date_from=str(date_from) if date_from else None,
                date_to=str(date_to) if date_to else None,
                force=force,
            )
            snapshot_result = generate_snapshots(
                date_from=str(date_from) if date_from else None,
                date_to=str(date_to) if date_to else None,
                force_generated=False,
            )
            repair_result = repair_asset_snapshot_duplicates(
                verify_month=verify_month or None,
            )

            with db() as conn:
                init_db(conn)
                summary = asset_summary_for_month(conn, period_month=verify_month or None)
                yearly = asset_yearly_performance(conn)
                fiscal_yearly = asset_fiscal_year_performance(conn)

            self.send_json(
                {
                    "status": "ok",
                    "nav_fetch": nav_result,
                    "snapshot_generate": snapshot_result,
                    "dedupe_repair": repair_result,
                    "summary": summary,
                    "yearly": yearly,
                    "fiscal_yearly": fiscal_yearly,
                }
            )
            return
        self.send_error_json("not found", status=404)
    except AnalysisError as e:
        self.send_error_json(str(e), status=400)
    except ValueError as e:
        self.send_error_json(str(e), status=400)
    except Exception as e:
        print(f"[server] unexpected error in POST {parsed.path}")
        traceback.print_exc()
        self.send_error_json(str(e), status=500)

def handle_patch(self):  # noqa: N802
    parsed = urlparse(self.path)
    try:
        if parsed.path.startswith("/api/transactions/"):
            transaction_id = int(parsed.path.rsplit("/", 1)[1])
            payload = self.read_json()
            category_id = payload.get("category_id")
            subcategory = payload.get("subcategory") or "未分類"
            learn_rule = bool(payload.get("learn_rule", True))
            apply_to_existing = bool(payload.get("apply_to_existing", False))
            if not category_id:
                self.send_error_json("category_id is required", status=400)
                return
            with db() as conn:
                init_db(conn)
                updated = update_transaction_category(
                    conn,
                    transaction_id,
                    category_id,
                    subcategory,
                    learn_rule=learn_rule,
                    apply_to_existing=apply_to_existing,
                )
            self.send_json({"status": "ok", "applied_count": updated.get("applied_count", 1)})
            return
        self.send_error_json("not found", status=404)
    except KeyError as e:
        self.send_error_json(str(e), status=404)
    except Exception as e:
        self.send_error_json(str(e), status=500)
