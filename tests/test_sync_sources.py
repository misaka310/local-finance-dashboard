from __future__ import annotations

import unittest

from mfblue.sync_gmail import _gmail_sources, _select_parser


class SyncSourceConfigTests(unittest.TestCase):
    def test_single_gmail_config_is_kept_backward_compatible(self) -> None:
        cfg = {
            "gmail": {
                "source_id": "paypay-card",
                "account_name": "PayPayカード",
                "query": "from:paypay-card.co.jp",
                "max_results": 50,
            }
        }
        sources = _gmail_sources(cfg)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source_id"], "paypay-card")
        self.assertEqual(sources[0]["max_results"], 50)

    def test_sources_config_is_preferred(self) -> None:
        cfg = {
            "gmail": {
                "source_id": "paypay-card",
                "account_name": "fallback",
                "query": "fallback-query",
                "max_results": 100,
                "sources": [
                    {"source_id": "paypay-card", "account_name": "PayPay", "query": "q1"},
                    {"source_id": "amazon-order", "account_name": "Amazonメール", "query": "q2", "parser": "amazon-order"},
                ],
            }
        }
        sources = _gmail_sources(cfg)
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[1]["source_id"], "amazon-order")
        self.assertEqual(sources[1]["max_results"], 100)
        self.assertIsNotNone(_select_parser(sources[0]))
        self.assertIsNotNone(_select_parser(sources[1]))


if __name__ == "__main__":
    unittest.main()
