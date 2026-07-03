# 資産タブ（月次復元）運用手順

## 目的
- 保有資産CSVの最新スナップショットだけでなく、取引履歴と公開基準価額から過去月の評価額を復元する。
- 資産タブで月次推移・年間成績・過去月の保有状態を表示する。

## 実行順
1. 取引履歴CSVを配置  
   `data/imports/assets/trades/*.csv`
2. 取引履歴を取り込む  
   `.\scripts\14_import_asset_trades_csv.ps1`
3. 公開基準価額を取得する  
   `.\scripts\15_fetch_fund_nav_prices.ps1 --from 2024-01-01`
4. 月次スナップショットを生成する  
   `.\scripts\16_generate_asset_snapshots.ps1`
5. 重複修復（必要時）  
   `.\scripts\17_repair_asset_snapshot_duplicates.ps1 -VerifyMonth 2026-05 -ExpectTotal 1234567`
6. アプリを再起動して資産タブを確認する

## 取引履歴CSVの取り込み仕様
- 対応列:
  - `約定日` → `trade_date`
  - `受渡日` → `settlement_date`
  - `銘柄` → `fund_name`
  - `預り` → `account_type`（`NISA (成長)` / `NISA (つみたて)` を新NISA区分へ正規化）
  - `取引` → `trade_type`（買付/売却/分配金再投資）
  - `約定数量` → `quantity`
  - `約定単価` → `unit_price`
  - `受渡金額` → `amount_yen`
- 保存先テーブル: `asset_trades`

## 基準価額取得元（公式API優先）
- 三菱UFJアセットマネジメント系ファンドは、公式Web API仕様書を一次情報として利用する。
  - 仕様書: https://www.am.mufg.jp/assets/pdf/tool/webapi/fund_api.pdf
  - API Host: `https://developer.am.mufg.jp`
  - 主要エンドポイント:
    - `GET /fund_information_latest/fund_cd/{fund_cd}`
    - `GET /fund_information_date/fund_cd/{fund_cd}/base_date/{yyyymmdd}`
  - `source_type` は `official_api` を使用。
  - APIで取得失敗時のみ `chart_data_*.js`（`official_public_data`）へフォールバックする。

- ｅＭＡＸＩＳ　Ｓｌｉｍ　米国株式（Ｓ＆Ｐ５００）  
  - 三菱ＵＦＪアセットマネジメント  
  - 公式API（fund_cd）: `253266` / 協会コード: `03311187`
  - API URL: `https://developer.am.mufg.jp/fund_information_date/fund_cd/253266/base_date/{base_date}`
  - フォールバック: `https://www.am.mufg.jp/fund_file/chart/chart_data_253266.js`
- ｅＭＡＸＩＳ　Ｓｌｉｍ　新興国株式インデックス  
  - 三菱ＵＦＪアセットマネジメント  
  - 公式API（fund_cd）: `252878` / 協会コード: `0331C177`
  - API URL: `https://developer.am.mufg.jp/fund_information_date/fund_cd/252878/base_date/{base_date}`
  - フォールバック: `https://www.am.mufg.jp/fund_file/chart/chart_data_252878.js`
- ニッセイＳＯＸ指数インデックスファンド（米国半導体株）＜購入・換金手数料なし＞  
  - ニッセイアセットマネジメント  
  - `https://www.nam.co.jp/fundinfo/data/csv.php?fund_code=122309`
- ＳＢＩ日本高配当株式（分配）ファンド（年４回決算型）  
  - SBIアセットマネジメント（公開ページからリンクされる公開データ）  
  - `https://apl.wealthadvisor.jp/xml/chart/funddata/2023121201.xml`

## 月次スナップショット生成仕様
- 計算式: `評価額 = 保有口数 × 基準価額 ÷ 10000`
- 売却は平均取得単価ベースで数量・取得金額を減算。
- 月末に基準価額がない場合は「同月内の直近営業日」を採用。
- `asset_snapshots.source='generated'` で保存。
- `manual/csv` の実測スナップショットは常に優先して保護（上書きしない）。
- `--force-generated` 指定時のみ既存 `generated` を更新。
- 集計時は「同一月 + 同一商品（正規化名） + 同一口座区分」で1件に統合し、`csv/manual` がある場合は `generated` を除外する。

## 重複修復
- `.\scripts\17_repair_asset_snapshot_duplicates.ps1` は以下を実施する。
  - 正規化名で `asset_products` を再寄せ
  - 同一月・同一商品の `generated` 重複を削除
  - 実測 (`csv/manual`) がある場合は実測を残す
