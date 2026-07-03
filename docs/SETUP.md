# セットアップ手順

## 1. リポジトリを取得する

GitHubからcloneするか、ZIPを展開して、PowerShellでリポジトリ直下へ移動します。

```powershell
git clone https://github.com/misaka310/mfblue-local-budget.git
cd mfblue-local-budget
```

ZIPで取得した場合は、展開したフォルダで以降のコマンドを実行してください。

## 2. UIだけ先に試す

Gmail認証なしで、サンプル明細を入れて画面を確認できます。Windowsならリポジトリ直下で次を実行します。

```cmd
start_sample_mfblue.cmd
```

このコマンドは、セットアップ、サンプルデータ追加、UI起動までを順番に実行します。ブラウザで次を開きます。

```text
http://127.0.0.1:8765
```

成功条件は、サンプル明細が入った家計簿画面が表示されることです。

個別に実行したい場合:

```powershell
.\scripts\01_setup.ps1
.\scripts\05_seed_sample_data.ps1
.\scripts\04_run_app.ps1
```

## 3. Google OAuthクライアントを用意する

自分のGmailから取り込む場合だけ必要です。Google Cloud Consoleで、Gmail APIを有効化し、OAuthクライアントを作成します。

- アプリ種類: デスクトップアプリ
- 使用スコープ: `https://www.googleapis.com/auth/gmail.readonly`

ダウンロードしたJSONを次の名前で保存します。

```text
secrets\google_oauth_client.json
```

このファイルはGit管理外です。公開リポジトリへコミットしないでください。

## 4. 初回セットアップ

PowerShellでリポジトリ直下に移動して、次を実行します。

```powershell
.\scripts\01_setup.ps1
```

この処理で次を行います。

- `.venv` 作成
- Python依存関係インストール
- SQLite DB初期化
- 初期カテゴリと分類ルール登録

## 5. Gmail認証

```powershell
.\scripts\02_authorize_gmail.ps1
```

ブラウザが開くので、Gmail読み取り専用の許可をします。OAuthトークンはPython `keyring` 経由でOSの資格情報保管領域に保存されます。

## 6. Gmail同期

```powershell
.\scripts\03_sync_now.ps1
```

`config/app.json` の `gmail.sources` に設定した各ソースのGmail検索条件でメールを取得し、ソースごとのパーサーで解析します。

- `paypay-card`: PayPayカード利用通知
- `amazon-order`: Amazon注文確定/注文確認（発送・配達・キャンセル・返金・広告系は除外）

Amazonメールは、別Gmailから家計簿用Gmailへフィルター転送されたメールも対象にできます。

## 7. UI起動

```powershell
.\scripts\04_run_app.ps1
```

ブラウザで次を開きます。

```text
http://127.0.0.1:8765
```

## Gmail検索条件を変えたい場合

`config/app.json` の `gmail.sources` を編集してください。既存互換のため `gmail.query` も残っていますが、新規設定では `sources` の利用を推奨します。

初期値（抜粋）:

```json
"sources": [
  {
    "source_id": "paypay-card",
    "query": "newer_than:180d (from:(paypay-card.co.jp) OR subject:(PayPayカード) OR \"PayPayカード\")"
  },
  {
    "source_id": "amazon-order",
    "query": "newer_than:180d from:(amazon.co.jp) (subject:(注文を確定しました OR ご注文の確認 OR 注文確認 OR ご注文ありがとうございます OR 注文内容の確認) -subject:(発送 OR 出荷 OR 配達 OR お届け OR キャンセル OR 返金 OR 返品 OR セール OR おすすめ OR Prime))"
  }
]
```

パーサー未対応やメール形式変更で取り込み失敗が出た場合は、SQLiteの `import_errors` を確認してください。プライバシー方針として、本文全文や商品名は保存しません。

## Amazon注文履歴CSVの取り込み

- Amazon注文履歴から作成したCSVは `data/imports/amazon/` に配置します。
- CSVは `data/imports/` 配下のためGit管理外です。CSVファイルはコミットしません。
- 実行時に「今回取り込むCSV」が表示されます。
- 引数未指定時は `data/imports/amazon/*.csv` 全件が対象です。古いCSV混入防止のため、可能なら明示指定を推奨します。
- 取り込みは以下を実行します。

```powershell
.\scripts\08_import_amazon_history_csv.ps1
```

引数を渡す場合はファイル、ディレクトリ、ワイルドカードを指定できます。

```powershell
.\scripts\08_import_amazon_history_csv.ps1 "data/imports/amazon/*.csv"
```

dry-run（DB更新なし）で見込みを確認:

```powershell
.\scripts\08_import_amazon_history_csv.ps1 -DryRun
```

成功したCSVを `data/imports/amazon/imported/` へ移動:

```powershell
.\scripts\08_import_amazon_history_csv.ps1 -MoveImported
```

0円注文（`amount_yen <= 0`）は取り込みません。UIでは口座フィルターで `すべて / PayPayカード / Amazon注文履歴 / Amazonメール` を切り替えて集計と明細を確認できます。

## Codex App Serverによる分析

- 月次/年間分析はWebSocket(JSON-RPC)でCodex App Serverへ接続します。
- 接続先デフォルト: `ws://127.0.0.1:8787`（`config/app.json` の `analysis` セクションで変更可能）。
- ブラウザから直接接続せず、mfblueのPythonバックエンド経由で実行します。
- App Serverが未起動でも、家計簿の閲覧機能は利用できます（分析のみ失敗表示）。

起動例:

```powershell
codex app-server --listen ws://127.0.0.1:8787
```

または:

```powershell
.\scripts\10_run_codex_app_server.ps1
```

外部公開前提ではありません。Windowsファイアウォールで外部公開やパブリックネットワーク許可は不要です。

分析結果はSQLiteの `analysis_runs` に保存され、同じ `input_hash` なら再利用されます。
