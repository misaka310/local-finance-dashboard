from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import (
    connect,
    ensure_account,
    init_db,
    list_available_accounts,
    summary_for_period,
    transactions_for_period,
    upsert_transaction,
)


class DbAccountFilterTests(unittest.TestCase):
    def test_summary_and_transactions_can_filter_by_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                ensure_account(conn, "amazon-order-history", "Amazon注文履歴")
                ensure_account(conn, "amazon-order", "Amazonメール")

                common = {
                    "thread_id": None,
                    "direction": "expense",
                    "occurred_at": "2026-05-10",
                    "posted_at": None,
                    "merchant": "Amazon.co.jp",
                    "raw_description": "sample",
                    "category_id": "daily",
                    "subcategory": "Amazon",
                }
                upsert_transaction(
                    conn,
                    {
                        **common,
                        "source_id": "paypay-card-csv",
                        "account_id": "paypay-card",
                        "external_id": "pp-1",
                        "amount_yen": 1000,
                    },
                )
                upsert_transaction(
                    conn,
                    {
                        **common,
                        "source_id": "amazon-order-history",
                        "account_id": "amazon-order-history",
                        "external_id": "amz-1",
                        "amount_yen": 3000,
                    },
                )
                upsert_transaction(
                    conn,
                    {
                        **common,
                        "source_id": "amazon-order",
                        "account_id": "amazon-order",
                        "external_id": "amz-2",
                        "amount_yen": 700,
                    },
                )
                conn.commit()

                all_summary = summary_for_period(conn, month="2026-05", direction="expense")
                amazon_summary = summary_for_period(
                    conn,
                    month="2026-05",
                    direction="expense",
                    account_id="amazon-order-history",
                )
                amazon_group_summary = summary_for_period(
                    conn,
                    month="2026-05",
                    direction="expense",
                    account_ids=["amazon-order-history", "amazon-order"],
                )
                self.assertEqual(all_summary["expense_total"], 4700)
                self.assertEqual(amazon_summary["expense_total"], 3000)
                self.assertEqual(amazon_group_summary["expense_total"], 3700)

                txs = transactions_for_period(
                    conn,
                    month="2026-05",
                    direction="expense",
                    account_id="amazon-order-history",
                )
                self.assertEqual(len(txs), 1)
                self.assertEqual(txs[0]["external_id"], "amz-1")

                grouped_txs = transactions_for_period(
                    conn,
                    month="2026-05",
                    direction="expense",
                    account_ids=["amazon-order-history", "amazon-order"],
                )
                self.assertEqual(len(grouped_txs), 2)

                accounts = list_available_accounts(conn)
                account_ids = {row["id"] for row in accounts}
                self.assertIn("paypay-card", account_ids)
                self.assertIn("amazon-order-history", account_ids)
                self.assertIn("amazon-order", account_ids)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
