from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import connect
from mfblue.import_assets_csv import import_files, parse_number


class ImportAssetsCsvTests(unittest.TestCase):
    def test_parse_number_supports_currency_symbols(self) -> None:
        self.assertEqual(parse_number("2,769,009円"), 2769009.0)
        self.assertEqual(parse_number("+11.65%"), 11.65)
        self.assertEqual(parse_number("634,439口"), 634439.0)
        self.assertEqual(parse_number("＋32,674円"), 32674.0)

    def test_upsert_same_asset_and_month_updates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "test.sqlite3"
            csv_path = temp_root / "assets.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "ファンド名,保有口数,基準価額,取得単価,評価額,取得金額,評価損益,評価損益率,評価損益 前日比,前日比率,分配金受取方法,評価日",
                        "\"ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）\",\"634,439口\",\"43,645円\",\"39,090円\",\"2,769,009円\",\"2,480,022円\",\"+288,987円\",\"+11.65%\",\"+32,674円\",\"+1.19%\",再投資,2026/02/28",
                    ]
                ),
                encoding="utf-8",
            )

            first = import_files(
                [csv_path],
                db_path=db_path,
                valuation_date=None,
                institution="SBI証券",
                account_type="新NISA",
                asset_type="investment_trust",
            )
            self.assertEqual(first["inserted"], 1)

            csv_path.write_text(
                "\n".join(
                    [
                        "ファンド名,保有口数,基準価額,取得単価,評価額,取得金額,評価損益,評価損益率,評価損益 前日比,前日比率,分配金受取方法,評価日",
                        "\"eMAXIS Slim 米国株式（S&P500）\",\"634,439口\",\"43,645円\",\"39,090円\",\"2,800,000円\",\"2,480,022円\",\"+319,978円\",\"+12.90%\",\"+1,000円\",\"+0.03%\",再投資,2026/02/28",
                    ]
                ),
                encoding="utf-8",
            )
            second = import_files(
                [csv_path],
                db_path=db_path,
                valuation_date=None,
                institution="SBI証券",
                account_type="新NISA",
                asset_type="investment_trust",
            )
            self.assertEqual(second["updated"], 1)

            conn = connect(db_path)
            try:
                products = conn.execute("SELECT COUNT(*) AS c FROM asset_products").fetchone()["c"]
                snapshots = conn.execute("SELECT COUNT(*) AS c FROM asset_snapshots").fetchone()["c"]
                value = conn.execute("SELECT current_value_yen FROM asset_snapshots").fetchone()["current_value_yen"]
                self.assertEqual(products, 1)
                self.assertEqual(snapshots, 1)
                self.assertEqual(value, 2800000)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
