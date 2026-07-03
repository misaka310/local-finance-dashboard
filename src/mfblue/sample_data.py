from __future__ import annotations

from datetime import date

from .categorizer import categorize
from .db import db, ensure_account, init_db, upsert_transaction

SAMPLE = [
    ("セブンイレブン", 680, "food", "コンビニ"),
    ("スターバックス", 540, "food", "カフェ"),
    ("Amazon", 2980, "uncategorized", "未分類"),
    ("Spotify", 980, "hobby", "サブスク"),
    ("マツモトキヨシ", 1320, "daily", "ドラッグストア"),
]


def main() -> int:
    today = date.today().isoformat()
    with db() as conn:
        init_db(conn)
        ensure_account(conn, "paypay-card", "PayPayカード")
        for i, (merchant, amount, _, _) in enumerate(SAMPLE, start=1):
            cat, sub = categorize(conn, merchant, merchant, "paypay-card")
            upsert_transaction(
                conn,
                {
                    "source_id": "paypay-card",
                    "account_id": "paypay-card",
                    "external_id": f"sample-{date.today().isoformat()}-{i}",
                    "thread_id": None,
                    "direction": "expense",
                    "occurred_at": today,
                    "posted_at": None,
                    "merchant": merchant,
                    "raw_description": f"サンプル / {merchant}",
                    "amount_yen": amount,
                    "category_id": cat,
                    "subcategory": sub,
                },
            )
    print("サンプルデータを追加しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
