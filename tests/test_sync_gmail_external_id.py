from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.db import connect, ensure_account, init_db, upsert_transaction
from mfblue.parser import ParsedTransaction
from mfblue.sync_gmail import _migrate_legacy_amazon_external_id, _preferred_external_id


class SyncGmailExternalIdTests(unittest.TestCase):
    def test_preferred_external_id_uses_order_number_for_amazon(self) -> None:
        parsed = ParsedTransaction(
            occurred_at="2026-05-13",
            merchant="Amazon.co.jp",
            amount_yen=1000,
            raw_description="注文済み / 注文番号:123-1234567-1234567",
            external_id_hint="123-1234567-1234567",
        )
        self.assertEqual(
            _preferred_external_id("amazon-order", "gmail-message-id-1", parsed),
            "amazon-order:123-1234567-1234567",
        )

    def test_preferred_external_id_keeps_message_id_for_paypay(self) -> None:
        parsed = ParsedTransaction(
            occurred_at="2026-05-13",
            merchant="テスト",
            amount_yen=1000,
            raw_description="test",
            external_id_hint="123-1234567-1234567",
        )
        self.assertEqual(_preferred_external_id("paypay-card", "gmail-message-id-1", parsed), "gmail-message-id-1")

    def test_migrate_legacy_external_id_to_order_number(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                ensure_account(conn, "amazon-order", "Amazonメール")
                upsert_transaction(
                    conn,
                    {
                        "source_id": "amazon-order",
                        "account_id": "amazon-order",
                        "external_id": "gmail-message-id-1",
                        "thread_id": "thread-1",
                        "direction": "expense",
                        "occurred_at": "2026-05-13",
                        "posted_at": None,
                        "merchant": "Amazon.co.jp",
                        "raw_description": "注文済み",
                        "amount_yen": 1000,
                        "category_id": "uncategorized",
                        "subcategory": "未分類",
                    },
                )

                _migrate_legacy_amazon_external_id(
                    conn,
                    "amazon-order",
                    "gmail-message-id-1",
                    "amazon-order:123-1234567-1234567",
                )

                migrated = conn.execute(
                    "SELECT external_id FROM transactions WHERE source_id = ?",
                    ("amazon-order",),
                ).fetchall()
                self.assertEqual(len(migrated), 1)
                self.assertEqual(migrated[0]["external_id"], "amazon-order:123-1234567-1234567")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
