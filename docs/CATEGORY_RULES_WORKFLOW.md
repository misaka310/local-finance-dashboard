# 分類ルール運用ガイド

## 取り込み方針
- 過去分は PayPayカードCSV (`.\scripts\07_import_paypay_csv.ps1`) で取り込む。
- 今後分は Gmail 利用速報 (`.\scripts\03_sync_now.ps1`) で取り込む。

## 分類を効率化する流れ
- 1件ずつ分類を直す前に `.\scripts\08_export_merchant_candidates.ps1` を実行する。
- `data/classification/merchant_candidates.csv` を確認し、店名ベースで `data/classification/category_rules.csv` を作成する。
- `.\scripts\09_import_category_rules.ps1` を実行して、分類ルール登録と既存明細への一括適用を行う。
- 実行後はUIを再読み込みして、カテゴリ表示を更新する。

## プライバシー配慮
- 外部AIや外部委託に渡す場合は、全明細CSVではなく `merchant_candidates.csv` を使う。
- `merchant_candidates.csv` は店名・件数・合計金額のみなので、明細本文を渡すより安全。

## 注意点
- `data/` と `secrets/` は Git 管理しない。
- Amazon、楽天、Yahoo!ショッピングなど用途が広い店名は自動分類しすぎない。
  必要なら `未分類` のままにして手動判断を残す。
- 分類ルールCSVの `match_type` は `exact` または `contains`。
  `exact` が優先され、`contains` はパターンが長いものが優先される。
