from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import connect, ensure_account, init_db, upsert_transaction


class DbUniquenessTests(unittest.TestCase):
    def test_same_external_id_can_exist_across_different_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                ensure_account(conn, "paypay-card", "PayPayカード")
                ensure_account(conn, "amazon-order", "Amazonメール")

                tx_common = {
                    "thread_id": None,
                    "direction": "expense",
                    "occurred_at": "2026-05-01",
                    "posted_at": None,
                    "merchant": "Amazon.co.jp",
                    "raw_description": "sample",
                    "amount_yen": 1000,
                    "category_id": "uncategorized",
                    "subcategory": "未分類",
                }
                result1 = upsert_transaction(
                    conn,
                    {
                        **tx_common,
                        "source_id": "paypay-card",
                        "account_id": "paypay-card",
                        "external_id": "same-message-id",
                    },
                )
                result2 = upsert_transaction(
                    conn,
                    {
                        **tx_common,
                        "source_id": "amazon-order",
                        "account_id": "amazon-order",
                        "external_id": "same-message-id",
                    },
                )
                self.assertEqual(result1, "inserted")
                self.assertEqual(result2, "inserted")
                count = conn.execute(
                    "SELECT COUNT(*) AS c FROM transactions WHERE external_id = ?",
                    ("same-message-id",),
                ).fetchone()["c"]
                self.assertEqual(count, 2)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
