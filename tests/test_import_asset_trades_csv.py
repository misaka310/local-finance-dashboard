from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import connect
from mfblue.import_asset_trades_csv import import_trade_files
from mfblue.paths import project_path


class ImportAssetTradesCsvTests(unittest.TestCase):
    def test_import_trades_and_normalize_account_type_and_trade_type(self) -> None:
        fixture = project_path("tests", "fixtures", "asset_trades_sample.csv")
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            result = import_trade_files([fixture], db_path=db_path)
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["inserted"], 3)

            conn = connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT fund_name, account_type, trade_type, quantity, unit_price, amount_yen FROM asset_trades ORDER BY id"
                ).fetchall()
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[0]["account_type"], "新NISA（成長投資枠）")
                self.assertEqual(rows[0]["trade_type"], "dividend_reinvest")
                self.assertEqual(rows[1]["account_type"], "新NISA（つみたて投資枠）")
                self.assertEqual(rows[1]["trade_type"], "buy")
                self.assertEqual(rows[2]["trade_type"], "sell")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

