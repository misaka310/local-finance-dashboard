# 入力ガイド

実CSVはGit管理しません。`data/imports/` に置き、取り込み後も公開リポジトリへ追加しないでください。

## PayPayカードCSV

```powershell
.\scripts\07_import_paypay_csv.ps1 "%USERPROFILE%\Downloads\detail*.csv"
```

CSV行は安定した識別子を生成して取り込みます。同じ明細を再取り込みした場合は既存の明細を更新します。

## Amazon注文履歴CSV

```powershell
.\scripts\08_import_amazon_history_csv.ps1 "data/imports/amazon/2026-05.csv"
```

引数なしでは `data/imports/amazon/*.csv` が対象です。古いCSVの混入を避けるため、対象ファイルを明示することを推奨します。

```powershell
.\scripts\08_import_amazon_history_csv.ps1 -DryRun
.\scripts\08_import_amazon_history_csv.ps1 -MoveImported
```

`-DryRun` はDBを変更せず取り込み見込みだけを確認します。`-MoveImported` は成功したCSVを `data/imports/amazon/imported/` へ移動します。

## 証券資産CSV

```powershell
.\scripts\13_import_assets_csv.ps1 "data/imports/assets/sbi_2026-02.csv" -ValuationDate "2026-02-28"
```

評価日列がCSVにある場合はその値を使用します。資産と月が同じスナップショットは更新として扱います。取引履歴・基準価額による履歴生成は [資産履歴](ASSET_HISTORY.md) を参照してください。
