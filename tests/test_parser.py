from __future__ import annotations

import unittest

from mfblue.parser import ParseSkip, parse_amazon_order_email, parse_paypay_card_email


class ParserTests(unittest.TestCase):
    def test_parse_amazon_order_subject_confirmation_with_delivery_words(self) -> None:
        subject = "\u6ce8\u6587\u6e08\u307f: TESCOM \u30c9\u30e9\u30a4\u30e4\u30fc"
        body = """\
\u6ce8\u6587\u65e5: 2026\u5e7405\u670813\u65e5
\u6ce8\u6587\u756a\u53f7: 999-1111111-2222222
\u3054\u8acb\u6c42\u984d: \uffe55,478
\u914d\u9001\u5148: \u6771\u4eac\u90fd\u5343\u4ee3\u7530\u533a...
\u914d\u9001\u4e88\u5b9a: 2026\u5e7405\u670815\u65e5
\u304a\u5c4a\u3051\u4e88\u5b9a: 5\u670815\u65e5
"""
        headers = {"Date": "Wed, 13 May 2026 10:00:00 +0900", "From": "Amazon.co.jp <auto-confirm@amazon.co.jp>"}
        parsed = parse_amazon_order_email(subject, body, headers)
        self.assertEqual(parsed.occurred_at, "2026-05-13")
        self.assertEqual(parsed.merchant, "Amazon.co.jp")
        self.assertEqual(parsed.amount_yen, 5478)
        self.assertEqual(parsed.direction, "expense")
        self.assertEqual(parsed.external_id_hint, "999-1111111-2222222")
        self.assertEqual(parsed.raw_description, f"{subject} / \u6ce8\u6587\u756a\u53f7:999-1111111-2222222")

    def test_parse_amazon_order_accepts_body_match_without_subject_keywords(self) -> None:
        subject = "Amazon.co.jp receipt"
        body = """\
amazon.co.jp
\u6ce8\u6587\u756a\u53f7: 111-2222222-3333333
\u3054\u8acb\u6c42\u984d: \uffe52,100
\u6ce8\u6587\u65e5: 2026\u5e7405\u670820\u65e5
\u914d\u9001\u4e88\u5b9a: 2026\u5e7405\u670822\u65e5
"""
        headers = {"Date": "Wed, 20 May 2026 18:00:00 +0900", "From": "Amazon.co.jp <auto-confirm@amazon.co.jp>"}
        parsed = parse_amazon_order_email(subject, body, headers)
        self.assertEqual(parsed.occurred_at, "2026-05-20")
        self.assertEqual(parsed.amount_yen, 2100)

    def test_parse_amazon_order_accepts_jpy_amount_on_next_line(self) -> None:
        subject = "注文済み: TESCOM ドライヤー"
        body = """\
注文番号
503-1813186-3007018
数量: 1
8500 JPY
合計
8200 JPY
"""
        headers = {"Date": "Tue, 19 May 2026 20:00:00 +0900", "From": "Amazon.co.jp <auto-confirm@amazon.co.jp>"}
        parsed = parse_amazon_order_email(subject, body, headers)
        self.assertEqual(parsed.occurred_at, "2026-05-19")
        self.assertEqual(parsed.amount_yen, 8200)
        self.assertEqual(parsed.external_id_hint, "503-1813186-3007018")

    def test_parse_amazon_rejects_shipping_cancel_refund_return(self) -> None:
        headers = {"Date": "Tue, 12 May 2026 09:00:00 +0900", "From": "Amazon.co.jp <auto-confirm@amazon.co.jp>"}
        body = """\
\u6ce8\u6587\u756a\u53f7: 123-1234567-1234567
\u6ce8\u6587\u5408\u8a08: 1,000\u5186
"""
        subjects = [
            "Amazon.co.jp \u767a\u9001\u3057\u307e\u3057\u305f",
            "Amazon.co.jp \u914d\u9054\u5b8c\u4e86\u306e\u304a\u77e5\u3089\u305b",
            "Amazon.co.jp \u3054\u6ce8\u6587\u306e\u30ad\u30e3\u30f3\u30bb\u30eb",
            "Amazon.co.jp \u8fd4\u91d1\u306e\u304a\u77e5\u3089\u305b",
            "Amazon.co.jp \u30bf\u30a4\u30e0\u30bb\u30fc\u30eb\u306e\u304a\u77e5\u3089\u305b",
        ]
        for subject in subjects:
            with self.subTest(subject=subject):
                with self.assertRaises(ParseSkip):
                    parse_amazon_order_email(subject, body, headers)

        subject_ok = "Amazon.co.jp \u3054\u6ce8\u6587\u5185\u5bb9\u306e\u78ba\u8a8d"
        bad_bodies = [
            body + "\u30ad\u30e3\u30f3\u30bb\u30eb\u3055\u308c\u307e\u3057\u305f\n",
            body + "\u8fd4\u91d1\u51e6\u7406\u3092\u884c\u3044\u307e\u3057\u305f\n",
            body + "\u8fd4\u54c1\u3092\u53d7\u3051\u4ed8\u3051\u307e\u3057\u305f\n",
        ]
        for bad in bad_bodies:
            with self.subTest(body=bad):
                with self.assertRaises(ParseSkip):
                    parse_amazon_order_email(subject_ok, bad, headers)

    def test_parse_paypay_parser_still_works(self) -> None:
        subject = "\u3010PayPay\u30ab\u30fc\u30c9\u3011\u3054\u5229\u7528\u306e\u304a\u77e5\u3089\u305b"
        body = """\
\u3054\u5229\u7528\u65e5: 2026\u5e7405\u670809\u65e5
\u3054\u5229\u7528\u5148: \u30bb\u30d6\u30f3\u30a4\u30ec\u30d6\u30f3
\u3054\u5229\u7528\u91d1\u984d: 2,345\u5186"""
        headers = {"Date": "Sat, 09 May 2026 08:00:00 +0900"}
        parsed = parse_paypay_card_email(subject, body, headers)
        self.assertEqual(parsed.occurred_at, "2026-05-09")
        self.assertEqual(parsed.merchant, "\u30bb\u30d6\u30f3\u30a4\u30ec\u30d6\u30f3")
        self.assertEqual(parsed.amount_yen, 2345)


if __name__ == "__main__":
    unittest.main()
