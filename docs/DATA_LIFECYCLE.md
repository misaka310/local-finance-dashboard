# データライフサイクル

## 明細の識別と再取り込み

`transactions` は `UNIQUE(source_id, external_id)` を持ちます。同じ外部識別子でも入力元が違えば別明細として保存でき、同一入力元から同じ明細を再取得した場合は `upsert_transaction` が更新として扱います。

- PayPayメールはGmail message IDを `external_id` として使用します。
- Amazonメールは注文番号を取得できた場合に `amazon-order:<注文番号>` を優先し、取得できない場合はGmail message IDを使います。
- Amazon注文履歴CSVはCSV内の注文識別子を使います。同じCSVを再取り込みしても行数を増やさず、既存行を更新します。

Amazonメールでは、以前のGmail message ID識別子が存在していて注文番号を得られた場合、同じ `source_id` の既存行を注文番号形式に移行してからupsertします。これにより、メールの再取得が別明細を作るのを防ぎます。

根拠となるテスト:

- `tests/test_db_source_uniqueness.py`: 入力元ごとの一意性
- `tests/test_sync_gmail_external_id.py`: PayPayのmessage ID、Amazon注文番号の優先、旧Amazon識別子の移行
- `tests/test_import_amazon_history_csv.py`: 同一CSVの再取り込みが更新になること、dry-runがDBへ書き込まないこと

## CSV取り込みとdry-run

Amazon注文履歴CSVの `-DryRun` は、入力検証と件数見込みを実行しますが、トランザクション・カテゴリ・インポート実行履歴・エラーをDBへ書き込みません。通常実行は有効な行をinsertまたはupdateとして記録し、0円行や不正なカテゴリなどはスキップまたはエラーとして数えます。

PayPayカードCSVは家計明細系として安定した識別子を使い、`transactions` をupsertします。証券資産CSVは資産系として商品と月のスナップショットキーを使い、`asset_products` と `asset_snapshots` をupsertします。実ファイルは `data/imports/` 配下に置き、Git管理しません。

## 資産スナップショットの優先順位

`asset_snapshots` は資産と月の組み合わせで一意です。CSVまたは手入力の実測スナップショットと、取引履歴・基準価額から生成したスナップショットが競合する場合は、実測値（`csv` / `manual`）を優先します。重複修復では対象月に実測値があれば生成値を削除します。

根拠となるテスト:

- `tests/test_import_assets_csv.py`: 同じ資産・月のCSV再取り込みが更新になること
- `tests/test_generate_asset_snapshots.py`: 実測スナップショットを生成値より優先すること
- `tests/test_repair_asset_snapshot_duplicates.py`: 正規化名の重複を統合し、優先順位に従って修復すること

## スキーマ初期化と移行

`init_db` は `CREATE TABLE IF NOT EXISTS` と列・制約値の確認を用いて、既存DBを削除せずに必要なテーブル・列・インデックスを追加します。既存の制約値を広げる必要があるテーブルだけは、一時テーブルへのコピー後に置き換えます。初期カテゴリ・口座・分類ルールは `INSERT OR IGNORE` で投入するため、既存データを上書きしません。

この方針は既存DBを破棄しないことを目的とします。DB操作前にはバックアップを取り、実データはリポジトリやCIへ渡しません。
