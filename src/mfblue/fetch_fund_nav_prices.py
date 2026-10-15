from __future__ import annotations

import argparse
import calendar
import csv
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .asset_fund_names import normalize_asset_fund_name
from .db import (
    connect,
    init_db,
    list_fund_price_sources,
    upsert_fund_nav_price,
    upsert_fund_price_source,
)
from .fund_price_sources import load_fund_price_sources


class NavFetchError(Exception):
    pass


def parse_iso_date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise NavFetchError("response encoding is unsupported")


def fetch_text(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "local-finance-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310
        raw = res.read()
    return decode_bytes(raw)


def parse_mufg_chart_js(text: str) -> list[tuple[str, float]]:
    payload = json.loads(text.strip())
    rows = payload.get("ROWS") or []
    result: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        base_date = str(row.get("BASE_DATE") or "").strip()
        base_price = row.get("BASE_PRICE")
        if len(base_date) != 8 or base_price in {None, ""}:
            continue
        price_date = f"{base_date[0:4]}-{base_date[4:6]}-{base_date[6:8]}"
        result.append((price_date, float(base_price)))
    return result


def parse_mufg_official_api_json(text: str) -> list[tuple[str, float]]:
    payload = json.loads(text.strip())
    datasets = payload.get("datasets") or []
    if isinstance(datasets, dict):
        datasets = [datasets]
    result: list[tuple[str, float]] = []
    for row in datasets:
        if not isinstance(row, dict):
            continue
        base_date = str(row.get("base_date") or "").strip()
        nav = row.get("nav")
        if len(base_date) != 8 or nav in {None, ""}:
            continue
        price_date = f"{base_date[0:4]}-{base_date[4:6]}-{base_date[6:8]}"
        result.append((price_date, float(nav)))
    return result


def parse_nam_csv(text: str) -> list[tuple[str, float]]:
    reader = csv.DictReader(text.splitlines())
    result: list[tuple[str, float]] = []
    for row in reader:
        day = str(row.get("日付") or "").strip()
        base_price = str(row.get("基準価額") or "").strip().replace(",", "")
        m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", day)
        if not m or not base_price:
            continue
        y, mth, d = [int(x) for x in m.groups()]
        result.append((f"{y:04d}-{mth:02d}-{d:02d}", float(base_price)))
    return result


def parse_wealthadvisor_xml(text: str) -> list[tuple[str, float]]:
    root = ET.fromstring(text)
    result: list[tuple[str, float]] = []
    for day in root.findall(".//day"):
        year = str(day.attrib.get("year") or "").strip()
        month = str(day.attrib.get("month") or "").strip()
        value = str(day.attrib.get("value") or "").strip()
        price = str(day.attrib.get("price") or "").strip()
        if not year or not month or not value or not price:
            continue
        result.append((f"{int(year):04d}-{int(month):02d}-{int(value):02d}", float(price)))
    return result


def parse_manual_csv(path: Path) -> list[tuple[str, float]]:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    result: list[tuple[str, float]] = []
    for row in reader:
        day = str(row.get("price_date") or row.get("date") or "").strip()
        price_raw = str(row.get("base_price") or row.get("price") or "").strip().replace(",", "")
        if not day or not price_raw:
            continue
        result.append((day, float(price_raw)))
    return result


PARSERS = {
    "mufg_chart_js": parse_mufg_chart_js,
    "mufg_official_api_json": parse_mufg_official_api_json,
    "nam_csv_cp932": parse_nam_csv,
    "wealthadvisor_fund_xml": parse_wealthadvisor_xml,
}


def month_end_first_key(item: tuple[str, float]) -> tuple[int, str]:
    day = parse_iso_date(item[0])
    month_end = calendar.monthrange(day.year, day.month)[1]
    is_month_end = 1 if day.day == month_end else 0
    return (-is_month_end, item[0])


def _source_priority(source: dict[str, Any]) -> tuple[int, int]:
    source_type = str(source.get("source_type") or "")
    parser_name = str(source.get("parser_name") or "")
    if source_type == "official_api":
        return (0, 0)
    if source_type == "official_public_data":
        return (1, 0 if parser_name == "mufg_chart_js" else 1)
    if source_type == "official_csv":
        return (2, 0)
    if source_type == "manual_csv":
        return (3, 0)
    return (9, 0)


def _date_token(day: date) -> str:
    return f"{day.year:04d}{day.month:02d}{day.day:02d}"


def _date_iter(start: date, end: date) -> list[date]:
    cursor = start
    items: list[date] = []
    while cursor <= end:
        items.append(cursor)
        cursor += timedelta(days=1)
    return items


def _existing_latest_price_date(
    conn,
    *,
    normalized_fund_name: str,
    provider_name: str,
) -> str | None:
    rows = conn.execute(
        """
        SELECT fund_name, price_date
        FROM fund_nav_prices
        WHERE provider_name = ?
        ORDER BY price_date DESC, id DESC
        """,
        (provider_name,),
    ).fetchall()
    for row in rows:
        if normalize_asset_fund_name(str(row["fund_name"] or "")) == normalized_fund_name:
            return str(row["price_date"])
    return None


def _resolve_official_api_range(
    conn,
    *,
    normalized_fund_name: str,
    provider_name: str,
    date_from: str | None,
    date_to: str | None,
) -> tuple[date, date]:
    today = date.today()
    end = parse_iso_date(date_to) if date_to else today
    if date_from:
        return (parse_iso_date(date_from), end)
    latest = _existing_latest_price_date(
        conn,
        normalized_fund_name=normalized_fund_name,
        provider_name=provider_name,
    )
    if latest:
        start = parse_iso_date(latest) + timedelta(days=1)
        return (start, end)
    # 初回は短めに取得し、必要に応じて公式公開データへフォールバックする。
    return (end - timedelta(days=45), end)


def _fetch_mufg_official_api_rows(
    source_url: str,
    *,
    date_from: date,
    date_to: date,
) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    parser = PARSERS["mufg_official_api_json"]
    for day in _date_iter(date_from, date_to):
        url = source_url.replace("{base_date}", _date_token(day))
        text = fetch_text(url)
        parsed = parser(text)
        rows.extend(parsed)
    return rows


def fetch_nav_prices(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    range_from = parse_iso_date(date_from) if date_from else None
    range_to = parse_iso_date(date_to) if date_to else None
    totals = {
        "sources": 0,
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "error_details": [],
    }
    conn = connect()
    try:
        init_db(conn)
        for source in load_fund_price_sources():
            upsert_fund_price_source(conn, source)
        conn.commit()

        source_rows = list_fund_price_sources(conn, active_only=True)
        grouped_sources: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for src in source_rows:
            fund_name = str(src["fund_name"] or "")
            provider = str(src["provider_name"] or "")
            key = (normalize_asset_fund_name(fund_name), provider)
            grouped_sources.setdefault(key, []).append(src)

        totals["sources"] = len(source_rows)
        for (_, provider), group in grouped_sources.items():
            ordered = sorted(group, key=_source_priority)
            source_applied = False

            for src in ordered:
                fund_name = str(src["fund_name"])
                source_url = str(src["source_url"])
                parser_name = str(src["parser_name"])
                source_type = str(src["source_type"])
                normalized_fund_name = normalize_asset_fund_name(fund_name)
                print(f"[nav] fetch: fund={fund_name} provider={provider} parser={parser_name} url={source_url}")
                try:
                    if source_type == "manual_csv":
                        rows = parse_manual_csv(Path(source_url))
                    elif source_type == "official_api":
                        api_from, api_to = _resolve_official_api_range(
                            conn,
                            normalized_fund_name=normalized_fund_name,
                            provider_name=provider,
                            date_from=date_from,
                            date_to=date_to,
                        )
                        if api_from > api_to:
                            rows = []
                        else:
                            rows = _fetch_mufg_official_api_rows(
                                source_url,
                                date_from=api_from,
                                date_to=api_to,
                            )
                    else:
                        parser = PARSERS.get(parser_name)
                        if not parser:
                            raise NavFetchError(f"unknown parser_name: {parser_name}")
                        text = fetch_text(source_url)
                        rows = parser(text)

                    filtered: list[tuple[str, float]] = []
                    for price_date, base_price in rows:
                        day = parse_iso_date(price_date)
                        if range_from and day < range_from:
                            continue
                        if range_to and day > range_to:
                            continue
                        filtered.append((price_date, base_price))
                    filtered.sort(key=month_end_first_key)

                    existing_dates: set[str] = set()
                    if not force:
                        where: list[str] = ["provider_name = ?"]
                        params: list[Any] = [provider]
                        if date_from:
                            where.append("price_date >= ?")
                            params.append(date_from)
                        if date_to:
                            where.append("price_date <= ?")
                            params.append(date_to)
                        query = "SELECT fund_name, price_date FROM fund_nav_prices WHERE " + " AND ".join(where)
                        for row in conn.execute(query, params).fetchall():
                            if normalize_asset_fund_name(str(row["fund_name"] or "")) != normalized_fund_name:
                                continue
                            existing_dates.add(str(row["price_date"]))

                    for price_date, base_price in filtered:
                        totals["fetched"] += 1
                        if not force and price_date in existing_dates:
                            totals["skipped"] += 1
                            continue
                        status = upsert_fund_nav_price(
                            conn,
                            {
                                "fund_name": fund_name,
                                "price_date": price_date,
                                "base_price": base_price,
                                "provider_name": provider,
                                "source_url": source_url,
                            },
                        )
                        totals[status] += 1
                    conn.commit()
                    source_applied = True
                    break
                except Exception as exc:
                    totals["errors"] += 1
                    totals["error_details"].append(
                        {
                            "fund_name": fund_name,
                            "provider_name": provider,
                            "parser_name": parser_name,
                            "source_url": source_url,
                            "error": str(exc),
                        }
                    )
                    print(f"[nav] error: fund={fund_name} parser={parser_name} reason={exc}")
                    conn.commit()
                    continue
            if not source_applied:
                continue
    finally:
        conn.close()
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch fund nav prices from public source pages.")
    parser.add_argument("--from", dest="date_from", help="from date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="to date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="refetch even if cached")
    args = parser.parse_args(argv)
    result = fetch_nav_prices(date_from=args.date_from, date_to=args.date_to, force=args.force)
    print("Fund nav fetch completed.")
    print(
        f"sources: {result['sources']} / fetched: {result['fetched']} / inserted: {result['inserted']} / "
        f"updated: {result['updated']} / skipped: {result['skipped']} / errors: {result['errors']}"
    )
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
