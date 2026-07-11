from __future__ import annotations

import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, urlopen
from unittest.mock import patch

from mfblue.db import connect, ensure_asset_product, init_db, upsert_asset_snapshot
from mfblue.server import Handler, ThreadingHTTPServer


class AssetsApiTests(unittest.TestCase):
    def test_post_purchase_api(self) -> None:
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
                    account_type="新NISA",
                )
                conn.commit()
            finally:
                conn.close()

            @contextmanager
            def temp_db_ctx():
                inner = connect(db_path)
                try:
                    yield inner
                    inner.commit()
                finally:
                    inner.close()

            with patch("mfblue.api_routes.db", temp_db_ctx):
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f"http://127.0.0.1:{server.server_address[1]}"
                    request = Request(
                        f"{base}/api/assets/purchases",
                        data=json.dumps(
                            {
                                "asset_id": asset_id,
                                "purchase_date": "2026-02-10",
                                "amount_yen": 50000,
                                "memo": "積立",
                            }
                        ).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(request) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(payload["status"], "ok")
                    self.assertEqual(payload["purchase"]["amount_yen"], 50000)

                    with urlopen(f"{base}/api/assets/monthly") as response:
                        monthly = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(len(monthly["monthly"]), 0)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

            conn = connect(db_path)
            try:
                row = conn.execute("SELECT amount_yen, period_month FROM asset_purchases").fetchone()
                self.assertEqual(row["amount_yen"], 50000)
                self.assertEqual(row["period_month"], "2026-02")
            finally:
                conn.close()

    def test_assets_monthly_and_holdings_include_month_diff_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                asset_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（成長投資枠）",
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-04-30",
                        "period_month": "2026-04",
                        "current_value_yen": 1000000,
                        "invested_amount_yen": 900000,
                        "profit_loss_yen": 100000,
                        "source": "csv",
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-05-31",
                        "period_month": "2026-05",
                        "current_value_yen": 1200000,
                        "invested_amount_yen": 1000000,
                        "profit_loss_yen": 200000,
                        "source": "csv",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            @contextmanager
            def temp_db_ctx():
                inner = connect(db_path)
                try:
                    yield inner
                    inner.commit()
                finally:
                    inner.close()

            with patch("mfblue.api_routes.db", temp_db_ctx):
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f"http://127.0.0.1:{server.server_address[1]}"
                    with urlopen(f"{base}/api/assets/monthly") as response:
                        monthly = json.loads(response.read().decode("utf-8"))
                    self.assertIn("axis", monthly)
                    self.assertIn("change", monthly["axis"])
                    self.assertEqual(monthly["monthly"][-1]["month_change_yen"], 200000)

                    with urlopen(f"{base}/api/assets/holdings?period_month=2026-05") as response:
                        holdings = json.loads(response.read().decode("utf-8"))
                    row = holdings["holdings"][0]
                    self.assertEqual(row["month_change_yen"], 200000)
                    self.assertAlmostEqual(row["month_change_rate"], 20.0, places=4)
                    self.assertIn("source_label", row)
                    with urlopen(f"{base}/api/assets/yearly") as response:
                        yearly = json.loads(response.read().decode("utf-8"))
                    self.assertIn("fiscal_yearly", yearly)
                    self.assertIn("percent_rules", yearly)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_refresh_prices_api_returns_nav_and_snapshot_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                asset_id, _ = ensure_asset_product(
                    conn,
                    name="ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）",
                    asset_type="investment_trust",
                    institution="SBI証券",
                    account_type="新NISA（成長投資枠）",
                )
                upsert_asset_snapshot(
                    conn,
                    {
                        "asset_id": asset_id,
                        "valuation_date": "2026-05-31",
                        "period_month": "2026-05",
                        "current_value_yen": 1234567,
                        "invested_amount_yen": 1000000,
                        "profit_loss_yen": 234567,
                        "source": "csv",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            @contextmanager
            def temp_db_ctx():
                inner = connect(db_path)
                try:
                    yield inner
                    inner.commit()
                finally:
                    inner.close()

            with (
                patch("mfblue.api_routes.db", temp_db_ctx),
                patch("mfblue.api_routes.fetch_nav_prices", return_value={"sources": 2, "fetched": 3, "inserted": 1, "updated": 1, "skipped": 1, "errors": 0, "error_details": []}),
                patch("mfblue.api_routes.generate_snapshots", return_value={"months": 1, "inserted": 0, "updated": 1, "skipped": 0, "protected": 1, "errors": 0}),
                patch("mfblue.api_routes.repair_asset_snapshot_duplicates", return_value={"verified_month": "2026-05", "verified_total": 1234567}),
            ):
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base = f"http://127.0.0.1:{server.server_address[1]}"
                    request = Request(
                        f"{base}/api/assets/refresh-prices",
                        data=json.dumps({"period_month": "2026-05"}).encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(request) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(payload["status"], "ok")
                    self.assertEqual(payload["nav_fetch"]["fetched"], 3)
                    self.assertEqual(payload["summary"]["current_value_yen"], 1234567)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
