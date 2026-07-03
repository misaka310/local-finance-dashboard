from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .db import db, init_db
from .paths import project_path

OUTPUT_PATH = project_path("data", "classification", "merchant_candidates.csv")


def export_candidates(output_path: Path = OUTPUT_PATH) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with db() as conn:
        init_db(conn)
        rows = conn.execute(
            """
            WITH merchant_stats AS (
                SELECT
                    t.merchant AS merchant,
                    COUNT(*) AS tx_count,
                    SUM(t.amount_yen) AS total_amount
                FROM transactions t
                WHERE t.direction = 'expense'
                GROUP BY t.merchant
            ),
            merchant_category AS (
                SELECT
                    t.merchant AS merchant,
                    c.name AS category_name,
                    t.subcategory AS subcategory,
                    COUNT(*) AS tx_count,
                    SUM(t.amount_yen) AS amount_sum,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.merchant
                        ORDER BY COUNT(*) DESC, SUM(t.amount_yen) DESC, c.name, t.subcategory
                    ) AS rn
                FROM transactions t
                JOIN categories c ON c.id = t.category_id
                WHERE t.direction = 'expense'
                GROUP BY t.merchant, c.name, t.subcategory
            )
            SELECT
                ms.merchant,
                ms.tx_count,
                ms.total_amount,
                mc.category_name,
                mc.subcategory
            FROM merchant_stats ms
            LEFT JOIN merchant_category mc
              ON mc.merchant = ms.merchant
             AND mc.rn = 1
            ORDER BY ms.total_amount DESC, ms.tx_count DESC, ms.merchant COLLATE NOCASE
            """
        ).fetchall()

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["merchant", "count", "total_amount", "current_category", "current_subcategory"])
        for row in rows:
            category = (row["category_name"] or "").strip() or "未分類"
            subcategory = (row["subcategory"] or "").strip() or "未分類"
            writer.writerow([
                row["merchant"],
                int(row["tx_count"] or 0),
                int(row["total_amount"] or 0),
                category,
                subcategory,
            ])

    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export merchant-level category candidates")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    count = export_candidates(args.output)
    print(f"Exported {count} merchants.")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
