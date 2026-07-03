from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import (
    add_asset_trade,
    asset_holdings_for_month,
    asset_summary_for_month,
    connect,
    ensure_asset_product,
    init_db,
    upsert_asset_snapshot,
    upsert_fund_nav_price,
)
from mfblue.generate_asset_snapshots import generate_snapshots


class GenerateAssetSnapshotsTests(unittest.TestCase):
    def test_generate_snapshots_and_keep_measured_snapshot_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                upsert_fund_nav_price(
                    conn,
                    {
                        "fund_name": "ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                        "price_date": "2024-07-30",
                        "base_price": 10000,
                        "provider_name": "三菱ＵＦＪアセットマネジメント",
                        "source_url": "https://example.test/mufg",
                    },
                )
                upsert_fund_nav_price(
                    conn,
                    {
                        "fund_name": "ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                        "price_date": "2024-08-30",
                        "base_price": 11000,
                        "provider_name": "三菱ＵＦＪアセットマネジメント",
                        "source_url": "https://example.test/mufg",
                    },
                )
                add_asset_trade(
                    conn,
                    {
                        "trade_date": "2024-07-10",
                        "settlement_date": "2024-07-11",
                        "fund_name": "ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                        "institution": "SBI証券",
                        "account_type": "新NISA（成長投資枠）",
                        "trade_type": "buy",
                        "quantity": 10000,
                        "unit_price": 10000,
                        "amount_yen": 10000,
                        "source": "csv",
                    },
                )
                add_asset_trade(
                    conn,
                    {
                        "trade_date": "2024-07-10",
                        "settlement_date": "2024-07-11",
                        "fund_name": "ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                        "institution": "SBI証券",
                        "account_type": "新NISA（つみたて投資枠）",
                        "trade_type": "buy",
                        "quantity": 20000,
                        "unit_price": 10000,
                        "amount_yen": 20000,
                        "source": "csv",
                    },
                )
                growth_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（成長投資枠）",
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": growth_id,
                        "valuation_date": "2024-07-30",
                        "period_month": "2024-07",
                        "current_value_yen": 999999,
                        "invested_amount_yen": 10000,
                        "profit_loss_yen": 989999,
                        "source": "csv",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            result = generate_snapshots(
                date_from="2024-07-01",
                date_to="2024-08-31",
                db_path=db_path,
            )
            self.assertGreaterEqual(result["protected"], 1)
            self.assertGreaterEqual(result["inserted"], 1)

            conn = connect(db_path)
            try:
                july = asset_holdings_for_month(conn, "2024-07")
                august = asset_holdings_for_month(conn, "2024-08")
                self.assertEqual(len(july["holdings"]), 1)
                self.assertEqual(len(august["holdings"]), 2)
                july_growth = [r for r in july["holdings"] if r["account_type"] == "新NISA（成長投資枠）"][0]
                self.assertEqual(july_growth["current_value_yen"], 999999)
                august_sources = {r["source"] for r in august["holdings"]}
                self.assertEqual(august_sources, {"generated"})

                summary = asset_summary_for_month(conn, "2024-08")
                self.assertEqual(summary["current_value_yen"], 33000)
            finally:
                conn.close()

    def test_generate_matches_nav_and_trades_even_with_name_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                upsert_fund_nav_price(
                    conn,
                    {
                        "fund_name": "ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                        "price_date": "2026-05-30",
                        "base_price": 20000,
                        "provider_name": "三菱ＵＦＪアセットマネジメント",
                        "source_url": "https://example.test/mufg",
                    },
                )
                add_asset_trade(
                    conn,
                    {
                        "trade_date": "2026-05-10",
                        "settlement_date": "2026-05-11",
                        "fund_name": "eMAXIS Slim 米国株式（S&P500）",
                        "institution": "SBI証券",
                        "account_type": "新NISA（成長投資枠）",
                        "trade_type": "buy",
                        "quantity": 10000,
                        "unit_price": 20000,
                        "amount_yen": 20000,
                        "source": "csv",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            result = generate_snapshots(
                date_from="2026-05-01",
                date_to="2026-05-31",
                db_path=db_path,
            )
            self.assertGreaterEqual(result["inserted"], 1)

            conn = connect(db_path)
            try:
                summary = asset_summary_for_month(conn, "2026-05")
                self.assertEqual(summary["current_value_yen"], 20000)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
