from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue import analysis
from mfblue.analysis import build_analysis_input, get_analysis_if_exists, run_or_reuse_analysis
from mfblue.codex_app_server_client import CodexTurnResult
from mfblue.db import connect, ensure_account, init_db, summary_for_period, upsert_transaction


class FakeClient:
    calls = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    def run_text_turn(self, prompt: str) -> CodexTurnResult:
        FakeClient.calls += 1
        return CodexTurnResult(result_text=f"analysis-{FakeClient.calls}", thread_id="thr", turn_id="turn")


class FakeFailClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def run_text_turn(self, prompt: str) -> CodexTurnResult:
        raise analysis.CodexAppServerError("Codex App Serverに接続できません")


class AnalysisRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_client = analysis.CodexAppServerClient

    def tearDown(self) -> None:
        analysis.CodexAppServerClient = self._original_client

    def _seed_db(self, db_path: Path) -> None:
        conn = connect(db_path)
        try:
            init_db(conn)
            ensure_account(conn, "amazon-order-history", "Amazon注文履歴")
            ensure_account(conn, "amazon-order", "Amazonメール")
            tx_common = {
                "thread_id": None,
                "direction": "expense",
                "posted_at": None,
                "raw_description": "sample",
                "category_id": "daily",
                "subcategory": "Amazon",
            }
            upsert_transaction(
                conn,
                {
                    **tx_common,
                    "source_id": "amazon-order-history",
                    "account_id": "amazon-order-history",
                    "external_id": "a-001",
                    "occurred_at": "2026-05-10",
                    "merchant": "Amazon.co.jp",
                    "amount_yen": 1200,
                },
            )
            upsert_transaction(
                conn,
                {
                    **tx_common,
                    "source_id": "amazon-order",
                    "account_id": "amazon-order",
                    "external_id": "a-002",
                    "occurred_at": "2026-05-12",
                    "merchant": "Amazon.co.jp",
                    "amount_yen": 2500,
                },
            )
            upsert_transaction(
                conn,
                {
                    **tx_common,
                    "source_id": "paypay-card-csv",
                    "account_id": "paypay-card",
                    "external_id": "p-001",
                    "occurred_at": "2026-05-01",
                    "merchant": "コンビニ",
                    "amount_yen": 800,
                },
            )
            upsert_transaction(
                conn,
                {
                    **tx_common,
                    "source_id": "paypay-card-csv",
                    "account_id": "paypay-card",
                    "external_id": "p-002",
                    "merchant": "PayPayチャージ",
                    "category_id": "fund_movement",
                    "subcategory": "チャージ",
                    "occurred_at": "2026-05-15",
                    "amount_yen": 39000,
                },
            )
            conn.commit()
        finally:
            conn.close()

    def test_input_hash_changes_when_transaction_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            self._seed_db(db_path)

            conn = connect(db_path)
            try:
                init_db(conn)
                _, hash1 = build_analysis_input(
                    conn,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                )
                conn.execute(
                    "UPDATE transactions SET category_id = ?, subcategory = ?, updated_at = ? WHERE external_id = ?",
                    ("food", "外食", "2026-05-31T00:00:00+00:00", "a-001"),
                )
                conn.commit()
                _, hash2 = build_analysis_input(
                    conn,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                )
            finally:
                conn.close()

            self.assertNotEqual(hash1, hash2)

    def test_reuse_and_force_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            self._seed_db(db_path)
            analysis.CodexAppServerClient = FakeClient
            FakeClient.calls = 0

            config = {
                "analysis": {
                    "enabled": True,
                    "codex_app_server_url": "ws://127.0.0.1:8787",
                    "analyzer": "codex-app-server",
                    "analyzer_version": "v1",
                    "timeout_seconds": 30,
                }
            }

            conn = connect(db_path)
            try:
                init_db(conn)
                first = run_or_reuse_analysis(
                    conn,
                    config=config,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                    force=False,
                )
                second = run_or_reuse_analysis(
                    conn,
                    config=config,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                    force=False,
                )
                forced = run_or_reuse_analysis(
                    conn,
                    config=config,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                    force=True,
                )
                conn.commit()
            finally:
                conn.close()

            self.assertEqual(FakeClient.calls, 2)
            self.assertFalse(first["reused"])
            self.assertTrue(second["reused"])
            self.assertFalse(forced["reused"])

    def test_month_year_and_account_are_separated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            self._seed_db(db_path)

            conn = connect(db_path)
            try:
                init_db(conn)
                month_all = get_analysis_if_exists(
                    conn,
                    config={"analysis": {"analyzer": "codex-app-server", "analyzer_version": "v1"}},
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                )
                month_amz = get_analysis_if_exists(
                    conn,
                    config={"analysis": {"analyzer": "codex-app-server", "analyzer_version": "v1"}},
                    period_type="month",
                    period="2026-05",
                    account_id="amazon-order-history",
                    direction="expense",
                )
                month_amz_group = get_analysis_if_exists(
                    conn,
                    config={"analysis": {"analyzer": "codex-app-server", "analyzer_version": "v1"}},
                    period_type="month",
                    period="2026-05",
                    account_id="group:amazon",
                    account_ids=["amazon-order-history", "amazon-order"],
                    direction="expense",
                )
                year_all = get_analysis_if_exists(
                    conn,
                    config={"analysis": {"analyzer": "codex-app-server", "analyzer_version": "v1"}},
                    period_type="year",
                    period="2026",
                    account_id="all",
                    direction="expense",
                )
            finally:
                conn.close()

            self.assertNotEqual(month_all["input_hash"], month_amz["input_hash"])
            self.assertNotEqual(month_amz_group["input_hash"], month_amz["input_hash"])
            self.assertNotEqual(month_all["input_hash"], year_all["input_hash"])
            self.assertEqual(month_amz_group["account_id"], "group:amazon")

    def test_failed_run_is_saved_and_returned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            self._seed_db(db_path)
            analysis.CodexAppServerClient = FakeFailClient
            config = {
                "analysis": {
                    "enabled": True,
                    "codex_app_server_url": "ws://127.0.0.1:8787",
                    "analyzer": "codex-app-server",
                    "analyzer_version": "v1",
                    "timeout_seconds": 10,
                }
            }

            conn = connect(db_path)
            try:
                init_db(conn)
                failed = run_or_reuse_analysis(
                    conn,
                    config=config,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                    force=False,
                )
                conn.commit()

                saved = conn.execute(
                    "SELECT status, error_message FROM analysis_runs ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(failed["status"], "failed")
            self.assertIn("接続", failed.get("error_message") or "")
            self.assertEqual(saved["status"], "failed")

    def test_stale_analysis_is_returned_when_input_hash_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            self._seed_db(db_path)
            analysis.CodexAppServerClient = FakeClient
            FakeClient.calls = 0
            config = {
                "analysis": {
                    "enabled": True,
                    "codex_app_server_url": "ws://127.0.0.1:8787",
                    "analyzer": "codex-app-server",
                    "analyzer_version": "v1",
                    "timeout_seconds": 30,
                }
            }

            conn = connect(db_path)
            try:
                init_db(conn)
                first = run_or_reuse_analysis(
                    conn,
                    config=config,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                    force=False,
                )
                conn.execute(
                    "UPDATE transactions SET category_id = ?, subcategory = ?, updated_at = ? WHERE external_id = ?",
                    ("food", "外食", "2026-05-31T00:00:00+00:00", "a-001"),
                )
                conn.commit()
                stale = get_analysis_if_exists(
                    conn,
                    config=config,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                )
            finally:
                conn.close()

            self.assertTrue(stale["has_analysis"])
            self.assertTrue(stale["stale"])
            self.assertEqual(stale["result_text"], first["result_text"])
            self.assertNotEqual(stale["input_hash"], first["input_hash"])

    def test_fund_movement_is_excluded_from_expense_summary_and_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.sqlite3"
            self._seed_db(db_path)

            conn = connect(db_path)
            try:
                init_db(conn)
                payload, _ = build_analysis_input(
                    conn,
                    period_type="month",
                    period="2026-05",
                    account_id="all",
                    direction="expense",
                )
                summary = summary_for_period(conn, month="2026-05", direction="expense")
            finally:
                conn.close()

            self.assertEqual(payload["expense_total"], 4500)
            self.assertEqual(payload["excluded_fund_movement"]["amount_yen"], 39000)
            self.assertNotIn("fund_movement", {row["category_id"] for row in payload["category_totals"]})
            self.assertEqual(summary["expense_total"], 4500)
            self.assertEqual(summary["fund_movement_total"], 39000)


if __name__ == "__main__":
    unittest.main()
