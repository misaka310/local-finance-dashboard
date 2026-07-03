from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import (
    MIN_BASE_VALUE_FOR_PERCENT,
    add_asset_purchase,
    asset_fiscal_year_performance,
    asset_holdings_for_month,
    asset_monthly_chart_payload,
    asset_monthly_series,
    asset_summary_for_month,
    asset_yearly_performance,
    connect,
    ensure_asset_product,
    init_db,
    upsert_asset_snapshot,
)


class AssetDbTests(unittest.TestCase):
    def test_monthly_and_yearly_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                asset_id, _ = ensure_asset_product(
                    conn,
                    name="eMAXIS Slim 米国株式(S&P500)",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（つみたて投資枠）",
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-01-31",
                        "period_month": "2026-01",
                        "current_value_yen": 1000000,
                        "invested_amount_yen": 950000,
                        "profit_loss_yen": 50000,
                        "profit_loss_rate": 5.26,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-02-28",
                        "period_month": "2026-02",
                        "current_value_yen": 1150000,
                        "invested_amount_yen": 1050000,
                        "profit_loss_yen": 100000,
                        "profit_loss_rate": 9.52,
                        "source": "csv",
                    },
                )
                add_asset_purchase(
                    conn,
                    {
                        "asset_id": asset_id,
                        "purchase_date": "2026-02-10",
                        "amount_yen": 100000,
                        "source": "manual",
                    },
                )
                conn.commit()

                monthly = asset_monthly_series(conn)
                self.assertEqual(len(monthly), 2)
                self.assertEqual(monthly[1]["month_change_yen"], 150000)
                self.assertAlmostEqual(monthly[1]["month_change_rate"], 15.0, places=4)
                self.assertEqual(monthly[1]["purchase_amount_yen"], 100000)
                self.assertEqual(monthly[1]["operation_change_yen"], 50000)
                self.assertAlmostEqual(monthly[1]["operation_change_rate"], 5.0, places=4)

                summary = asset_summary_for_month(conn, "2026-02")
                self.assertTrue(summary["has_data"])
                self.assertEqual(summary["current_value_yen"], 1150000)
                self.assertEqual(summary["purchase_amount_yen"], 100000)

                yearly = asset_yearly_performance(conn)
                self.assertEqual(len(yearly), 1)
                self.assertEqual(yearly[0]["year"], "2026")
                self.assertEqual(yearly[0]["total_change_yen"], 150000)
                self.assertEqual(yearly[0]["purchase_amount_yen"], 100000)
                self.assertEqual(yearly[0]["operation_change_yen"], 50000)
            finally:
                conn.close()

    def test_measured_snapshot_is_prioritized_over_generated_and_total_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                growth_measured_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（成長投資枠）",
                )
                tsumitate_measured_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（つみたて投資枠）",
                )
                now = "2026-05-31T00:00:00+00:00"
                cur_growth = conn.execute(
                    """
                    INSERT INTO asset_products(name, asset_type, institution, account_type, memo, created_at, updated_at)
                    VALUES (?, 'investment_trust', 'SBI証券', '新NISA（成長投資枠）', NULL, ?, ?)
                    """,
                    ("eMAXIS Slim 米国株式（S&P500）", now, now),
                )
                growth_generated_id = int(cur_growth.lastrowid)
                cur_tsumitate = conn.execute(
                    """
                    INSERT INTO asset_products(name, asset_type, institution, account_type, memo, created_at, updated_at)
                    VALUES (?, 'investment_trust', 'SBI証券', '新NISA（つみたて投資枠）', NULL, ?, ?)
                    """,
                    ("eMAXIS Slim 米国株式（S&P500）", now, now),
                )
                tsumitate_generated_id = int(cur_tsumitate.lastrowid)
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": growth_measured_id,
                        "valuation_date": "2026-05-31",
                        "period_month": "2026-05",
                        "current_value_yen": 800000,
                        "invested_amount_yen": 750000,
                        "profit_loss_yen": 50000,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": tsumitate_measured_id,
                        "valuation_date": "2026-05-31",
                        "period_month": "2026-05",
                        "current_value_yen": 434567,
                        "invested_amount_yen": 400000,
                        "profit_loss_yen": 34567,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": growth_generated_id,
                        "valuation_date": "2026-05-30",
                        "period_month": "2026-05",
                        "current_value_yen": 850000,
                        "invested_amount_yen": 750000,
                        "profit_loss_yen": 100000,
                        "source": "generated",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": tsumitate_generated_id,
                        "valuation_date": "2026-05-30",
                        "period_month": "2026-05",
                        "current_value_yen": 450000,
                        "invested_amount_yen": 400000,
                        "profit_loss_yen": 50000,
                        "source": "generated",
                    },
                )
                conn.commit()

                summary = asset_summary_for_month(conn, "2026-05")
                self.assertEqual(summary["current_value_yen"], 1234567)
                holdings = asset_holdings_for_month(conn, "2026-05")
                self.assertEqual(len(holdings["holdings"]), 2)
                self.assertEqual({row["source_label"] for row in holdings["holdings"]}, {"実測"})
            finally:
                conn.close()

    def test_generated_is_used_when_measured_not_exists_for_month(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                measured_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（成長投資枠）",
                )
                cur = conn.execute(
                    """
                    INSERT INTO asset_products(name, asset_type, institution, account_type, memo, created_at, updated_at)
                    VALUES (?, 'investment_trust', 'SBI証券', '新NISA（成長投資枠）', NULL, ?, ?)
                    """,
                    ("eMAXIS Slim 米国株式（S&P500）", "2026-04-30T00:00:00+00:00", "2026-04-30T00:00:00+00:00"),
                )
                generated_id = int(cur.lastrowid)
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": measured_id,
                        "valuation_date": "2026-05-31",
                        "period_month": "2026-05",
                        "current_value_yen": 1000000,
                        "invested_amount_yen": 900000,
                        "profit_loss_yen": 100000,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": generated_id,
                        "valuation_date": "2026-04-30",
                        "period_month": "2026-04",
                        "current_value_yen": 800000,
                        "invested_amount_yen": 760000,
                        "profit_loss_yen": 40000,
                        "source": "generated",
                    },
                )
                conn.commit()

                april = asset_summary_for_month(conn, "2026-04")
                self.assertEqual(april["current_value_yen"], 800000)
                monthly_payload = asset_monthly_chart_payload(conn)
                self.assertIn("axis", monthly_payload)
                self.assertIn("value", monthly_payload["axis"])
            finally:
                conn.close()

    def test_percent_visibility_rule_and_fiscal_year_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                asset_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　新興国株式インデックス",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（つみたて投資枠）",
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2024-10-31",
                        "period_month": "2024-10",
                        "current_value_yen": MIN_BASE_VALUE_FOR_PERCENT - 1,
                        "invested_amount_yen": 90000,
                        "profit_loss_yen": 9999,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2025-03-31",
                        "period_month": "2025-03",
                        "current_value_yen": 140000,
                        "invested_amount_yen": 110000,
                        "profit_loss_yen": 30000,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-04-30",
                        "period_month": "2026-04",
                        "current_value_yen": 200000,
                        "invested_amount_yen": 180000,
                        "profit_loss_yen": 20000,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-05-31",
                        "period_month": "2026-05",
                        "current_value_yen": 220000,
                        "invested_amount_yen": 200000,
                        "profit_loss_yen": 20000,
                        "source": "csv",
                    },
                )
                conn.commit()

                yearly = asset_yearly_performance(conn)
                row_2024 = next(item for item in yearly if item["year"] == "2024")
                self.assertFalse(row_2024["percent_available"])
                self.assertIsNone(row_2024["total_change_rate"])

                fiscal = asset_fiscal_year_performance(conn)
                row_2026 = next(item for item in fiscal if item["year"] == "2026")
                self.assertEqual(row_2026["start_period_month"], "2026-04")
                self.assertEqual(row_2026["end_period_month"], "2026-05")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
