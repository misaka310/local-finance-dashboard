# mfblue-local-budget

PayPayカード利用通知メールやAmazon注文確定メールをGmailから読み取り、ローカルSQLiteに保存し、マネーフォワードME風の月別・カテゴリ別画面で支出を見るためのローカル家計簿アプリです。

- 取り込み対象は **PayPayカード利用通知メール** と **Amazon注文確定/注文確認メール** です。
- Gmail権限は読み取り専用の `gmail.readonly` だけを使います。
- Gmail OAuthトークンは、Python `keyring` 経由でOSの資格情報保管領域に保存します。
- 明細本文全文や商品名は保存せず、日付・店名・金額・分類などの必要項目だけをSQLiteに保存します。
- 実データ、OAuthクライアントJSON、SQLite DB、CSV取り込みファイルはリポジトリに含めません。

## デモ

![mfblue-local-budget demo](docs/images/demo.png)

## まずUIだけ試す

Gmail認証なしで、サンプル明細を入れて画面を確認できます。Windowsならリポジトリ直下で次を実行します。

```cmd
start_sample_mfblue.cmd
```

このコマンドは、セットアップ、サンプルデータ追加、UI起動までを順番に実行します。ブラウザで次を開きます。

```text
http://127.0.0.1:8765
```

成功すると、サンプル明細が入った家計簿画面が表示されます。`.\scripts\04_run_app.ps1` は `--open-browser` 付きで起動するため、環境によってはブラウザが自動で開きます。

個別に実行したい場合:

```powershell
.\scripts\01_setup.ps1
.\scripts\05_seed_sample_data.ps1
.\scripts\04_run_app.ps1
```

## 自分のGmailから取り込む

初回だけ:

1. Google Cloudでデスクトップアプリ用OAuthクライアントを作る
2. ダウンロードしたJSONを `secrets/google_oauth_client.json` として置く
3. PowerShellで `.\scripts\01_setup.ps1` を実行
4. PowerShellで `.\scripts\02_authorize_gmail.ps1` を実行

普段使うとき:

1. PowerShellで `.\scripts\03_sync_now.ps1` を実行してGmailから取り込む
2. PowerShellで `.\scripts\04_run_app.ps1` を実行
3. ブラウザで `http://127.0.0.1:8765` を開く

詳しい手順は `docs/SETUP.md` を見てください。

## ディレクトリ構成

```text
mfblue-local-budget/
  config/                 アプリ設定
  data/                   SQLite DB保存先・CSV置き場（実データはGit管理外）
  docs/                   手順・設計・セキュリティメモ
  frontend/               ローカルUI
  scripts/                Windows用起動スクリプト
  secrets/                Google OAuthクライアントJSON置き場（実ファイルはGit管理外）
  src/mfblue/             Python本体
```

## 注意

PayPayカード利用速報は、利用先・利用金額によって通知が届かない場合があります。このアプリは「通知メールから作るローカル家計簿」であり、カード会社の確定請求明細そのものではありません。

Amazon取り込みは、Amazon注文確定/注文確認メールを家計簿用Gmailへ転送する運用を前提にしています。発送通知、配達通知、キャンセル、返金、広告系メールは取り込み対象外です。Amazonメール形式の変更などで取り込みに失敗した場合は `import_errors` を確認してください。

## Codex App Server分析（WebSocket）

- 月次分析 / 年間分析は、Pythonバックエンド経由で `Codex App Server` に接続して実行します。
- 接続先はデフォルトで `ws://127.0.0.1:8787`（`config/app.json` の `analysis.codex_app_server_url` で変更可能）。
- ブラウザから直接接続せず、`/api/analysis` と `/api/analysis/run` を使います。
- App Server未起動時は分析のみ失敗し、家計簿の閲覧・明細表示は継続できます。
- 分析結果は `analysis_runs` テーブルに保存され、同じ `input_hash` なら再利用されます。

起動方法:

```powershell
codex app-server --listen ws://127.0.0.1:8787
```

または:

```powershell
.\scripts\10_run_codex_app_server.ps1
```

ローカル専用運用を前提としており、Windowsファイアウォールの外部公開設定やパブリックネットワーク許可は不要です。

## PayPayカードCSV取り込み

過去分の明細はCSVから取り込めます。CSVはリポジトリにコミットしないでください。

```powershell
.\scripts\07_import_paypay_csv.ps1 "%USERPROFILE%\Downloads\detail*.csv"
```

## Amazon注文履歴CSV取り込み

- 実行時に「今回取り込むCSV」が必ず表示されます。
- 引数なし実行は `data/imports/amazon/*.csv` が対象です。古いCSV混入防止のため、明示指定を推奨します。

```powershell
.\scripts\08_import_amazon_history_csv.ps1
```

```powershell
.\scripts\08_import_amazon_history_csv.ps1 "data/imports/amazon/2026-05.csv"
```

取り込み見込みだけ確認する場合:

```powershell
.\scripts\08_import_amazon_history_csv.ps1 -DryRun
```

成功したCSVを `data/imports/amazon/imported/` へ移動する場合:

```powershell
.\scripts\08_import_amazon_history_csv.ps1 -MoveImported
```

## 資産（SBI証券）CSV取り込み

資産タブ向けのスナップショットは `data/imports/assets/*.csv` から取り込めます。CSVはリポジトリにコミットしないでください。

```powershell
.\scripts\13_import_assets_csv.ps1
```

評価日列がCSVにない場合は、取り込み時に指定できます。

```powershell
.\scripts\13_import_assets_csv.ps1 "data/imports/assets/sbi_2026-02.csv" -ValuationDate "2026-02-28"
```

## Galaxy向け読み取り専用HTMLエクスポート

Galaxyなどでオフライン閲覧するために、単一HTMLの読み取り専用エクスポートを追加しています。

```powershell
.\scripts\12_export_readonly_html.ps1
```

生成物:

- `dist/readonly/mfblue_readonly.html`
- `dist/readonly/mfblue_readonly.zip`

使い方:

1. `mfblue_readonly.zip` をGalaxyへ転送
2. GalaxyでZIPを展開
3. `mfblue_readonly.html` をブラウザで開く

このHTMLは書き出し時点の固定データです。編集・同期・再分析はできません。内容更新はPCで再エクスポートしてください。

## 資産タブの月次復元（取引履歴 + 基準価額）

取引履歴CSVと公開基準価額から、過去月の評価額スナップショットを自動生成できます。  
手順と取得元URLは [docs/ASSET_HISTORY.md](docs/ASSET_HISTORY.md) を参照してください。

三菱UFJアセットマネジメント系ファンドは、`developer.am.mufg.jp` の公式Web API（`fund_information_date` / `fund_information_latest`）を優先し、API失敗時のみ公式公開データ（`chart_data_*.js`）へフォールバックします。

重複修復が必要な場合:

```powershell
.\scripts\17_repair_asset_snapshot_duplicates.ps1 -VerifyMonth 2026-05 -ExpectTotal 1234567
```

## License

MIT License. See [LICENSE](LICENSE).
