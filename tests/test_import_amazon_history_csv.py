from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import connect
from mfblue.import_amazon_history_csv import import_files


class ImportAmazonHistoryCsvTests(unittest.TestCase):
    def test_import_and_reimport_updates_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "test.sqlite3"
            csv_path = temp_root / "amazon_orders.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "source_id,account_id,external_id,occurred_at,merchant,raw_description,amount_yen,direction,category_id,subcategory",
                        "amazon-order-history,amazon-order-history,ORDER-001,2026-05-01,Amazon.co.jp,ORDER-001,1200,expense,daily,Amazon",
                        "amazon-order-history,amazon-order-history,ORDER-000,2026-05-01,Amazon.co.jp,ORDER-000,0,expense,daily,Amazon",
                        "amazon-order-history,amazon-order-history,ORDER-INVALID,2026-05-01,Amazon.co.jp,ORDER-INVALID,1500,expense,not_exists,Amazon",
                    ]
                ),
                encoding="utf-8",
            )

            first = import_files([csv_path], db_path=db_path)
            self.assertEqual(first["files"], 1)
            self.assertEqual(first["inserted"], 1)
            self.assertEqual(first["updated"], 0)
            self.assertEqual(first["skipped"], 1)
            self.assertEqual(first["errors"], 1)

            second = import_files([csv_path], db_path=db_path)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(second["updated"], 1)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(second["errors"], 1)

            conn = connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT source_id, account_id, external_id, amount_yen, category_id, subcategory
                    FROM transactions
                    ORDER BY id
                    """
                ).fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["source_id"], "amazon-order-history")
                self.assertEqual(rows[0]["account_id"], "amazon-order-history")
                self.assertEqual(rows[0]["external_id"], "ORDER-001")
                self.assertEqual(rows[0]["amount_yen"], 1200)
                self.assertEqual(rows[0]["category_id"], "daily")
                self.assertEqual(rows[0]["subcategory"], "Amazon")

                error_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM import_errors WHERE source_id = ?",
                    ("amazon-order-history",),
                ).fetchone()["c"]
                self.assertEqual(error_count, 2)
            finally:
                conn.close()

    def test_dry_run_does_not_write_transactions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "test.sqlite3"
            csv_path = temp_root / "amazon_orders.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "external_id,occurred_at,merchant,raw_description,amount_yen,direction,category_id,subcategory",
                        "ORDER-101,2026-05-01,Amazon.co.jp,ORDER-101,2000,expense,daily,Amazon",
                    ]
                ),
                encoding="utf-8",
            )

            preview = import_files([csv_path], db_path=db_path, dry_run=True)
            self.assertEqual(preview["inserted"], 1)
            self.assertEqual(preview["updated"], 0)

            conn = connect(db_path)
            try:
                count = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
                self.assertEqual(count, 0)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
