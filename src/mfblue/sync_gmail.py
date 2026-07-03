from __future__ import annotations

import sys
import traceback
from typing import Any, Callable

from .categorizer import categorize
from .config import load_config
from .db import db, ensure_account, init_db, upsert_transaction, utc_now_iso
from .gmail_client import extract_text_from_payload, get_message, headers_to_dict, search_message_ids
from .parser import ParseError, ParseSkip, ParsedTransaction, parse_amazon_order_email, parse_paypay_card_email

ParserFunc = Callable[[str, str, dict[str, str]], ParsedTransaction]

PARSERS: dict[str, ParserFunc] = {
    "paypay-card": parse_paypay_card_email,
    "paypay_card": parse_paypay_card_email,
    "amazon-order": parse_amazon_order_email,
    "amazon_order": parse_amazon_order_email,
}


def _gmail_sources(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gmail_cfg = cfg["gmail"]
    sources = gmail_cfg.get("sources")
    if isinstance(sources, list) and sources:
        result: list[dict[str, Any]] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            merged = dict(gmail_cfg)
            merged.update(source)
            result.append(merged)
        return result
    return [gmail_cfg]


def _select_parser(source_cfg: dict[str, Any]) -> ParserFunc:
    parser_key = str(source_cfg.get("parser") or source_cfg.get("source_id") or "").strip().lower()
    parser = PARSERS.get(parser_key)
    if not parser:
        raise ValueError(f"Unsupported parser/source: {parser_key}")
    return parser


def _preferred_external_id(source_id: str, message_id: str, parsed: ParsedTransaction) -> str:
    hint = (parsed.external_id_hint or "").strip()
    if source_id == "amazon-order" and hint:
        return f"amazon-order:{hint}"
    return message_id


def _migrate_legacy_amazon_external_id(
    conn: Any, source_id: str, message_id: str, preferred_external_id: str
) -> None:
    if source_id != "amazon-order":
        return
    if preferred_external_id == message_id:
        return
    preferred_exists = conn.execute(
        "SELECT 1 FROM transactions WHERE source_id = ? AND external_id = ?",
        (source_id, preferred_external_id),
    ).fetchone()
    if preferred_exists:
        return
    conn.execute(
        """
        UPDATE transactions
        SET external_id = ?, updated_at = ?
        WHERE source_id = ? AND external_id = ?
        """,
        (preferred_external_id, utc_now_iso(), source_id, message_id),
    )


def _run_source(source_cfg: dict[str, Any]) -> dict[str, Any]:
    source_id = str(source_cfg["source_id"])
    account_name = str(source_cfg["account_name"])
    query = str(source_cfg["query"])
    max_results = int(source_cfg.get("max_results", 100))
    parser = _select_parser(source_cfg)

    with db() as conn:
        ensure_account(conn, source_id, account_name)
        started = utc_now_iso()
        cur = conn.execute(
            "INSERT INTO import_runs(source_id, started_at, status, message) VALUES (?, ?, 'running', ?)",
            (source_id, started, query),
        )
        run_id = int(cur.lastrowid)

    fetched = inserted = updated = skipped = errors = 0
    try:
        message_ids = search_message_ids(query, max_results=max_results)
        fetched = len(message_ids)
        for message_id in message_ids:
            subject = ""
            try:
                msg = get_message(message_id)
                payload = msg.get("payload", {})
                headers = headers_to_dict(payload.get("headers", []))
                subject = headers.get("subject") or headers.get("Subject") or ""
                body = extract_text_from_payload(payload)
                parsed = parser(subject, body, headers)
                external_id = _preferred_external_id(source_id, message_id, parsed)
                with db() as conn:
                    _migrate_legacy_amazon_external_id(conn, source_id, message_id, external_id)
                    category_id, subcategory = categorize(
                        conn,
                        merchant=parsed.merchant,
                        description=parsed.raw_description,
                        source_id=source_id,
                    )
                    result = upsert_transaction(
                        conn,
                        {
                            "source_id": source_id,
                            "account_id": source_id,
                            "external_id": external_id,
                            "thread_id": msg.get("threadId"),
                            "direction": parsed.direction,
                            "occurred_at": parsed.occurred_at,
                            "posted_at": None,
                            "merchant": parsed.merchant,
                            "raw_description": parsed.raw_description,
                            "amount_yen": parsed.amount_yen,
                            "category_id": category_id,
                            "subcategory": subcategory,
                        },
                    )
                    if result == "inserted":
                        inserted += 1
                    elif result == "updated":
                        updated += 1
                    else:
                        skipped += 1
            except ParseSkip:
                skipped += 1
            except ParseError as e:
                errors += 1
                with db() as conn:
                    conn.execute(
                        "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, source_id, message_id, subject, str(e), utc_now_iso()),
                    )
            except Exception:
                errors += 1
                with db() as conn:
                    conn.execute(
                        "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, source_id, message_id, subject, traceback.format_exc(), utc_now_iso()),
                    )
        with db() as conn:
            conn.execute(
                """
                UPDATE import_runs
                SET finished_at = ?, status = 'success', fetched_count = ?, inserted_count = ?, updated_count = ?,
                    skipped_count = ?, error_count = ?
                WHERE id = ?
                """,
                (utc_now_iso(), fetched, inserted, updated, skipped, errors, run_id),
            )
        return {
            "status": "success",
            "source_id": source_id,
            "run_id": run_id,
            "fetched": fetched,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }
    except Exception:
        with db() as conn:
            conn.execute(
                "UPDATE import_runs SET finished_at = ?, status = 'failed', error_count = ?, message = ? WHERE id = ?",
                (utc_now_iso(), errors + 1, traceback.format_exc(), run_id),
            )
        raise


def sync_once() -> dict[str, Any]:
    cfg = load_config()
    with db() as conn:
        init_db(conn)

    source_results = [_run_source(source_cfg) for source_cfg in _gmail_sources(cfg)]
    return {
        "status": "success",
        "sources": source_results,
        "fetched": sum(int(r["fetched"]) for r in source_results),
        "inserted": sum(int(r["inserted"]) for r in source_results),
        "updated": sum(int(r["updated"]) for r in source_results),
        "skipped": sum(int(r["skipped"]) for r in source_results),
        "errors": sum(int(r["errors"]) for r in source_results),
    }


def main(argv: list[str] | None = None) -> int:
    result = sync_once()
    print("Gmail同期が完了しました。")
    for source in result["sources"]:
        print(
            f"[{source['source_id']}] 取得: {source['fetched']} / 新規: {source['inserted']} / "
            f"更新: {source['updated']} / スキップ: {source['skipped']} / エラー: {source['errors']}"
        )
    print(
        f"[合計] 取得: {result['fetched']} / 新規: {result['inserted']} / "
        f"更新: {result['updated']} / スキップ: {result['skipped']} / エラー: {result['errors']}"
    )
    if result["errors"]:
        print("一部のメールは解析できませんでした。UIまたはSQLiteの import_errors を確認してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
