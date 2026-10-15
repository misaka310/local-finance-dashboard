from __future__ import annotations

import argparse
import csv
import glob
import re
import shutil
import traceback
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .categorizer import categorize
from .db import DEFAULT_SUBCATEGORY, connect, ensure_account, init_db, utc_now_iso

SOURCE_ID = "amazon-order-history"
ACCOUNT_ID = "amazon-order-history"
ACCOUNT_NAME = "Amazon注文履歴"
DEFAULT_GLOB = "data/imports/amazon/*.csv"
DEFAULT_IMPORTED_DIR = "data/imports/amazon/imported"
DEFAULT_MERCHANT = "Amazon.co.jp"


class CsvImportError(Exception):
    pass


class RowSkip(Exception):
    pass


@dataclass
class CsvTransaction:
    source_id: str
    account_id: str
    external_id: str
    occurred_at: str
    merchant: str
    raw_description: str
    amount_yen: int
    direction: str
    category_id: str
    subcategory: str


COLUMN_ALIASES = {
    "source_id": ["source_id", "source", "source id", "source-id", "sourceid"],
    "account_id": ["account_id", "account", "account id", "account-id", "accountid"],
    "external_id": [
        "external_id",
        "external id",
        "external-id",
        "externalid",
        "order_id",
        "order id",
        "order-id",
        "orderid",
        "amazon_order_id",
        "amazon_order_number",
        "amazon_order_no",
        "amazon_order",
        "order_number",
    ],
    "occurred_at": [
        "occurred_at",
        "occurred at",
        "occurred-at",
        "occurredat",
        "date",
        "order_date",
        "order date",
        "transaction_date",
    ],
    "merchant": ["merchant", "shop", "store", "seller", "merchant_name"],
    "raw_description": [
        "raw_description",
        "raw description",
        "raw-description",
        "description",
        "memo",
        "note",
        "details",
    ],
    "amount_yen": [
        "amount_yen",
        "amount yen",
        "amount-yen",
        "amountyen",
        "amount",
        "total",
        "total_amount",
        "price",
        "payment_amount",
    ],
    "direction": ["direction", "type", "transaction_type", "income_expense"],
    "category_id": [
        "category_id",
        "category id",
        "category-id",
        "categoryid",
        "category",
    ],
    "subcategory": [
        "subcategory",
        "sub_category",
        "sub-category",
        "subcategory_name",
        "sub category",
        "middle_category",
    ],
}


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
    return unicodedata.normalize("NFKC", (name or "").strip().replace("\ufeff", ""))


def normalize_key(name: str) -> str:
    normalized = normalize_header(name).lower()
    return "".join(ch for ch in normalized if ch.isalnum())


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", (value or "").strip())


def pick(row: dict[str, str], key: str) -> str:
    for alias in COLUMN_ALIASES.get(key, [key]):
        value = row.get(normalize_key(alias), "")
        if value.strip():
            return normalize_text(value)
    return ""


def parse_date(value: str) -> str:
    text = normalize_text(value)
    m = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if not m:
        raise CsvImportError(f"could not parse occurred_at: {value}")
    y, mon, day = m.groups()
    return f"{int(y):04d}-{int(mon):02d}-{int(day):02d}"


def parse_amount(value: str) -> int:
    text = normalize_text(value).replace(",", "")
    text = text.replace("円", "").replace("¥", "").replace("￥", "")
    text = text.strip()
    if not text:
        raise CsvImportError("amount_yen is missing")
    try:
        amount = int(float(text))
    except ValueError as exc:
        raise CsvImportError(f"could not parse amount_yen: {value}") from exc
    if amount <= 0:
        raise RowSkip("amount_yen must be greater than zero")
    return amount


def parse_direction(value: str) -> str:
    text = normalize_text(value).lower()
    if not text:
        return "expense"
    if text in {"expense", "spend", "debit", "支出"}:
        return "expense"
    if text in {"income", "credit", "refund", "収入"}:
        return "income"
    raise CsvImportError(f"invalid direction: {value}")


def read_rows(path: Path) -> list[dict[str, str]]:
    text = read_text(path)
    reader = csv.DictReader(text.splitlines(), dialect=sniff_dialect(text))
    if not reader.fieldnames:
        raise CsvImportError(f"could not parse header row: {path}")

    header_keys = [normalize_key(name) for name in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        normalized: dict[str, str] = {}
        for original, key in zip(reader.fieldnames, header_keys):
            normalized[key] = (raw_row.get(original) or "").strip()
        rows.append(normalized)
    return rows


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

    unique: list[Path] = []
    seen: set[str] = set()
    for path in result:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def resolve_category(
    conn,
    row: dict[str, str],
    merchant: str,
    raw_description: str,
    *,
    persist_subcategory: bool,
) -> tuple[str, str]:
    csv_category = pick(row, "category_id")
    csv_subcategory = pick(row, "subcategory")

    fallback_category = ""
    fallback_subcategory = ""
    if not csv_category or not csv_subcategory:
        fallback_category, fallback_subcategory = categorize(
            conn,
            merchant,
            raw_description,
            source_id=SOURCE_ID,
        )

    category_id = csv_category or fallback_category
    if not category_id:
        raise CsvImportError("category_id could not be resolved")

    category = conn.execute("SELECT id FROM categories WHERE id = ?", (category_id,)).fetchone()
    if category is None:
        raise CsvImportError(f"category_id does not exist: {category_id}")

    subcategory = csv_subcategory or fallback_subcategory or DEFAULT_SUBCATEGORY
    if persist_subcategory:
        conn.execute(
            "INSERT OR IGNORE INTO subcategories(category_id, name, sort_order) VALUES (?, ?, 999)",
            (category_id, subcategory),
        )
    return category_id, subcategory


def row_to_transaction(conn, row: dict[str, str], *, persist_subcategory: bool) -> CsvTransaction:
    csv_source_id = pick(row, "source_id")
    if csv_source_id and csv_source_id != SOURCE_ID:
        raise CsvImportError(f"source_id must be {SOURCE_ID}: {csv_source_id}")
    csv_account_id = pick(row, "account_id")
    if csv_account_id and csv_account_id != ACCOUNT_ID:
        raise CsvImportError(f"account_id must be {ACCOUNT_ID}: {csv_account_id}")

    source_id = SOURCE_ID
    account_id = ACCOUNT_ID
    external_id = pick(row, "external_id")
    if not external_id:
        raise CsvImportError("external_id is required")

    occurred_at = parse_date(pick(row, "occurred_at"))
    merchant = pick(row, "merchant") or DEFAULT_MERCHANT
    raw_description = pick(row, "raw_description") or external_id
    amount_yen = parse_amount(pick(row, "amount_yen"))
    direction = parse_direction(pick(row, "direction"))
    category_id, subcategory = resolve_category(
        conn,
        row,
        merchant,
        raw_description,
        persist_subcategory=persist_subcategory,
    )

    return CsvTransaction(
        source_id=source_id,
        account_id=account_id,
        external_id=external_id,
        occurred_at=occurred_at,
        merchant=merchant,
        raw_description=raw_description,
        amount_yen=amount_yen,
        direction=direction,
        category_id=category_id,
        subcategory=subcategory,
    )


def upsert_amazon_transaction(conn, tx: CsvTransaction) -> str:
    now = utc_now_iso()
    exists = conn.execute(
        "SELECT id FROM transactions WHERE source_id = ? AND external_id = ?",
        (tx.source_id, tx.external_id),
    ).fetchone()
    if exists:
        conn.execute(
            """
            UPDATE transactions
            SET account_id = ?, thread_id = NULL, direction = ?, occurred_at = ?, posted_at = NULL,
                merchant = ?, raw_description = ?, amount_yen = ?, category_id = ?, subcategory = ?, updated_at = ?
            WHERE source_id = ? AND external_id = ?
            """,
            (
                tx.account_id,
                tx.direction,
                tx.occurred_at,
                tx.merchant,
                tx.raw_description,
                tx.amount_yen,
                tx.category_id,
                tx.subcategory,
                now,
                tx.source_id,
                tx.external_id,
            ),
        )
        return "updated"

    conn.execute(
        """
        INSERT INTO transactions(
            source_id, account_id, external_id, thread_id, direction, occurred_at, posted_at,
            merchant, raw_description, amount_yen, category_id, subcategory, note, imported_at, updated_at
        ) VALUES (?, ?, ?, NULL, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            tx.source_id,
            tx.account_id,
            tx.external_id,
            tx.direction,
            tx.occurred_at,
            tx.merchant,
            tx.raw_description,
            tx.amount_yen,
            tx.category_id,
            tx.subcategory,
            now,
            now,
        ),
    )
    return "inserted"


def estimate_upsert_result(conn, tx: CsvTransaction) -> str:
    exists = conn.execute(
        "SELECT 1 FROM transactions WHERE source_id = ? AND external_id = ?",
        (tx.source_id, tx.external_id),
    ).fetchone()
    return "updated" if exists else "inserted"


def record_import_error(conn, run_id: int, external_id: str | None, subject: str, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, SOURCE_ID, external_id, subject, reason, utc_now_iso()),
    )


def import_files(
    paths: list[Path],
    db_path: Path | None = None,
    *,
    dry_run: bool = False,
    move_imported_to: Path | None = None,
) -> dict[str, int]:
    if not paths:
        raise CsvImportError("No CSV files were specified")

    totals = {"files": 0, "rows": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0, "moved_files": 0}
    conn = connect(db_path)
    run_id = 0
    successful_files: list[Path] = []
    try:
        init_db(conn)
        ensure_account(conn, ACCOUNT_ID, ACCOUNT_NAME)
        if not dry_run:
            cur = conn.execute(
                "INSERT INTO import_runs(source_id, started_at, status, message) VALUES (?, ?, 'running', ?)",
                (SOURCE_ID, utc_now_iso(), ", ".join(str(p) for p in paths)),
            )
            run_id = int(cur.lastrowid)
            conn.commit()

        for path in paths:
            totals["files"] += 1
            file_errors = 0
            if not path.exists():
                totals["errors"] += 1
                file_errors += 1
                if not dry_run:
                    record_import_error(conn, run_id, str(path), path.name, "CSV file not found")
                continue

            try:
                rows = read_rows(path)
            except Exception as exc:
                totals["errors"] += 1
                file_errors += 1
                if not dry_run:
                    record_import_error(conn, run_id, str(path), path.name, str(exc))
                continue

            for i, row in enumerate(rows, start=2):
                totals["rows"] += 1
                try:
                    tx = row_to_transaction(conn, row, persist_subcategory=not dry_run)
                    if dry_run:
                        result = estimate_upsert_result(conn, tx)
                    else:
                        result = upsert_amazon_transaction(conn, tx)
                    totals[result] += 1
                except RowSkip:
                    totals["skipped"] += 1
                except Exception as exc:
                    totals["errors"] += 1
                    file_errors += 1
                    if not dry_run:
                        record_import_error(
                            conn,
                            run_id,
                            row.get(normalize_key("external_id")) or f"{path}:{i}",
                            path.name,
                            str(exc),
                        )

            if file_errors == 0:
                successful_files.append(path)

        if dry_run:
            conn.rollback()
            return totals

        conn.execute(
            """
            UPDATE import_runs
            SET finished_at = ?, status = 'success', fetched_count = ?, inserted_count = ?, updated_count = ?,
                skipped_count = ?, error_count = ?
            WHERE id = ?
            """,
            (
                utc_now_iso(),
                totals["rows"],
                totals["inserted"],
                totals["updated"],
                totals["skipped"],
                totals["errors"],
                run_id,
            ),
        )

        if move_imported_to:
            move_imported_to.mkdir(parents=True, exist_ok=True)
            for src in successful_files:
                if not src.exists():
                    continue
                dst = move_imported_to / src.name
                if dst.exists():
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dst = move_imported_to / f"{src.stem}_{stamp}{src.suffix}"
                shutil.move(str(src), str(dst))
                totals["moved_files"] += 1

        conn.commit()
        return totals
    except Exception:
        if run_id:
            conn.execute(
                "UPDATE import_runs SET finished_at = ?, status = 'failed', error_count = ?, message = ? WHERE id = ?",
                (utc_now_iso(), totals["errors"] + 1, traceback.format_exc(), run_id),
            )
            conn.commit()
        raise
    finally:
        conn.close()


def print_target_files(paths: list[Path], *, used_default_glob: bool) -> None:
    print("今回取り込むCSV:")
    if not paths:
        print("  (対象なし)")
        return

    stale_threshold = datetime.now() - timedelta(days=45)
    stale_files: list[Path] = []
    for path in paths:
        if not path.exists():
            print(f"  - {path} (missing)")
            continue
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        if mtime < stale_threshold:
            stale_files.append(path)
        print(f"  - {path} ({mtime:%Y-%m-%d %H:%M}, {stat.st_size} bytes)")

    if used_default_glob:
        print("注意: 引数未指定のため data/imports/amazon/*.csv を対象にしました。古いCSV混入防止のため明示指定を推奨します。")
    if stale_files:
        print("注意: 更新日時が古いCSVが含まれています。意図しない再取り込みに注意してください。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Amazon order history CSV files into the local budget database.")
    parser.add_argument("paths", nargs="*", help="CSV file path, directory, or wildcard")
    parser.add_argument("--dry-run", action="store_true", help="DBには書き込まず、取り込み見込みだけ表示する")
    parser.add_argument(
        "--move-imported",
        nargs="?",
        const=DEFAULT_IMPORTED_DIR,
        default=None,
        help="成功したCSVを指定ディレクトリへ移動する (default: data/imports/amazon/imported)",
    )
    args = parser.parse_args(argv)

    used_default_glob = not args.paths
    paths = expand_paths(args.paths or [DEFAULT_GLOB])
    print_target_files(paths, used_default_glob=used_default_glob)

    if not paths:
        print("CSVが見つかりませんでした。")
        return 1

    move_to = Path(args.move_imported) if args.move_imported else None
    result = import_files(paths, dry_run=args.dry_run, move_imported_to=move_to)

    if args.dry_run:
        print("Amazon CSV dry-run completed. (DB更新なし)")
    else:
        print("Amazon CSV import completed.")
    print(
        f"files: {result['files']} / rows: {result['rows']} / inserted: {result['inserted']} / "
        f"updated: {result['updated']} / skipped: {result['skipped']} / errors: {result['errors']}"
    )
    if result.get("moved_files", 0):
        print(f"moved_files: {result['moved_files']}")
    if result["errors"]:
        print("Some rows failed. Check the import_errors table in data/mfblue.sqlite3.")
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
