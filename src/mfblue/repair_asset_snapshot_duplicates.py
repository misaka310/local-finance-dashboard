from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .asset_fund_names import normalize_asset_fund_name
from .db import asset_summary_for_month, connect, init_db, utc_now_iso


def _source_priority(source: str | None) -> int:
    return 0 if str(source or "").strip().lower() in {"csv", "manual"} else 1


def _is_better(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    cand_priority = _source_priority(str(candidate.get("source") or ""))
    exist_priority = _source_priority(str(existing.get("source") or ""))
    if cand_priority != exist_priority:
        return cand_priority < exist_priority
    cand_valuation = str(candidate.get("valuation_date") or "")
    exist_valuation = str(existing.get("valuation_date") or "")
    if cand_valuation != exist_valuation:
        return cand_valuation > exist_valuation
    cand_updated = str(candidate.get("updated_at") or "")
    exist_updated = str(existing.get("updated_at") or "")
    if cand_updated != exist_updated:
        return cand_updated > exist_updated
    return int(candidate.get("id") or 0) > int(existing.get("id") or 0)


def repair_asset_snapshot_duplicates(
    *,
    db_path: Path | None = None,
    verify_month: str | None = None,
) -> dict[str, Any]:
    stats = {
        "product_groups": 0,
        "merged_products": 0,
        "moved_snapshots": 0,
        "deleted_snapshots": 0,
        "moved_purchases": 0,
        "deleted_products": 0,
        "deduped_conflicts": 0,
        "verified_month": verify_month,
        "verified_total": None,
    }
    conn = connect(db_path)
    try:
        init_db(conn)
        now = utc_now_iso()
        products = conn.execute(
            """
            SELECT id, name, institution, account_type
            FROM asset_products
            ORDER BY institution, account_type, id
            """
        ).fetchall()
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in products:
            key = (
                normalize_asset_fund_name(str(row["name"] or "")),
                str(row["institution"] or ""),
                str(row["account_type"] or ""),
            )
            grouped.setdefault(key, []).append(dict(row))

        for group_key, group_products in grouped.items():
            if len(group_products) <= 1:
                continue
            stats["product_groups"] += 1
            measured_counts: dict[int, int] = {}
            for prod in group_products:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM asset_snapshots
                    WHERE asset_id = ? AND source IN ('csv', 'manual')
                    """,
                    (int(prod["id"]),),
                ).fetchone()
                measured_counts[int(prod["id"])] = int(count_row["c"] if count_row else 0)
            canonical = sorted(
                group_products,
                key=lambda p: (-measured_counts[int(p["id"])], int(p["id"])),
            )[0]
            canonical_id = int(canonical["id"])

            for product in group_products:
                product_id = int(product["id"])
                if product_id == canonical_id:
                    continue
                stats["merged_products"] += 1
                snapshot_rows = conn.execute(
                    """
                    SELECT
                        id, asset_id, valuation_date, period_month, quantity, base_price, acquisition_price,
                        current_value_yen, invested_amount_yen, profit_loss_yen, profit_loss_rate,
                        daily_change_yen, daily_change_rate, dividend_method, source, created_at, updated_at
                    FROM asset_snapshots
                    WHERE asset_id = ?
                    ORDER BY period_month, id
                    """,
                    (product_id,),
                ).fetchall()
                for raw in snapshot_rows:
                    snapshot = dict(raw)
                    period = str(snapshot["period_month"])
                    existing = conn.execute(
                        """
                        SELECT
                            id, asset_id, valuation_date, period_month, quantity, base_price, acquisition_price,
                            current_value_yen, invested_amount_yen, profit_loss_yen, profit_loss_rate,
                            daily_change_yen, daily_change_rate, dividend_method, source, created_at, updated_at
                        FROM asset_snapshots
                        WHERE asset_id = ? AND period_month = ?
                        """,
                        (canonical_id, period),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "UPDATE asset_snapshots SET asset_id = ?, updated_at = ? WHERE id = ?",
                            (canonical_id, now, int(snapshot["id"])),
                        )
                        stats["moved_snapshots"] += 1
                        continue
                    existing_dict = dict(existing)
                    if _is_better(snapshot, existing_dict):
                        conn.execute(
                            """
                            UPDATE asset_snapshots
                            SET valuation_date = ?, quantity = ?, base_price = ?, acquisition_price = ?,
                                current_value_yen = ?, invested_amount_yen = ?, profit_loss_yen = ?, profit_loss_rate = ?,
                                daily_change_yen = ?, daily_change_rate = ?, dividend_method = ?, source = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                snapshot["valuation_date"],
                                snapshot["quantity"],
                                snapshot["base_price"],
                                snapshot["acquisition_price"],
                                snapshot["current_value_yen"],
                                snapshot["invested_amount_yen"],
                                snapshot["profit_loss_yen"],
                                snapshot["profit_loss_rate"],
                                snapshot["daily_change_yen"],
                                snapshot["daily_change_rate"],
                                snapshot["dividend_method"],
                                snapshot["source"],
                                now,
                                int(existing_dict["id"]),
                            ),
                        )
                    conn.execute("DELETE FROM asset_snapshots WHERE id = ?", (int(snapshot["id"]),))
                    stats["deleted_snapshots"] += 1

                purchase_rows = conn.execute(
                    "SELECT id FROM asset_purchases WHERE asset_id = ?",
                    (product_id,),
                ).fetchall()
                for purchase in purchase_rows:
                    conn.execute(
                        "UPDATE asset_purchases SET asset_id = ?, updated_at = ? WHERE id = ?",
                        (canonical_id, now, int(purchase["id"])),
                    )
                    stats["moved_purchases"] += 1

                conn.execute("DELETE FROM asset_products WHERE id = ?", (product_id,))
                stats["deleted_products"] += 1

        measured_months = conn.execute(
            """
            SELECT DISTINCT s.period_month
            FROM asset_snapshots s
            WHERE s.source IN ('csv', 'manual')
            """
        ).fetchall()
        for row in measured_months:
            target = conn.execute(
                """
                SELECT id
                FROM asset_snapshots
                WHERE source = 'generated'
                  AND period_month = ?
                """,
                (str(row["period_month"]),),
            ).fetchall()
            for item in target:
                conn.execute("DELETE FROM asset_snapshots WHERE id = ?", (int(item["id"]),))
                stats["deleted_snapshots"] += 1
                stats["deduped_conflicts"] += 1

        snapshot_rows = conn.execute(
            """
            SELECT
                s.id,
                s.asset_id,
                s.valuation_date,
                s.period_month,
                s.source,
                s.updated_at,
                p.name,
                p.institution,
                p.account_type
            FROM asset_snapshots s
            JOIN asset_products p ON p.id = s.asset_id
            ORDER BY s.period_month, p.institution, p.account_type, p.name, s.id
            """
        ).fetchall()
        grouped_snapshots: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in snapshot_rows:
            row_dict = dict(row)
            key = (
                str(row_dict["period_month"] or ""),
                normalize_asset_fund_name(str(row_dict["name"] or "")),
                str(row_dict["institution"] or ""),
                str(row_dict["account_type"] or ""),
            )
            grouped_snapshots.setdefault(key, []).append(row_dict)

        for _, rows in grouped_snapshots.items():
            if len(rows) <= 1:
                continue
            winner = rows[0]
            for row in rows[1:]:
                if _is_better(row, winner):
                    winner = row
            for row in rows:
                if int(row["id"]) == int(winner["id"]):
                    continue
                conn.execute("DELETE FROM asset_snapshots WHERE id = ?", (int(row["id"]),))
                stats["deleted_snapshots"] += 1
                stats["deduped_conflicts"] += 1

        conn.commit()
        if verify_month:
            summary = asset_summary_for_month(conn, period_month=verify_month)
            stats["verified_total"] = int(summary.get("current_value_yen") or 0)
    finally:
        conn.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair duplicated asset snapshots by normalized fund name and source priority.")
    parser.add_argument("--db-path", help="override sqlite path")
    parser.add_argument("--verify-month", help="verify total of target month (YYYY-MM)")
    parser.add_argument("--expect-total", type=int, help="expected total yen for --verify-month")
    args = parser.parse_args(argv)

    stats = repair_asset_snapshot_duplicates(
        db_path=Path(args.db_path) if args.db_path else None,
        verify_month=args.verify_month,
    )
    print("Asset snapshot repair completed.")
    print(
        "groups: {product_groups} / merged_products: {merged_products} / moved_snapshots: {moved_snapshots} / "
        "deleted_snapshots: {deleted_snapshots} / moved_purchases: {moved_purchases} / deleted_products: {deleted_products} / "
        "deduped_conflicts: {deduped_conflicts}".format(**stats)
    )
    if args.verify_month:
        print(f"verify {args.verify_month}: {stats['verified_total']}")
    if args.expect_total is not None:
        if stats["verified_total"] != int(args.expect_total):
            print(f"expected {int(args.expect_total)} but got {stats['verified_total']}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
