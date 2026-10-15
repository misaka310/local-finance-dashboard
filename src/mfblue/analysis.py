from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from typing import Any

from .codex_app_server_client import CodexAppServerClient, CodexAppServerError
from .db import (
    FUND_MOVEMENT_CATEGORY_ID,
    is_fund_movement_category,
    month_bounds,
    utc_now_iso,
    year_bounds,
)

MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
YEAR_RE = re.compile(r"^20\d{2}$")


def _console_safe_text(value: Any, stream: Any | None = None) -> str:
    text = str(value)
    target = stream if stream is not None else sys.stdout
    encoding = getattr(target, "encoding", None) or "utf-8"
    try:
        return text.encode(encoding, errors="backslashreplace").decode(encoding)
    except LookupError:
        return text.encode("ascii", errors="backslashreplace").decode("ascii")


class AnalysisError(RuntimeError):
    pass


def normalize_direction(direction: str) -> str:
    value = str(direction or "").strip().lower() or "expense"
    if value not in {"expense", "income"}:
        raise AnalysisError("direction は expense または income を指定してください")
    return value


def resolve_period(period_type: str, month: str | None = None, year: str | None = None) -> str:
    if period_type == "month":
        value = month or ""
        if not MONTH_RE.match(value):
            raise AnalysisError("month は YYYY-MM 形式で指定してください")
        return value
    if period_type == "year":
        value = year or ""
        if not YEAR_RE.match(value):
            raise AnalysisError("year は YYYY 形式で指定してください")
        return value
    raise AnalysisError("period_type は month または year を指定してください")


def _period_bounds(period_type: str, period: str) -> tuple[str, str]:
    if period_type == "month":
        return month_bounds(period)
    return year_bounds(period)


def _shift_month(month: str, delta: int) -> str:
    y, m = [int(x) for x in month.split("-")]
    total = y * 12 + (m - 1) + delta
    next_year = total // 12
    next_month = (total % 12) + 1
    return f"{next_year:04d}-{next_month:02d}"


def _fetch_rows(
    conn,
    *,
    start: str,
    end: str,
    direction: str,
    account_id: str,
    account_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [start, end, direction]
    where = ["occurred_at >= ?", "occurred_at < ?", "direction = ?"]
    if account_ids:
        placeholders = ", ".join(["?"] * len(account_ids))
        where.append(f"account_id IN ({placeholders})")
        params.extend(account_ids)
    elif account_id != "all":
        where.append("account_id = ?")
        params.append(account_id)

    rows = conn.execute(
        f"""
        SELECT id, occurred_at, merchant, amount_yen, category_id, subcategory, account_id, updated_at
        FROM transactions
        WHERE {' AND '.join(where)}
        ORDER BY occurred_at ASC, id ASC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _category_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sums: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        key = str(row.get("category_id") or "uncategorized")
        sums[key] += int(row.get("amount_yen") or 0)
        counts[key] += 1
    result = [
        {"category_id": key, "total": total, "count": counts[key]}
        for key, total in sums.items()
    ]
    result.sort(key=lambda item: (-item["total"], item["category_id"]))
    return result


def _subcategory_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sums: dict[tuple[str, str], int] = defaultdict(int)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        category_id = str(row.get("category_id") or "uncategorized")
        subcategory = str(row.get("subcategory") or "未分類")
        key = (category_id, subcategory)
        sums[key] += int(row.get("amount_yen") or 0)
        counts[key] += 1
    result = [
        {
            "category_id": key[0],
            "subcategory": key[1],
            "total": total,
            "count": counts[key],
        }
        for key, total in sums.items()
    ]
    result.sort(key=lambda item: (-item["total"], item["category_id"], item["subcategory"]))
    return result


def _top_transactions(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -int(row.get("amount_yen") or 0),
            str(row.get("occurred_at") or ""),
            str(row.get("merchant") or ""),
        ),
    )
    return [
        {
            "id": int(row["id"]),
            "occurred_at": row["occurred_at"],
            "merchant": row["merchant"],
            "amount_yen": int(row["amount_yen"] or 0),
            "category_id": row["category_id"],
            "subcategory": row.get("subcategory") or "未分類",
            "account_id": row.get("account_id"),
        }
        for row in sorted_rows[:limit]
    ]


def _uncategorized_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    filtered = [
        row
        for row in rows
        if str(row.get("category_id") or "") == "uncategorized"
        or str(row.get("subcategory") or "") == "未分類"
    ]
    return {
        "count": len(filtered),
        "amount_yen": sum(int(row.get("amount_yen") or 0) for row in filtered),
    }


def _notable_spending(rows: list[dict[str, Any]], total: int) -> list[dict[str, Any]]:
    threshold = max(5000, int(total * 0.08))
    notable = [row for row in rows if int(row.get("amount_yen") or 0) >= threshold]
    return _top_transactions(notable, limit=8)


def _monthly_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sums: dict[str, int] = defaultdict(int)
    for row in rows:
        month = str(row.get("occurred_at") or "")[:7]
        if month:
            sums[month] += int(row.get("amount_yen") or 0)
    result = [{"month": month, "total": total} for month, total in sums.items()]
    result.sort(key=lambda item: item["month"])
    return result


def _surge_months(monthly: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(monthly) < 2:
        return []
    diffs: list[dict[str, Any]] = []
    for prev, curr in zip(monthly, monthly[1:]):
        diff = int(curr["total"]) - int(prev["total"])
        if diff > 0:
            diffs.append(
                {
                    "from": prev["month"],
                    "to": curr["month"],
                    "diff": diff,
                    "current_total": int(curr["total"]),
                }
            )
    diffs.sort(key=lambda item: (-item["diff"], item["to"]))
    return diffs[:4]


def _recurring_spending(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        merchant = str(row.get("merchant") or "").strip() or "(不明)"
        slot = stats.setdefault(merchant, {"merchant": merchant, "count": 0, "total": 0, "amounts": []})
        amount = int(row.get("amount_yen") or 0)
        slot["count"] += 1
        slot["total"] += amount
        slot["amounts"].append(amount)

    result: list[dict[str, Any]] = []
    for merchant, slot in stats.items():
        if int(slot["count"]) < 3:
            continue
        amounts = sorted(slot["amounts"])
        median = amounts[len(amounts) // 2]
        result.append(
            {
                "merchant": merchant,
                "count": int(slot["count"]),
                "total": int(slot["total"]),
                "median_amount": int(median),
            }
        )
    result.sort(key=lambda item: (-item["total"], -item["count"], item["merchant"]))
    return result[:8]


def _hash_transactions(
    rows: list[dict[str, Any]],
    *,
    period_type: str,
    period: str,
    account_id: str,
    direction: str,
) -> str:
    stable_rows = [
        {
            "id": int(row["id"]),
            "occurred_at": row.get("occurred_at"),
            "merchant": row.get("merchant"),
            "amount_yen": int(row.get("amount_yen") or 0),
            "category_id": row.get("category_id"),
            "subcategory": row.get("subcategory") or "未分類",
            "account_id": row.get("account_id"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]
    payload = {
        "period_type": period_type,
        "period": period,
        "account_id": account_id,
        "direction": direction,
        "transactions": stable_rows,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _split_analysis_rows(
    rows: list[dict[str, Any]],
    *,
    direction: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if direction != "expense":
        return rows, []
    normal_rows: list[dict[str, Any]] = []
    fund_movement_rows: list[dict[str, Any]] = []
    for row in rows:
        if is_fund_movement_category(str(row.get("category_id") or "")):
            fund_movement_rows.append(row)
        else:
            normal_rows.append(row)
    return normal_rows, fund_movement_rows


def _fund_movement_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "category_id": FUND_MOVEMENT_CATEGORY_ID,
        "count": len(rows),
        "amount_yen": sum(int(row.get("amount_yen") or 0) for row in rows),
        "top_transactions": _top_transactions(rows, limit=5),
    }


def build_analysis_input(
    conn,
    *,
    period_type: str,
    period: str,
    account_id: str,
    account_ids: list[str] | None = None,
    direction: str,
) -> tuple[dict[str, Any], str]:
    direction = normalize_direction(direction)
    start, end = _period_bounds(period_type, period)
    all_rows = _fetch_rows(
        conn,
        start=start,
        end=end,
        direction=direction,
        account_id=account_id,
        account_ids=account_ids,
    )
    rows, fund_movement_rows = _split_analysis_rows(all_rows, direction=direction)
    input_hash = _hash_transactions(
        rows,
        period_type=period_type,
        period=period,
        account_id=account_id,
        direction=direction,
    )

    total = sum(int(row.get("amount_yen") or 0) for row in rows)
    category_totals = _category_totals(rows)
    subcategory_totals = _subcategory_totals(rows)
    top_transactions = _top_transactions(rows)
    uncategorized = _uncategorized_stats(rows)

    payload: dict[str, Any] = {
        "period_type": period_type,
        "period": period,
        "account_id": account_id,
        "direction": direction,
        "all_transaction_count": len(all_rows),
        "transaction_count": len(rows),
    }
    if direction == "expense":
        payload["excluded_fund_movement"] = _fund_movement_summary(fund_movement_rows)

    if period_type == "month":
        prev_month = _shift_month(period, -1)
        prev_start, prev_end = month_bounds(prev_month)
        prev_all_rows = _fetch_rows(
            conn,
            start=prev_start,
            end=prev_end,
            direction=direction,
            account_id=account_id,
            account_ids=account_ids,
        )
        prev_rows, _ = _split_analysis_rows(prev_all_rows, direction=direction)
        prev_total = sum(int(row.get("amount_yen") or 0) for row in prev_rows)
        prev_by_category = {item["category_id"]: int(item["total"]) for item in _category_totals(prev_rows)}
        increased = []
        for item in category_totals:
            current_total = int(item["total"])
            diff = current_total - int(prev_by_category.get(item["category_id"], 0))
            if diff > 0:
                increased.append(
                    {
                        "category_id": item["category_id"],
                        "diff": diff,
                        "current_total": current_total,
                    }
                )
        increased.sort(key=lambda row: (-int(row["diff"]), row["category_id"]))

        payload.update(
            {
                "month": period,
                "expense_total": total,
                "category_totals": category_totals,
                "subcategory_totals": subcategory_totals,
                "top_transactions": top_transactions,
                "month_over_month": {
                    "previous_month": prev_month,
                    "previous_total": prev_total,
                    "diff": total - prev_total,
                },
                "increased_categories": increased[:6],
                "uncategorized": uncategorized,
                "notable_spending": _notable_spending(rows, total),
            }
        )
    else:
        monthly = _monthly_totals(rows)
        payload.update(
            {
                "year": period,
                "annual_total": total,
                "monthly_totals": monthly,
                "category_totals": category_totals,
                "top_transactions": top_transactions,
                "uncategorized": uncategorized,
                "high_spending_months": sorted(monthly, key=lambda row: (-int(row["total"]), row["month"]))[:3],
                "surge_months": _surge_months(monthly),
                "fixed_cost_like_spending": _recurring_spending(rows),
                "review_candidates": _notable_spending(rows, total),
            }
        )

    return payload, input_hash


def find_latest_analysis(
    conn,
    *,
    period_type: str,
    period: str,
    account_id: str,
    direction: str,
    input_hash: str,
    analyzer: str,
    analyzer_version: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM analysis_runs
        WHERE period_type = ?
          AND period = ?
          AND account_id = ?
          AND direction = ?
          AND input_hash = ?
          AND analyzer = ?
          AND analyzer_version = ?
          AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (period_type, period, account_id, direction, input_hash, analyzer, analyzer_version),
    ).fetchone()
    return dict(row) if row else None


def find_latest_analysis_by_scope(
    conn,
    *,
    period_type: str,
    period: str,
    account_id: str,
    direction: str,
    analyzer: str,
    analyzer_version: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM analysis_runs
        WHERE period_type = ?
          AND period = ?
          AND account_id = ?
          AND direction = ?
          AND analyzer = ?
          AND analyzer_version = ?
          AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (period_type, period, account_id, direction, analyzer, analyzer_version),
    ).fetchone()
    return dict(row) if row else None


def save_analysis_run(
    conn,
    *,
    period_type: str,
    period: str,
    account_id: str,
    direction: str,
    input_hash: str,
    analyzer: str,
    analyzer_version: str,
    status: str,
    result_text: str | None,
    result_json: dict[str, Any] | None,
    error_message: str | None,
) -> dict[str, Any]:
    now = utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO analysis_runs(
            period_type, period, account_id, direction, input_hash,
            analyzer, analyzer_version, status, result_text, result_json,
            error_message, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            period_type,
            period,
            account_id,
            direction,
            input_hash,
            analyzer,
            analyzer_version,
            status,
            result_text,
            json.dumps(result_json, ensure_ascii=False) if result_json else None,
            error_message,
            now,
            now,
        ),
    )
    row_id = int(cur.lastrowid)
    row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        raise AnalysisError("analysis run could not be loaded")
    return dict(row)


def build_codex_prompt(payload: dict[str, Any]) -> str:
    period_type = payload.get("period_type")
    if period_type == "month":
        target = f"{payload.get('month')} の月次支出分析"
    else:
        target = f"{payload.get('year')} の年間支出分析"

    guide = {
        "output_requirements": [
            "日本語で回答する",
            "全体を750字以内でまとめる",
            "見出しは次の4つだけをこの順で使う: 1. 今月の結論, 2. 見るべき支出, 3. 次にやること, 4. 今月は気にしなくていいこと",
            "同じ金額・同じカテゴリ説明を繰り返さない",
            "カテゴリ別集計の説明や前月比・割合の細かい説明を多用しない",
            "一般論を書かず、判断と次の行動に集中する",
            "今月の結論は1〜2文にする",
            "見るべき支出は最大3件。金額順ではなく、判断に効くものを選ぶ",
            "次にやることは最大3個。家計簿上で実際に行う作業にする",
            "今月は気にしなくていいことは1〜2個。単発要因を過剰に問題扱いしない",
            "家計簿を見守るキャラクターとして、やさしく背中を押す口調にする",
            "断定しすぎず、安心感がありつつ実務的な提案にする",
            "支出分析では資金移動カテゴリを主支出に混ぜない",
            "追加質問で終わらない",
            "個人情報の推測や断定をしない",
        ]
    }

    return (
        "あなたは家計簿を見守るアシスタントキャラクターです。"
        "次の集計データだけを使い、短く読みやすく、でも中身のあるコメントを作ってください。\n"
        f"対象: {target}\n"
        "出力形式: プレーンテキスト\n\n"
        f"分析ガイド:\n{json.dumps(guide, ensure_ascii=False, indent=2)}\n\n"
        f"集計データ:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def run_or_reuse_analysis(
    conn,
    *,
    config: dict[str, Any],
    period_type: str,
    period: str,
    account_id: str,
    account_ids: list[str] | None = None,
    direction: str,
    force: bool,
) -> dict[str, Any]:
    direction = normalize_direction(direction)
    analysis_cfg = config.get("analysis") or {}
    enabled = bool(analysis_cfg.get("enabled", True))
    analyzer = str(analysis_cfg.get("analyzer") or "codex-app-server")
    analyzer_version = str(analysis_cfg.get("analyzer_version") or "v1")
    timeout_seconds = int(analysis_cfg.get("timeout_seconds") or 120)
    server_url = str(analysis_cfg.get("codex_app_server_url") or "ws://127.0.0.1:8787")

    if not enabled:
        raise AnalysisError("分析機能は設定で無効化されています")

    payload, input_hash = build_analysis_input(
        conn,
        period_type=period_type,
        period=period,
        account_id=account_id,
        account_ids=account_ids,
        direction=direction,
    )

    if not force:
        reused = find_latest_analysis(
            conn,
            period_type=period_type,
            period=period,
            account_id=account_id,
            direction=direction,
            input_hash=input_hash,
            analyzer=analyzer,
            analyzer_version=analyzer_version,
        )
        if reused:
            reused["reused"] = True
            reused["has_analysis"] = True
            reused["stale"] = False
            return reused

    prompt = build_codex_prompt(payload)

    client = CodexAppServerClient(
        url=server_url,
        timeout_seconds=timeout_seconds,
        client_name="local-finance-dashboard",
        client_version=analyzer_version,
    )
    try:
        turn = client.run_text_turn(prompt)
        row = save_analysis_run(
            conn,
            period_type=period_type,
            period=period,
            account_id=account_id,
            direction=direction,
            input_hash=input_hash,
            analyzer=analyzer,
            analyzer_version=analyzer_version,
            status="success",
            result_text=turn.result_text,
            result_json=None,
            error_message=None,
        )
        row["reused"] = False
        row["has_analysis"] = True
        row["stale"] = False
        return row
    except CodexAppServerError as exc:
        error_code = getattr(exc, "error_code", "codex_app_server_error")
        error_stage = getattr(exc, "stage", None)
        log_message = (
            "[analysis] Codex App Server error: "
            f"code={error_code} stage={error_stage} message={exc}"
        )
        print(_console_safe_text(log_message))
        row = save_analysis_run(
            conn,
            period_type=period_type,
            period=period,
            account_id=account_id,
            direction=direction,
            input_hash=input_hash,
            analyzer=analyzer,
            analyzer_version=analyzer_version,
            status="failed",
            result_text=None,
            result_json=None,
            error_message=str(exc),
        )
        row["status"] = "failed"
        row["reused"] = False
        row["has_analysis"] = False
        row["stale"] = False
        row["error_code"] = error_code
        row["error_stage"] = error_stage
        return row


def get_analysis_if_exists(
    conn,
    *,
    config: dict[str, Any],
    period_type: str,
    period: str,
    account_id: str,
    account_ids: list[str] | None = None,
    direction: str,
) -> dict[str, Any]:
    direction = normalize_direction(direction)
    analysis_cfg = config.get("analysis") or {}
    analyzer = str(analysis_cfg.get("analyzer") or "codex-app-server")
    analyzer_version = str(analysis_cfg.get("analyzer_version") or "v1")

    _, input_hash = build_analysis_input(
        conn,
        period_type=period_type,
        period=period,
        account_id=account_id,
        account_ids=account_ids,
        direction=direction,
    )
    existing = find_latest_analysis(
        conn,
        period_type=period_type,
        period=period,
        account_id=account_id,
        direction=direction,
        input_hash=input_hash,
        analyzer=analyzer,
        analyzer_version=analyzer_version,
    )
    if not existing:
        stale = find_latest_analysis_by_scope(
            conn,
            period_type=period_type,
            period=period,
            account_id=account_id,
            direction=direction,
            analyzer=analyzer,
            analyzer_version=analyzer_version,
        )
        if not stale:
            return {
                "has_analysis": False,
                "period_type": period_type,
                "period": period,
                "account_id": account_id,
                "direction": direction,
                "input_hash": input_hash,
                "analyzer": analyzer,
                "analyzer_version": analyzer_version,
                "stale": False,
            }
        stale_input_hash = stale.get("input_hash")
        stale["has_analysis"] = True
        stale["stale"] = True
        stale["input_hash"] = input_hash
        stale["matched_input_hash"] = stale_input_hash
        return stale

    existing["has_analysis"] = True
    existing["stale"] = False
    existing["input_hash"] = input_hash
    return existing
