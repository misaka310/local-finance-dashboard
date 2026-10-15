from __future__ import annotations

import argparse
import csv
import glob
import re
from pathlib import Path
from typing import Iterable

from .asset_fund_names import normalize_asset_fund_name
from .db import add_asset_trade, connect, ensure_asset_product, init_db
from .paths import project_path

DEFAULT_INSTITUTION = "SBI証券"

ACCOUNT_TYPE_MAP = {
    "NISA (成長)": "新NISA（成長投資枠）",
    "NISA (つみたて)": "新NISA（つみたて投資枠）",
}

TRADE_TYPE_MAP = {
    "買付": "buy",
    "売却": "sell",
    "分配金再投資": "dividend_reinvest",
}


class TradeImportError(Exception):
    pass


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "cp932", "shift_jis", "utf-8"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise TradeImportError(f"unsupported csv encoding: {path}")


def normalize_header(name: str) -> str:
    return (name or "").strip().replace("\ufeff", "")


def normalize_key(name: str) -> str:
    return re.sub(r"[\s\u3000/()（）]", "", normalize_header(name)).lower()


def parse_date(value: str) -> str:
    text = str(value or "").strip()
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)
    if not m:
        raise TradeImportError(f"could not parse date: {value}")
    y, mth, d = [int(x) for x in m.groups()]
    return f"{y:04d}-{mth:02d}-{d:02d}"


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
        "－": "-",
        "ー": "-",
        "−": "-",
        "＋": "+",
    }
)


def parse_number(value: str) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"--", "未設定"}:
        return None
    text = text.translate(_FULL_WIDTH_TRANS).replace(",", "")
    text = re.sub(r"[^\d\.\-\+]", "", text)
    if text in {"", "+", "-", ".", "+.", "-."}:
        return None
    return float(text)


def parse_int(value: str) -> int | None:
    num = parse_number(value)
    if num is None:
        return None
    return int(round(num))


def parse_rows(path: Path) -> list[dict[str, str]]:
    text = read_text(path)
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise TradeImportError(f"header not found: {path}")
    original = [normalize_header(x) for x in reader.fieldnames]
    normalized = [normalize_key(x) for x in original]
    rows: list[dict[str, str]] = []
    for row in reader:
        item: dict[str, str] = {}
        for key_org, key_norm in zip(original, normalized):
            item[key_norm] = str(row.get(key_org) or "").strip()
        rows.append(item)
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
    seen: set[str] = set()
    unique: list[Path] = []
    for path in result:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def pick(row: dict[str, str], *names: str) -> str:
    for name in names:
        key = normalize_key(name)
        if key in row:
            value = str(row.get(key) or "").strip()
            if value:
                return value
    return ""


def normalize_account_type(value: str) -> str:
    raw = str(value or "").strip()
    return ACCOUNT_TYPE_MAP.get(raw, raw or "不明")


def normalize_trade_type(value: str) -> str:
    raw = str(value or "").strip()
    return TRADE_TYPE_MAP.get(raw, "other")


def import_trade_files(paths: list[Path], *, db_path: Path | None = None) -> dict[str, int]:
    if not paths:
        raise TradeImportError("no trade csv files were specified")
    totals = {
        "files": 0,
        "rows": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
        "products_inserted": 0,
        "products_updated": 0,
    }
    conn = connect(db_path)
    try:
        init_db(conn)
        for path in paths:
            totals["files"] += 1
            if not path.exists():
                totals["errors"] += 1
                continue
            rows = parse_rows(path)
            for row in rows:
                totals["rows"] += 1
                try:
                    trade_date = parse_date(pick(row, "約定日"))
                    settlement_raw = pick(row, "受渡日")
                    settlement_date = parse_date(settlement_raw) if settlement_raw else None
                    fund_name = pick(row, "銘柄")
                    if not fund_name:
                        totals["skipped"] += 1
                        continue
                    if not normalize_asset_fund_name(fund_name):
                        totals["skipped"] += 1
                        continue
                    account_type = normalize_account_type(pick(row, "預り"))
                    trade_type = normalize_trade_type(pick(row, "取引"))
                    quantity = parse_number(pick(row, "約定数量"))
                    unit_price = parse_number(pick(row, "約定単価"))
                    amount_yen = parse_int(pick(row, "受渡金額"))

                    _, product_state = ensure_asset_product(
                        conn,
                        name=fund_name,
                        asset_type="investment_trust",
                        institution=DEFAULT_INSTITUTION,
                        account_type=account_type,
                    )
                    if product_state == "inserted":
                        totals["products_inserted"] += 1
                    elif product_state == "updated":
                        totals["products_updated"] += 1

                    saved = add_asset_trade(
                        conn,
                        {
                            "trade_date": trade_date,
                            "settlement_date": settlement_date,
                            "fund_name": fund_name,
                            "institution": DEFAULT_INSTITUTION,
                            "account_type": account_type,
                            "trade_type": trade_type,
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "amount_yen": amount_yen,
                            "source": "csv",
                        },
                    )
                    totals[saved["status"]] += 1
                except Exception:
                    totals["errors"] += 1
        conn.commit()
    finally:
        conn.close()
    return totals


def default_paths() -> list[Path]:
    return expand_paths([str(project_path("data", "imports", "assets", "trades", "*.csv"))])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import SBI trade-history CSV files into asset_trades.")
    parser.add_argument("paths", nargs="*", help="CSV path, directory, or glob")
    args = parser.parse_args(argv)
    paths = expand_paths(args.paths) if args.paths else default_paths()
    result = import_trade_files(paths)
    print("Asset trades CSV import completed.")
    print(
        f"files: {result['files']} / rows: {result['rows']} / inserted: {result['inserted']} / "
        f"skipped: {result['skipped']} / errors: {result['errors']}"
    )
    print(f"products inserted: {result['products_inserted']} / products updated: {result['products_updated']}")
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
