from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mfblue.db import connect, init_db
from mfblue.sync_gmail import _run_source


class SyncGmailAmazonOrderFlowTests(unittest.TestCase):
    def _make_db_context(self, db_path: Path):
        @contextmanager
        def _ctx():
            conn = connect(db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        return _ctx

    def _run_sync(self, db_path: Path, headers: dict[str, str], body: str) -> dict[str, int | str]:
        source_cfg = {
            "source_id": "amazon-order",
            "account_name": "Amazon\u30e1\u30fc\u30eb",
            "query": "subject:\u6ce8\u6587\u6e08\u307f",
            "max_results": 10,
        }
        with patch("mfblue.sync_gmail.db", self._make_db_context(db_path)), patch(
            "mfblue.sync_gmail.search_message_ids", return_value=["message-1"]
        ), patch("mfblue.sync_gmail.get_message", return_value={"threadId": "thread-1", "payload": {}}), patch(
            "mfblue.sync_gmail.headers_to_dict", return_value=headers
        ), patch("mfblue.sync_gmail.extract_text_from_payload", return_value=body), patch(
            "mfblue.sync_gmail.categorize", return_value=("uncategorized", "\u672a\u5206\u985e")
        ):
            return _run_source(source_cfg)

    def test_amazon_order_mail_is_upserted_instead_of_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                conn.commit()
            finally:
                conn.close()

            subject = "\u6ce8\u6587\u6e08\u307f: TESCOM \u30c9\u30e9\u30a4\u30e4\u30fc"
            body = """\
\u6ce8\u6587\u65e5: 2026\u5e7405\u670813\u65e5
\u6ce8\u6587\u756a\u53f7: 999-1111111-2222222
\u3054\u8acb\u6c42\u984d: \uffe55,478
\u914d\u9001\u5148: \u6771\u4eac\u90fd\u5343\u4ee3\u7530\u533a...
\u914d\u9001\u4e88\u5b9a: 2026\u5e7405\u670815\u65e5
\u304a\u5c4a\u3051\u4e88\u5b9a: 5\u670815\u65e5
"""
            headers = {
                "Subject": subject,
                "From": "Amazon.co.jp <auto-confirm@amazon.co.jp>",
                "Date": "Wed, 13 May 2026 10:00:00 +0900",
            }

            result = self._run_sync(db_path, headers, body)

            self.assertEqual(result["fetched"], 1)
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["updated"], 0)
            self.assertEqual(result["skipped"], 0)
            self.assertEqual(result["errors"], 0)

            conn = connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT source_id, external_id, merchant, amount_yen, raw_description FROM transactions"
                ).fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["source_id"], "amazon-order")
                self.assertEqual(rows[0]["external_id"], "amazon-order:999-1111111-2222222")
                self.assertEqual(rows[0]["merchant"], "Amazon.co.jp")
                self.assertEqual(rows[0]["amount_yen"], 5478)
                self.assertIn("TESCOM", rows[0]["raw_description"])
            finally:
                conn.close()

    def test_amazon_order_same_order_number_updates_existing_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            conn = connect(db_path)
            try:
                init_db(conn)
                conn.commit()
            finally:
                conn.close()

            subject = "\u6ce8\u6587\u6e08\u307f: TESCOM \u30c9\u30e9\u30a4\u30e4\u30fc"
            headers = {
                "Subject": subject,
                "From": "Amazon.co.jp <auto-confirm@amazon.co.jp>",
                "Date": "Wed, 13 May 2026 10:00:00 +0900",
            }
            first_body = """\
\u6ce8\u6587\u65e5: 2026\u5e7405\u670813\u65e5
\u6ce8\u6587\u756a\u53f7: 999-1111111-2222222
\u3054\u8acb\u6c42\u984d: \uffe55,478
\u914d\u9001\u5148: \u6771\u4eac\u90fd\u5343\u4ee3\u7530\u533a...
"""
            second_body = """\
\u6ce8\u6587\u65e5: 2026\u5e7405\u670813\u65e5
\u6ce8\u6587\u756a\u53f7: 999-1111111-2222222
\u3054\u8acb\u6c42\u984d: \uffe55,980
\u914d\u9001\u5148: \u6771\u4eac\u90fd\u5343\u4ee3\u7530\u533a...
"""

            first = self._run_sync(db_path, headers, first_body)
            second = self._run_sync(db_path, headers, second_body)

            self.assertEqual(first["inserted"], 1)
            self.assertEqual(first["updated"], 0)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(second["updated"], 1)
            self.assertEqual(second["skipped"], 0)
            self.assertEqual(second["errors"], 0)

            conn = connect(db_path)
            try:
                row = conn.execute(
                    "SELECT amount_yen FROM transactions WHERE source_id = ? AND external_id = ?",
                    ("amazon-order", "amazon-order:999-1111111-2222222"),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["amount_yen"], 5980)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
