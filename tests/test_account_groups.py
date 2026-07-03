from __future__ import annotations

import unittest

from mfblue.account_groups import resolve_account_filter


class AccountGroupTests(unittest.TestCase):
    def test_resolve_account_group_amazon(self) -> None:
        account_id, account_ids = resolve_account_filter(account_id="all", account_group="amazon")
        self.assertEqual(account_id, "group:amazon")
        self.assertEqual(account_ids, ["amazon-order-history", "amazon-order"])

    def test_resolve_account_id_shortcut_amazon(self) -> None:
        account_id, account_ids = resolve_account_filter(account_id="amazon", account_group=None)
        self.assertEqual(account_id, "group:amazon")
        self.assertEqual(account_ids, ["amazon-order-history", "amazon-order"])

    def test_reject_unknown_group(self) -> None:
        with self.assertRaises(ValueError):
            resolve_account_filter(account_id="all", account_group="unknown")


if __name__ == "__main__":
    unittest.main()
