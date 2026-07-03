from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import asset_summary_for_month, connect, ensure_asset_product, init_db, upsert_asset_snapshot
from mfblue.repair_asset_snapshot_duplicates import repair_asset_snapshot_duplicates


class RepairAssetSnapshotDuplicatesTests(unittest.TestCase):
    def test_repair_resolves_name_variants_and_prefers_measured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                measured_growth_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（成長投資枠）",
                )
                measured_tsumitate_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（つみたて投資枠）",
                )
                now = "2026-05-31T00:00:00+00:00"
                dup_growth = conn.execute(
                    """
                    INSERT INTO asset_products(name, asset_type, institution, account_type, memo, created_at, updated_at)
                    VALUES (?, 'investment_trust', 'SBI証券', '新NISA（成長投資枠）', NULL, ?, ?)
                    """,
                    ("eMAXIS Slim 米国株式（S&P500）", now, now),
                )
                dup_tsumitate = conn.execute(
                    """
                    INSERT INTO asset_products(name, asset_type, institution, account_type, memo, created_at, updated_at)
                    VALUES (?, 'investment_trust', 'SBI証券', '新NISA（つみたて投資枠）', NULL, ?, ?)
                    """,
                    ("eMAXIS Slim 米国株式（S&P500）", now, now),
                )
                dup_growth_id = int(dup_growth.lastrowid)
                dup_tsumitate_id = int(dup_tsumitate.lastrowid)

                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": measured_growth_id,
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
                        "asset_id": measured_tsumitate_id,
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
                        "asset_id": dup_growth_id,
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
                        "asset_id": dup_tsumitate_id,
                        "valuation_date": "2026-05-30",
                        "period_month": "2026-05",
                        "current_value_yen": 450000,
                        "invested_amount_yen": 400000,
                        "profit_loss_yen": 50000,
                        "source": "generated",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            result = repair_asset_snapshot_duplicates(db_path=db_path, verify_month="2026-05")
            self.assertEqual(result["verified_total"], 1234567)
            self.assertGreaterEqual(result["deleted_snapshots"], 2)
            self.assertGreaterEqual(result["deleted_products"], 1)

            conn = connect(db_path)
            try:
                summary = asset_summary_for_month(conn, "2026-05")
                self.assertEqual(summary["current_value_yen"], 1234567)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
