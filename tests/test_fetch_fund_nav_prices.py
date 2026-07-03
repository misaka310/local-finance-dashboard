from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from mfblue.fetch_fund_nav_prices import parse_mufg_chart_js, parse_mufg_official_api_json, parse_nam_csv, parse_wealthadvisor_xml
from mfblue.generate_asset_snapshots import select_nav_price
from mfblue.paths import project_path


class FetchFundNavPricesTests(unittest.TestCase):
    def test_parse_mufg_js(self) -> None:
        text = Path(project_path("tests", "fixtures", "mufg_nav_sample.js")).read_text(encoding="utf-8")
        rows = parse_mufg_chart_js(text)
        self.assertEqual(rows[1], ("2024-07-31", 10234.0))

    def test_parse_nam_csv(self) -> None:
        text = Path(project_path("tests", "fixtures", "nam_nav_sample.csv")).read_text(encoding="utf-8")
        rows = parse_nam_csv(text)
        self.assertEqual(rows[0], ("2024-07-31", 12100.0))

    def test_parse_mufg_official_api_json(self) -> None:
        text = Path(project_path("tests", "fixtures", "mufg_official_api_sample.json")).read_text(encoding="utf-8")
        rows = parse_mufg_official_api_json(text)
        self.assertEqual(rows[0], ("2026-05-16", 43125.0))

    def test_parse_wealthadvisor_xml(self) -> None:
        text = Path(project_path("tests", "fixtures", "wa_nav_sample.xml")).read_text(encoding="utf-8")
        rows = parse_wealthadvisor_xml(text)
        self.assertIn(("2024-07-31", 11111.0), rows)

    def test_select_nav_price_uses_last_business_day_in_month(self) -> None:
        rows = [
            {"price_date": "2024-07-29", "base_price": 10000},
            {"price_date": "2024-07-30", "base_price": 10100},
        ]
        selected = select_nav_price(rows, target_month_end=date(2024, 7, 31))
        self.assertEqual(selected, ("2024-07-30", 10100.0))


if __name__ == "__main__":
    unittest.main()
