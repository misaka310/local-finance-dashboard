from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mfblue.db import (  # noqa: E402
    connect,
    ensure_account,
    ensure_asset_product,
    init_db,
    upsert_asset_snapshot,
    upsert_transaction,
)
from mfblue.export_readonly_html import export_readonly_html  # noqa: E402

TRANSACTIONS = [
    ("2026-01-05", "給与", 285000, "income", "uncategorized", "収入"),
    ("2026-01-08", "スーパーマーケット", 6840, "expense", "food", "食料品"),
    ("2026-01-12", "モバイル通信", 4980, "expense", "communication", "携帯電話"),
    ("2026-02-05", "給与", 285000, "income", "uncategorized", "収入"),
    ("2026-02-09", "書店", 2640, "expense", "education", "書籍"),
    ("2026-02-16", "フィットネス", 8800, "expense", "health", "フィットネス"),
    ("2026-03-05", "給与", 285000, "income", "uncategorized", "収入"),
    ("2026-03-08", "スーパーマーケット", 7310, "expense", "food", "食料品"),
    ("2026-03-10", "動画配信サービス", 1490, "expense", "hobby", "動画・音楽"),
    ("2026-03-18", "鉄道", 5210, "expense", "transport", "電車"),
]

ASSET_SERIES = {
    "全世界株式インデックス": [
        ("2026-01", "2026-01-31", 1200000, 100000),
        ("2026-02", "2026-02-28", 1325000, 100000),
        ("2026-03", "2026-03-31", 1458000, 100000),
    ],
    "国内債券インデックス": [
        ("2026-01", "2026-01-31", 420000, 30000),
        ("2026-02", "2026-02-28", 452000, 30000),
        ("2026-03", "2026-03-31", 486000, 30000),
    ],
}


def _seed_demo_database(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        init_db(conn)
        ensure_account(conn, "demo-bank", "デモ銀行", kind="bank")
        ensure_account(conn, "demo-card", "デモカード")

        for index, (occurred_at, merchant, amount, direction, category_id, subcategory) in enumerate(
            TRANSACTIONS, start=1
        ):
            upsert_transaction(
                conn,
                {
                    "source_id": "public-demo",
                    "account_id": "demo-bank" if direction == "income" else "demo-card",
                    "external_id": f"public-demo-{index:03d}",
                    "thread_id": None,
                    "direction": direction,
                    "occurred_at": occurred_at,
                    "posted_at": None,
                    "merchant": merchant,
                    "raw_description": "synthetic public demo data",
                    "amount_yen": amount,
                    "category_id": category_id,
                    "subcategory": subcategory,
                    "note": None,
                },
            )

        for name, snapshots in ASSET_SERIES.items():
            asset_id, _ = ensure_asset_product(
                conn,
                name=name,
                asset_type="investment_trust",
                institution="デモ証券",
                account_type="NISA",
                memo="合成データ",
            )
            for period_month, valuation_date, current_value_yen, purchase_amount_yen in snapshots:
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "period_month": period_month,
                        "valuation_date": valuation_date,
                        "current_value_yen": current_value_yen,
                        "purchase_amount_yen": purchase_amount_yen,
                        "source": "generated",
                    },
                )
        conn.commit()
    finally:
        conn.close()


def build_public_demo(output_path: Path) -> dict[str, object]:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="local-finance-demo-") as temp_dir:
        db_path = Path(temp_dir) / "synthetic-demo.sqlite3"
        _seed_demo_database(db_path)
        result = export_readonly_html(
            db_path=db_path,
            html_path=output_path,
            create_zip=False,
        )

    html = output_path.read_text(encoding="utf-8")
    html = html.replace(
        "読み取り専用デモ / 書き出し:",
        "合成データの公開デモ / 読み取り専用 / 生成:",
    )
    html = html.replace(
        "<title>Local Finance Dashboard (読み取り専用)</title>",
        "<title>Local Finance Dashboard — 合成データデモ</title>",
    )
    output_path.write_text(html, encoding="utf-8")
    (output_path.parent / ".nojekyll").write_text("", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the synthetic public GitHub Pages demo")
    parser.add_argument("--output", type=Path, default=ROOT / "_site" / "index.html")
    args = parser.parse_args(argv)

    result = build_public_demo(args.output)
    print(f"Public demo: {args.output.resolve()}")
    print(f"Transactions: {result['transaction_count']}")
    print(f"Asset products: {result['asset_products_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
