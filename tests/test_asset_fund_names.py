from __future__ import annotations

import unittest

from mfblue.asset_fund_names import normalize_asset_fund_name


class AssetFundNameNormalizeTests(unittest.TestCase):
    def test_full_width_half_width_spacing_variants_match(self) -> None:
        a = "ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）"
        b = "eMAXIS Slim 米国株式（S&P500）"
        c = " eMAXIS  Slim  米国株式 ( S&P500 ) "
        self.assertEqual(normalize_asset_fund_name(a), normalize_asset_fund_name(b))
        self.assertEqual(normalize_asset_fund_name(b), normalize_asset_fund_name(c))


if __name__ == "__main__":
    unittest.main()

