from __future__ import annotations

import unittest

from mfblue.paths import project_path


class AssetsFrontendTests(unittest.TestCase):
    def test_assets_view_is_single_summary_card_and_no_slider_dots(self) -> None:
        app_js = project_path("frontend", "app.js").read_text(encoding="utf-8")
        css = project_path("frontend", "styles.css").read_text(encoding="utf-8")
        html = project_path("frontend", "index.html").read_text(encoding="utf-8")

        self.assertIn("mascotImageHtml('cheer', 'たぬきマスコット', 'asset-total-mascot')", app_js)
        self.assertIn(".asset-card-total .asset-mascot-wrap", css)
        self.assertIn("asset-card-breakdown", app_js)
        self.assertNotIn("assetCardDots", app_js)
        self.assertNotIn("assetCardDots", html)
        self.assertIn(".asset-chart-y-label", css)
        self.assertIn("asset-holding-pnl", app_js)
        self.assertIn("id=\"assetModeMonth\"", html)
        self.assertIn("id=\"assetModeYear\"", html)
        self.assertIn("id=\"assetRefreshPricesButton\"", html)
        self.assertIn("総資産差（買い増し込み）", app_js)
        self.assertIn("運用増減（買い増し除外）", app_js)


if __name__ == "__main__":
    unittest.main()
