from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from mfblue.db import connect, init_db, upsert_transaction, ensure_asset_product, upsert_asset_snapshot
from mfblue.export_readonly_html import export_readonly_html


class ExportReadonlyHtmlTests(unittest.TestCase):
    def test_export_creates_single_html_and_zip_with_app_like_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "sample.sqlite3"
            html_path = temp_root / "dist" / "readonly" / "mfblue_readonly.html"
            zip_path = temp_root / "dist" / "readonly" / "mfblue_readonly.zip"

            conn = connect(db_path)
            try:
                init_db(conn)
                common = {
                    "thread_id": None,
                    "posted_at": None,
                    "raw_description": "raw text should not be exported",
                    "source_id": "paypay-card-csv",
                    "account_id": "paypay-card",
                    "subcategory": "未分類",
                    "note": None,
                }

                upsert_transaction(
                    conn,
                    {
                        **common,
                        "external_id": "exp-001",
                        "direction": "expense",
                        "occurred_at": "2026-05-10",
                        "merchant": "スーパー",
                        "amount_yen": 1200,
                        "category_id": "food",
                    },
                )
                upsert_transaction(
                    conn,
                    {
                        **common,
                        "external_id": "exp-002",
                        "direction": "expense",
                        "occurred_at": "2026-05-11",
                        "merchant": "PayPayチャージ",
                        "amount_yen": 10000,
                        "category_id": "fund_movement",
                        "subcategory": "チャージ",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            result = export_readonly_html(
                db_path=db_path,
                html_path=html_path,
                zip_path=zip_path,
                create_zip=True,
            )

            self.assertTrue(html_path.exists())
            self.assertTrue(zip_path.exists())
            self.assertEqual(result["transaction_count"], 2)
            self.assertIn("asset_monthly_count", result)
            self.assertIn("asset_products_count", result)

            html = html_path.read_text(encoding="utf-8")
            self.assertIn('id="mfblue-data"', html)
            self.assertIn('id="showSubcategories"', html)
            self.assertIn('id="syncButton"', html)
            self.assertIn('id="runAnalysisButton"', html)
            self.assertIn('id="rerunAnalysisButton"', html)
            self.assertIn('id="editDialog"', html)
            self.assertIn('id="subcategoryChips"', html)
            self.assertIn('id="viewFundMovement"', html)
            self.assertIn('id="scrollTopButton"', html)
            self.assertIn('id="assetTabView"', html)
            self.assertIn('id="assetChart"', html)
            self.assertIn('id="assetYearlyCards"', html)
            self.assertIn('id="openAssetPurchaseDialog"', html)
            self.assertIn("読み取り専用デモ", html)
            self.assertRegex(html, r"data:[^;]+;base64,")
            self.assertIn("カテゴリを変更", html)
            self.assertIn("同じ店舗を次回から同じカテゴリにする", html)
            self.assertIn("過去の同じ店舗にも適用する", html)
            self.assertIn("<dt>収支</dt>", html)
            self.assertNotIn("<dt>残高</dt>", html)

            self.assertNotIn("raw text should not be exported", html)
            self.assertNotIn("/api/", html)
            self.assertNotIn("口座/ソース別サマリ", html)
            self.assertNotIn("年別サマリ", html)
            self.assertNotIn("管理画面", html)

            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("mfblue_readonly.html", names)
                self.assertIn("README.txt", names)
                readme_text = zf.read("README.txt").decode("utf-8")
                self.assertIn("読み取り専用デモ", readme_text)

    def test_asset_chart_interactivity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "sample_assets.sqlite3"
            html_path = temp_root / "dist" / "readonly" / "mfblue_readonly_assets.html"

            conn = connect(db_path)
            try:
                init_db(conn)
                # Ensure an asset product exists
                asset_id, _ = ensure_asset_product(conn, name="テストファンド", institution="テスト証券")

                # Add some dummy asset data
                upsert_asset_snapshot(
                    conn,
                    snapshot={
                        "asset_id": asset_id,
                        "period_month": "2025-01",
                        "valuation_date": "2025-01-31",
                        "current_value_yen": 100000,
                        "purchase_amount_yen": 5000,
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    snapshot={
                        "asset_id": asset_id,
                        "period_month": "2025-02",
                        "valuation_date": "2025-02-28",
                        "current_value_yen": 105000,
                        "purchase_amount_yen": 2000,
                    },
                )
                upsert_asset_snapshot(
                    conn,
                    snapshot={
                        "asset_id": asset_id,
                        "period_month": "2025-03",
                        "valuation_date": "2025-03-31",
                        "current_value_yen": 110000,
                        "purchase_amount_yen": 1000,
                    },
                )
                conn.commit()
            finally:
                conn.close()

            result = export_readonly_html(
                db_path=db_path,
                html_path=html_path,
                create_zip=False,
            )

            self.assertTrue(html_path.exists())
            self.assertGreater(result["asset_monthly_count"], 0)

            html = html_path.read_text(encoding="utf-8")

            # Assert that the chart logic is present in the script
            # Since the SVG is rendered at runtime by JS, we check the JS source embedded in HTML.
            self.assertIn('data-idx="${idx}"', html)
            self.assertIn('class="asset-chart-hit-area"', html)
            self.assertIn("node.addEventListener('click', () => {", html)
            self.assertIn("state.asset.chartPointIndex = Number.isFinite(next) ? next : chartRows.length - 1;", html)
            self.assertIn("renderAssetChart();", html)

            # Assert for the presence of the compare summary section template/logic
            self.assertIn('<div class="asset-chart-compare">', html)
            self.assertIn('評価額:', html)
            self.assertIn('総資産差（買い増し込み）:', html)
            self.assertIn('前月比:', html)


if __name__ == "__main__":
    unittest.main()
