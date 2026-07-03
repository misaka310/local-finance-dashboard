from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .categorizer import categorize
from .db import db, ensure_account, init_db, upsert_transaction, utc_now_iso

SOURCE_ID = "paypay-card-csv"
ACCOUNT_ID = "paypay-card"
ACCOUNT_NAME = "PayPayカード"


DATE_COLUMNS = [
    "利用日/キャンセル日",
    "利用日",
    "日付",
]
CANCEL_DATE_COLUMNS = [
    "キャンセル日",
]
MERCHANT_COLUMNS = [
    "利用店名・商品名",
    "利用店名",
    "加盟店",
    "店名",
    "商品名",
]
AMOUNT_COLUMNS = [
    "利用金額",
    "金額",
    "支払総額",
    "当月支払金額",
]
ADJUSTMENT_COLUMNS = [
    "調整額",
]
NOTE_COLUMNS = [
    "摘要",
    "備考",
    "利用内容",
    "明細区分",
]
REFUND_KEYWORDS = ["キャンセル", "返金", "返品", "取消", "取り消し", "調整", "reversal", "refund"]


class CsvImportError(Exception):
    pass


@dataclass
class CsvTransaction:
    external_id: str
    occurred_at: str
    merchant: str
    amount_yen: int
    direction: str
    raw_description: str


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "cp932", "shift_jis", "utf-8"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise CsvImportError(f"CSV encoding is unsupported: {path}")


def sniff_dialect(text: str) -> csv.Dialect:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        class Fallback(csv.excel):
            delimiter = "\t" if "\t" in sample else ","
        return Fallback


def normalize_header(name: str) -> str:
    return (name or "").strip().replace("\ufeff", "")


def normalize_key(name: str) -> str:
    value = normalize_header(name).replace(" ", "").replace("　", "")
    return value.replace("/", "").replace("・", "").replace("_", "").lower()


def normalize_merchant(value: str) -> str:
    value = (value or "").strip().replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value)
    return value[:120] or "PayPayカード利用"


def parse_date(value: str) -> str:
    value = (value or "").strip()
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", value)
    if not m:
        raise CsvImportError(f"Could not parse date: {value}")
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def normalize_amount_text(value: str) -> str:
    value = (value or "").strip()
    value = value.translate(str.maketrans("０１２３４５６７８９，", "0123456789,"))
    value = value.replace("ー", "-").replace("−", "-").replace("―", "-").replace("－", "-")
    value = value.replace(",", "").replace("円", "")
    value = value.replace("△", "-").replace("▲", "-").replace("−", "-")
    return re.sub(r"[^0-9\-]", "", value)


def parse_amount(value: str) -> int:
    normalized = normalize_amount_text(value)
    if normalized in {"", "-"}:
        raise CsvImportError("Could not parse amount")
    return int(normalized)


def pick(row: dict[str, str], candidates: list[str]) -> str:
    for c in candidates:
        key = normalize_key(c)
        if key in row and row[key].strip():
            return row[key].strip()
    return ""


def stable_external_id(row: dict[str, str]) -> str:
    parts = [f"{k}={row.get(k, '')}" for k in sorted(row)]
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:32]


def is_refund_or_cancel(row: dict[str, str], amount: int) -> bool:
    if amount < 0:
        return True
    joined = " ".join(str(v) for v in row.values()).lower()
    if any(keyword.lower() in joined for keyword in REFUND_KEYWORDS):
        return True
    for col in ADJUSTMENT_COLUMNS + ["支払総額", "当月支払金額"]:
        value = pick(row, [col])
        if not value:
            continue
        try:
            if parse_amount(value) < 0:
                return True
        except CsvImportError:
            continue
    return False


def row_to_transaction(row: dict[str, str]) -> CsvTransaction:
    amount_raw = pick(row, AMOUNT_COLUMNS)
    amount = parse_amount(amount_raw)
    refund = is_refund_or_cancel(row, amount)

    if refund:
        date_value = pick(row, CANCEL_DATE_COLUMNS) or pick(row, DATE_COLUMNS)
        direction = "income"
    else:
        date_value = pick(row, DATE_COLUMNS)
        direction = "expense"
    occurred_at = parse_date(date_value)

    merchant = normalize_merchant(pick(row, MERCHANT_COLUMNS))
    amount_abs = abs(amount)
    if amount_abs <= 0:
        raise CsvImportError("amount must be greater than zero")

    note = pick(row, NOTE_COLUMNS)
    raw_description = " / ".join(part for part in [merchant, note] if part)

    return CsvTransaction(
        external_id=stable_external_id(row),
        occurred_at=occurred_at,
        merchant=merchant,
        amount_yen=amount_abs,
        direction=direction,
        raw_description=raw_description,
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    text = read_text(path)
    dialect = sniff_dialect(text)
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    if not reader.fieldnames:
        raise CsvImportError(f"Could not parse header row: {path}")
    original_headers = [normalize_header(x) for x in reader.fieldnames]
    normalized_headers = [normalize_key(x) for x in original_headers]

    rows: list[dict[str, str]] = []
    for row in reader:
        normalized: dict[str, str] = {}
        for original, normalized_key in zip(original_headers, normalized_headers):
            normalized[normalized_key] = (row.get(original) or "").strip()
        rows.append(normalized)
    return rows


def natural_duplicate_exists(conn, tx: CsvTransaction) -> bool:
    merchant_norm = re.sub(r"\s+", "", tx.merchant).lower()
    rows = conn.execute(
        """
        SELECT merchant FROM transactions
        WHERE account_id = ? AND occurred_at = ? AND amount_yen = ? AND direction = ?
        """,
        (ACCOUNT_ID, tx.occurred_at, tx.amount_yen, tx.direction),
    ).fetchall()
    for row in rows:
        existing = re.sub(r"\s+", "", row["merchant"] or "").lower()
        if existing == merchant_norm or merchant_norm in existing or existing in merchant_norm:
            return True
    return False


def expand_paths(inputs: Iterable[str]) -> list[Path]:
    result: list[Path] = []
    for item in inputs:
        matches = glob.glob(item)
        if matches:
            for match in matches:
                p = Path(match)
                if p.is_dir():
                    result.extend(sorted(p.glob("*.csv")))
                else:
                    result.append(p)
            continue
        p = Path(item)
        if p.is_dir():
            result.extend(sorted(p.glob("*.csv")))
        else:
            result.append(p)

    seen = set()
    unique: list[Path] = []
    for p in result:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def import_files(paths: list[Path]) -> dict[str, int]:
    if not paths:
        raise CsvImportError("No CSV files were specified")

    totals = {"files": 0, "fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    with db() as conn:
        init_db(conn)
        ensure_account(conn, ACCOUNT_ID, ACCOUNT_NAME)
        cur = conn.execute(
            "INSERT INTO import_runs(source_id, started_at, status, message) VALUES (?, ?, 'running', ?)",
            (SOURCE_ID, utc_now_iso(), ", ".join(str(p) for p in paths)),
        )
        run_id = int(cur.lastrowid)

    try:
        for path in paths:
            totals["files"] += 1
            if not path.exists():
                totals["errors"] += 1
                with db() as conn:
                    conn.execute(
                        "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, SOURCE_ID, str(path), path.name, "CSV file not found", utc_now_iso()),
                    )
                continue
            try:
                rows = read_rows(path)
            except Exception as exc:
                totals["errors"] += 1
                with db() as conn:
                    conn.execute(
                        "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, SOURCE_ID, str(path), path.name, str(exc), utc_now_iso()),
                    )
                continue

            for i, row in enumerate(rows, start=2):
                totals["fetched"] += 1
                try:
                    tx = row_to_transaction(row)
                    with db() as conn:
                        if natural_duplicate_exists(conn, tx):
                            totals["skipped"] += 1
                            continue
                        category_id, subcategory = categorize(conn, tx.merchant, tx.raw_description, source_id=SOURCE_ID)
                        result = upsert_transaction(
                            conn,
                            {
                                "source_id": SOURCE_ID,
                                "account_id": ACCOUNT_ID,
                                "external_id": tx.external_id,
                                "thread_id": None,
                                "direction": tx.direction,
                                "occurred_at": tx.occurred_at,
                                "posted_at": None,
                                "merchant": tx.merchant,
                                "raw_description": tx.raw_description,
                                "amount_yen": tx.amount_yen,
                                "category_id": category_id,
                                "subcategory": subcategory,
                            },
                        )
                    totals[result] += 1
                except Exception as exc:
                    totals["errors"] += 1
                    with db() as conn:
                        conn.execute(
                            "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (run_id, SOURCE_ID, f"{path}:{i}", path.name, str(exc), utc_now_iso()),
                        )
        with db() as conn:
            conn.execute(
                """
                UPDATE import_runs
                SET finished_at = ?, status = 'success', fetched_count = ?, inserted_count = ?, updated_count = ?,
                    skipped_count = ?, error_count = ?
                WHERE id = ?
                """,
                (utc_now_iso(), totals["fetched"], totals["inserted"], totals["updated"], totals["skipped"], totals["errors"], run_id),
            )
        return totals
    except Exception:
        with db() as conn:
            conn.execute(
                "UPDATE import_runs SET finished_at = ?, status = 'failed', error_count = ?, message = ? WHERE id = ?",
                (utc_now_iso(), totals["errors"] + 1, traceback.format_exc(), run_id),
            )
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import PayPay Card CSV files into the local budget database.")
    parser.add_argument("paths", nargs="+", help="CSV file path, directory, or wildcard, e.g. %USERPROFILE%\\Downloads\\detail*.csv")
    args = parser.parse_args(argv)
    paths = expand_paths(args.paths)
    result = import_files(paths)
    print("PayPay CSV import completed.")
    print(
        f"files: {result['files']} / rows: {result['fetched']} / inserted: {result['inserted']} / "
        f"updated: {result['updated']} / skipped: {result['skipped']} / errors: {result['errors']}"
    )
    if result["errors"]:
        print("Some rows failed. Check the import_errors table in data/mfblue.sqlite3.")
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
