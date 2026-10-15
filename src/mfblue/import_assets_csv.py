from __future__ import annotations

import argparse
import csv
import glob
import re
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from .asset_fund_names import normalize_asset_fund_name
from .db import (
    connect,
    ensure_asset_product,
    init_db,
    period_month_from_date,
    upsert_asset_snapshot,
    utc_now_iso,
)
from .paths import project_path

SOURCE_ID = "sbi-assets-csv"
DEFAULT_INSTITUTION = "SBI証券"
DEFAULT_ACCOUNT_TYPE = "新NISA"

NAME_COLUMNS = ["ファンド名", "銘柄名", "商品名", "名称"]
QUANTITY_COLUMNS = ["保有口数", "数量", "口数"]
BASE_PRICE_COLUMNS = ["基準価額", "基準価格", "現在値"]
ACQUISITION_PRICE_COLUMNS = ["取得単価", "平均取得単価", "買付単価"]
CURRENT_VALUE_COLUMNS = ["評価額", "時価評価額", "現在評価額"]
INVESTED_AMOUNT_COLUMNS = ["取得金額", "買付金額", "投資金額"]
PROFIT_LOSS_COLUMNS = ["評価損益", "損益"]
PROFIT_LOSS_RATE_COLUMNS = ["評価損益率", "損益率"]
DAILY_CHANGE_YEN_COLUMNS = ["評価損益 前日比", "評価損益前日比", "前日比金額"]
DAILY_CHANGE_RATE_COLUMNS = ["前日比率", "評価損益 前日比率", "評価損益前日比率", "前日比%"]
DIVIDEND_METHOD_COLUMNS = ["分配金受取方法", "分配金受取"]
VALUATION_DATE_COLUMNS = ["評価日", "基準日", "日付"]


class CsvImportError(Exception):
    pass


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


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u3000", " ").strip())


def pick(row: dict[str, str], columns: list[str]) -> str:
    for col in columns:
        key = normalize_key(col)
        if key in row:
            raw = str(row[key] or "").strip()
            if raw:
                return raw
    return ""


_FULL_WIDTH_TRANS = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "，": ",",
        "．": ".",
        "％": "%",
        "＋": "+",
        "－": "-",
        "ー": "-",
        "―": "-",
        "−": "-",
        "△": "-",
        "▲": "-",
    }
)


def parse_number(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.translate(_FULL_WIDTH_TRANS)
    normalized = normalized.replace("円", "").replace("口", "").replace(",", "")
    normalized = normalized.replace("%", "").replace("＋", "+")
    normalized = normalized.replace("▲", "-").replace("△", "-")
    normalized = re.sub(r"[^\d\.\-\+]", "", normalized)
    if normalized in {"", "+", "-", ".", "+.", "-."}:
        return None
    return float(normalized)


def parse_int(value: str) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(round(number))


def parse_date(value: str) -> str:
    text = normalize_text(value)
    m = re.search(r"(20\d{2})[\/\-.年](\d{1,2})[\/\-.月](\d{1,2})", text)
    if not m:
        raise CsvImportError(f"Could not parse date: {value}")
    year, month, day = [int(x) for x in m.groups()]
    return f"{year:04d}-{month:02d}-{day:02d}"


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


@contextmanager
def _db_ctx(path: Path | None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def import_files(
    paths: list[Path],
    *,
    db_path: Path | None = None,
    valuation_date: str | None = None,
    institution: str = DEFAULT_INSTITUTION,
    account_type: str = DEFAULT_ACCOUNT_TYPE,
    asset_type: str = "investment_trust",
) -> dict[str, int]:
    if not paths:
        raise CsvImportError("No CSV files were specified")
    fallback_date = parse_date(valuation_date) if valuation_date else None
    totals = {
        "files": 0,
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "products_inserted": 0,
        "products_updated": 0,
    }
    with _db_ctx(db_path) as conn:
        init_db(conn)
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
                with _db_ctx(db_path) as conn:
                    conn.execute(
                        "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, SOURCE_ID, str(path), path.name, "CSV file not found", utc_now_iso()),
                    )
                continue
            try:
                rows = read_rows(path)
            except Exception as exc:
                totals["errors"] += 1
                with _db_ctx(db_path) as conn:
                    conn.execute(
                        "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, SOURCE_ID, str(path), path.name, str(exc), utc_now_iso()),
                    )
                continue

            for i, row in enumerate(rows, start=2):
                totals["fetched"] += 1
                try:
                    name = normalize_text(pick(row, NAME_COLUMNS))
                    if not name:
                        totals["skipped"] += 1
                        continue
                    if not normalize_asset_fund_name(name):
                        totals["skipped"] += 1
                        continue
                    date_raw = pick(row, VALUATION_DATE_COLUMNS)
                    parsed_date = parse_date(date_raw) if date_raw else fallback_date
                    if not parsed_date:
                        raise CsvImportError("評価日が見つかりません。--valuation-date を指定してください。")
                    period_month = period_month_from_date(parsed_date)
                    current_value = parse_int(pick(row, CURRENT_VALUE_COLUMNS))
                    if current_value is None:
                        totals["skipped"] += 1
                        continue

                    with _db_ctx(db_path) as conn:
                        product_id, product_state = ensure_asset_product(
                            conn,
                            name=name,
                            asset_type=asset_type,
                            institution=institution,
                            account_type=account_type,
                        )
                        if product_state == "inserted":
                            totals["products_inserted"] += 1
                        elif product_state == "updated":
                            totals["products_updated"] += 1

                        result = upsert_asset_snapshot(
                            conn,
                            {
                                "asset_id": product_id,
                                "valuation_date": parsed_date,
                                "period_month": period_month,
                                "quantity": parse_number(pick(row, QUANTITY_COLUMNS)),
                                "base_price": parse_number(pick(row, BASE_PRICE_COLUMNS)),
                                "acquisition_price": parse_number(pick(row, ACQUISITION_PRICE_COLUMNS)),
                                "current_value_yen": current_value,
                                "invested_amount_yen": parse_int(pick(row, INVESTED_AMOUNT_COLUMNS)),
                                "profit_loss_yen": parse_int(pick(row, PROFIT_LOSS_COLUMNS)),
                                "profit_loss_rate": parse_number(pick(row, PROFIT_LOSS_RATE_COLUMNS)),
                                "daily_change_yen": parse_int(pick(row, DAILY_CHANGE_YEN_COLUMNS)),
                                "daily_change_rate": parse_number(pick(row, DAILY_CHANGE_RATE_COLUMNS)),
                                "dividend_method": normalize_text(pick(row, DIVIDEND_METHOD_COLUMNS)) or None,
                                "source": "csv",
                            },
                        )
                    totals[result] += 1
                except Exception as exc:
                    totals["errors"] += 1
                    with _db_ctx(db_path) as conn:
                        conn.execute(
                            "INSERT INTO import_errors(run_id, source_id, external_id, subject, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (run_id, SOURCE_ID, f"{path}:{i}", path.name, str(exc), utc_now_iso()),
                        )
        with _db_ctx(db_path) as conn:
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
        with _db_ctx(db_path) as conn:
            conn.execute(
                "UPDATE import_runs SET finished_at = ?, status = 'failed', error_count = ?, message = ? WHERE id = ?",
                (utc_now_iso(), totals["errors"] + 1, traceback.format_exc(), run_id),
            )
        raise


def default_csv_paths() -> list[Path]:
    pattern = str(project_path("data", "imports", "assets", "*.csv"))
    return expand_paths([pattern])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import SBI-style asset CSV files into the local database.")
    parser.add_argument("paths", nargs="*", help="CSV file path, directory, or wildcard")
    parser.add_argument("--valuation-date", help="Fallback evaluation date (YYYY-MM-DD) when CSV has no 評価日 column")
    parser.add_argument("--institution", default=DEFAULT_INSTITUTION)
    parser.add_argument("--account-type", default=DEFAULT_ACCOUNT_TYPE)
    parser.add_argument("--asset-type", default="investment_trust")
    args = parser.parse_args(argv)

    paths = expand_paths(args.paths) if args.paths else default_csv_paths()
    result = import_files(
        paths,
        valuation_date=args.valuation_date,
        institution=args.institution,
        account_type=args.account_type,
        asset_type=args.asset_type,
    )
    print("Asset CSV import completed.")
    print(
        f"files: {result['files']} / rows: {result['fetched']} / inserted: {result['inserted']} / "
        f"updated: {result['updated']} / skipped: {result['skipped']} / errors: {result['errors']}"
    )
    print(f"products inserted: {result['products_inserted']} / products updated: {result['products_updated']}")
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
