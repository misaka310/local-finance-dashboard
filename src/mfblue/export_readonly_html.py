from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .account_groups import ACCOUNT_GROUP_MEMBERS
from .config import database_path
from .db import (
    FUND_MOVEMENT_CATEGORY_ID,
    asset_fiscal_year_performance,
    asset_holdings_for_month,
    asset_monthly_chart_payload,
    asset_monthly_series,
    asset_period_bounds,
    asset_summary_for_month,
    asset_yearly_performance,
    connect,
    init_db,
    list_asset_products,
    list_categories,
)
from .paths import project_path

DEFAULT_HTML_PATH = project_path("dist", "readonly", "mfblue_readonly.html")
DEFAULT_ZIP_PATH = project_path("dist", "readonly", "mfblue_readonly.zip")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _month_value(date_str: str) -> str:
    return (date_str or "")[:7]


def _year_value(date_str: str) -> str:
    return (date_str or "")[:4]


def _load_period_options(conn) -> dict[str, Any]:
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

    min_month = str(row["min_month"] or "")
    max_month = str(row["max_month"] or "")
    min_year = str(row["min_year"] or "")
    max_year = str(row["max_year"] or "")

    months: list[str] = []
    if min_month and max_month:
        start_year, start_month = [int(x) for x in min_month.split("-")]
        end_year, end_month = [int(x) for x in max_month.split("-")]
        cursor = start_year * 12 + (start_month - 1)
        end_cursor = end_year * 12 + (end_month - 1)
        while cursor <= end_cursor:
            y = cursor // 12
            m = (cursor % 12) + 1
            months.append(f"{y:04d}-{m:02d}")
            cursor += 1

    years: list[str] = []
    if min_year and max_year:
        for year in range(int(min_year), int(max_year) + 1):
            years.append(f"{year:04d}")

    latest_month = max_month or datetime.now().strftime("%Y-%m")
    latest_year = max_year or latest_month[:4]
    return {
        "months": months,
        "years": years,
        "latest_month": latest_month,
        "latest_year": latest_year,
        "min_month": min_month or latest_month,
        "max_month": max_month or latest_month,
        "min_year": min_year or latest_year,
        "max_year": max_year or latest_year,
    }


def _load_transactions(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            t.id,
            t.occurred_at,
            t.merchant,
            t.amount_yen,
            t.direction,
            t.category_id,
            c.name AS category_name,
            t.subcategory,
            a.name AS account_name,
            t.account_id,
            CASE WHEN t.category_id = ? THEN 1 ELSE 0 END AS is_fund_movement
        FROM transactions t
        JOIN categories c ON c.id = t.category_id
        JOIN accounts a ON a.id = t.account_id
        ORDER BY t.occurred_at DESC, t.id DESC
        """,
        (FUND_MOVEMENT_CATEGORY_ID,),
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        occurred_at = str(row["occurred_at"] or "")
        merchant = str(row["merchant"] or "").strip() or "(店舗名未設定)"
        subcategory = str(row["subcategory"] or "").strip() or "未分類"
        result.append(
            {
                "id": int(row["id"]),
                "occurred_at": occurred_at,
                "month": _month_value(occurred_at),
                "year": _year_value(occurred_at),
                "merchant": merchant,
                "amount_yen": int(row["amount_yen"] or 0),
                "direction": str(row["direction"] or "expense"),
                "category_id": str(row["category_id"] or ""),
                "category_name": str(row["category_name"] or "未分類"),
                "subcategory": subcategory,
                "account_name": str(row["account_name"] or row["account_id"]),
                "account_id": str(row["account_id"] or ""),
                "is_fund_movement": bool(row["is_fund_movement"]),
            }
        )
    return result


def _load_account_filters(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, name FROM accounts").fetchall()
    name_by_id = {str(row["id"]): str(row["name"]) for row in rows}

    amazon_ids = list(ACCOUNT_GROUP_MEMBERS.get("amazon", ("amazon-order-history", "amazon-order")))
    paypay_label = name_by_id.get("paypay-card", "PayPayカード")

    return [
        {
            "id": "all",
            "label": "すべて",
            "account_ids": None,
            "analysis_account_ids": ["all"],
        },
        {
            "id": "paypay-card",
            "label": paypay_label,
            "account_ids": ["paypay-card"],
            "analysis_account_ids": ["paypay-card"],
        },
        {
            "id": "amazon",
            "label": "Amazon",
            "account_ids": amazon_ids,
            "analysis_account_ids": ["group:amazon", *amazon_ids],
        },
    ]


def _load_analysis_runs(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                period_type,
                period,
                account_id,
                direction,
                analyzer,
                analyzer_version,
                result_text,
                result_json,
                input_hash,
                created_at,
                updated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY period_type, period, account_id, direction
                    ORDER BY id DESC
                ) AS rn
            FROM analysis_runs
            WHERE status = 'success'
        )
        SELECT
            period_type,
            period,
            account_id,
            direction,
            analyzer,
            analyzer_version,
            result_text,
            result_json,
            input_hash,
            created_at,
            updated_at
        FROM ranked
        WHERE rn = 1
        ORDER BY updated_at DESC, created_at DESC
        """
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        parsed_json: Any = None
        raw_result_json = row["result_json"]
        if raw_result_json:
            try:
                parsed_json = json.loads(raw_result_json)
            except json.JSONDecodeError:
                parsed_json = None
        result.append(
            {
                "period_type": str(row["period_type"] or ""),
                "period": str(row["period"] or ""),
                "account_id": str(row["account_id"] or ""),
                "direction": str(row["direction"] or "expense"),
                "analyzer": str(row["analyzer"] or ""),
                "analyzer_version": str(row["analyzer_version"] or ""),
                "result_text": str(row["result_text"] or "").strip(),
                "result_json": parsed_json,
                "input_hash": str(row["input_hash"] or ""),
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    return result


def _load_assets_payload(conn) -> dict[str, Any]:
    chart_payload = asset_monthly_chart_payload(conn)
    monthly = chart_payload["monthly"]
    yearly = asset_yearly_performance(conn)
    fiscal_yearly = asset_fiscal_year_performance(conn)
    bounds = asset_period_bounds(conn)
    products = list_asset_products(conn)
    latest_summary = asset_summary_for_month(conn)

    holdings_by_month: dict[str, list[dict[str, Any]]] = {}
    for row in monthly:
        month = str(row["period_month"])
        holdings_by_month[month] = asset_holdings_for_month(conn, period_month=month)["holdings"]

    return {
        "summary": latest_summary,
        "bounds": bounds,
        "monthly": monthly,
        "axis": chart_payload.get("axis", {}),
        "yearly": yearly,
        "fiscal_yearly": fiscal_yearly,
        "products": products,
        "holdings_by_month": holdings_by_month,
    }


def _encode_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _load_mascot_data_uris() -> dict[str, dict[str, str]]:
    base = project_path("frontend", "assets", "mascot", "tanuki")
    return {
        "cheer": {
            "webp": _encode_data_uri(base / "webp" / "tanuki_cheer.webp"),
            "png": _encode_data_uri(base / "png" / "tanuki_cheer.png"),
        },
        "thinking": {
            "webp": _encode_data_uri(base / "webp" / "tanuki_thinking.webp"),
            "png": _encode_data_uri(base / "png" / "tanuki_thinking.png"),
        },
        "stale": {
            "webp": _encode_data_uri(base / "webp" / "tanuki_mail_wink.webp"),
            "png": _encode_data_uri(base / "png" / "tanuki_mail_wink.png"),
        },
        "icon": {
            "webp": _encode_data_uri(base / "png" / "tanuki_thinking.png"),
            "png": _encode_data_uri(base / "png" / "tanuki_thinking.png"),
        },
    }


def _build_export_payload(conn, exported_at: str) -> dict[str, Any]:
    period_options = _load_period_options(conn)
    account_filters = _load_account_filters(conn)
    transactions = _load_transactions(conn)
    analysis_runs = _load_analysis_runs(conn)
    categories = list_categories(conn)
    assets = _load_assets_payload(conn)

    return {
        "meta": {
            "title": "家計簿",
            "readonly_notice": "読み取り専用デモ",
            "exported_at": exported_at,
        },
        "period_options": period_options,
        "account_filters": account_filters,
        "transactions": transactions,
        "analysis_runs": analysis_runs,
        "categories": categories,
        "assets": assets,
        "mascots": _load_mascot_data_uris(),
    }


def _readonly_runtime_script() -> str:
    path = project_path("frontend", "readonly_app.js")
    if not path.exists():
        raise FileNotFoundError(f"Readonly runtime script not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _application_styles() -> str:
    style_paths = [
        project_path("frontend", "styles", "base.css"),
        project_path("frontend", "styles", "assets.css"),
        project_path("frontend", "styles", "components.css"),
    ]
    missing = [str(style_path) for style_path in style_paths if not style_path.exists()]
    if missing:
        raise FileNotFoundError(f"Application stylesheet not found: {', '.join(missing)}")
    return "\n\n".join(
        style_path.read_text(encoding="utf-8").strip() for style_path in style_paths
    )


def _render_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    index_html = project_path("frontend", "index.html").read_text(encoding="utf-8")
    styles_css = _application_styles()

    extra_css = """
.readonly-demo-badge {
  margin: -4px 20px 12px;
  color: #64748b;
  font-size: 12px;
}
""".strip()

    style_block = f"<style>\n{styles_css}\n\n{extra_css}\n</style>"
    html = re.sub(
        r"<link\s+rel=\"stylesheet\"\s+href=\"/styles.css\"\s*/?>",
        lambda _: style_block,
        index_html,
        count=1,
    )

    html = html.replace("</header>", "</header>\n\n    <p id=\"readonlyDemoBadge\" class=\"readonly-demo-badge\"></p>", 1)

    script_block = (
        f"<script id=\"mfblue-data\" type=\"application/json\">{data_json}</script>\n"
        f"<script>\n{_readonly_runtime_script()}\n</script>"
    )
    module_script_pattern = (
        r"(?:\s*<script\s+src=\"/app-(?:core|assets|budget|analysis|bootstrap)\.js"
        r"(?:\?[^\"]*)?\"\s*></script>)+"
    )
    html, replacement_count = re.subn(
        module_script_pattern,
        lambda _: "\n" + script_block,
        html,
        count=1,
    )
    if replacement_count != 1:
        html, replacement_count = re.subn(
            r"<script\s+src=\"/app\.js(?:\?[^\"]*)?\"\s*></script>",
            lambda _: script_block,
            html,
            count=1,
        )
    if replacement_count != 1:
        raise RuntimeError("Application script tags were not found in frontend/index.html")

    html = html.replace("<title>MF Blue Local Budget</title>", "<title>家計簿 (読み取り専用デモ)</title>")
    return html


def _build_zip_readme_text() -> str:
    lines = [
        "MF Blue 読み取り専用デモHTMLエクスポート",
        "",
        "- このファイルは読み取り専用デモです。",
        "- 編集・同期・再分析は実行されません。",
        "- GalaxyではZIPを展開して mfblue_readonly.html を開いてください。",
    ]
    return "\n".join(lines) + "\n"


def export_readonly_html(
    *,
    db_path: Path,
    html_path: Path = DEFAULT_HTML_PATH,
    zip_path: Path = DEFAULT_ZIP_PATH,
    create_zip: bool = True,
) -> dict[str, Any]:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        init_db(conn)
        exported_at = _utc_now_iso()
        payload = _build_export_payload(conn, exported_at=exported_at)
    finally:
        conn.close()

    html = _render_html(payload)
    html_path.write_text(html, encoding="utf-8")

    readme_text = _build_zip_readme_text()
    if create_zip:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(html_path, arcname="mfblue_readonly.html")
            zf.writestr("README.txt", readme_text)

    return {
        "html_path": html_path,
        "zip_path": zip_path if create_zip else None,
        "transaction_count": len(payload["transactions"]),
        "analysis_count": len(payload["analysis_runs"]),
        "asset_monthly_count": len(payload.get("assets", {}).get("monthly", [])),
        "asset_products_count": len(payload.get("assets", {}).get("products", [])),
        "exported_at": payload["meta"]["exported_at"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export read-only single HTML for smartphone offline viewing")
    parser.add_argument("--db", type=Path, default=database_path())
    parser.add_argument("--output", type=Path, default=DEFAULT_HTML_PATH)
    parser.add_argument("--zip", dest="zip_path", type=Path, default=DEFAULT_ZIP_PATH)
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args(argv)

    result = export_readonly_html(
        db_path=args.db,
        html_path=args.output,
        zip_path=args.zip_path,
        create_zip=not args.no_zip,
    )
    print(f"Exported read-only HTML: {result['html_path']}")
    if result["zip_path"]:
        print(f"Exported ZIP: {result['zip_path']}")
    print(f"Transactions embedded: {result['transaction_count']}")
    print(f"Saved analyses embedded: {result['analysis_count']}")
    print(f"Asset monthly bounds: {result['asset_monthly_count']} months")
    print(f"Asset products embedded: {result['asset_products_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
