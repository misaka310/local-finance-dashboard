# 実装構成

機能追加時に関係のない巨大ファイルを編集しなくて済むよう、責務ごとに分割しています。

## フロントエンド

- `frontend/app-core.js`: 状態、共通定数、期間操作、APIクライアント、家計簿データ読み込み
- `frontend/app-budget.js`: 家計簿の集計・明細・カテゴリ編集UI
- `frontend/app-assets.js`: 資産集計、チャート、保有商品、基準価額更新UI
- `frontend/app-analysis.js`: 月次・年次分析の取得と表示
- `frontend/app-bootstrap.js`: 共通エスケープ処理、同期、イベント登録、初期起動
- `frontend/styles/base.css`: 共通レイアウトと家計簿UI
- `frontend/styles/assets.css`: 資産UI
- `frontend/styles/components.css`: 下部ナビ、ダイアログ、レスポンシブ調整

各JavaScriptは通常のscriptとして上記順で読み込みます。ES Modulesやビルド工程は追加せず、従来どおり静的ファイルのまま動作します。

## Pythonバックエンド

- `db_common.py`: DB接続、共通定数
- `db_schema.py`: SQLiteスキーマ作成とマイグレーション
- `db_budget.py`: 家計簿明細、カテゴリ、期間集計
- `db_assets.py`: 資産、取引、基準価額、スナップショット、成績集計
- `db.py`: 既存importを壊さない互換ファサード
- `api_routes.py`: GET・POST・PATCHのAPI処理
- `server.py`: HTTPサーバー、静的ファイル配信、起動処理

新規コードでは責務が明確な場合、`db.py`ではなく対応する`db_*`モジュールを直接編集します。既存コードの`from mfblue.db import ...`は互換性のため引き続き動作します。

## 変更時の確認

```powershell
python run_tests_with_path.py
node --check frontend/app-core.js
node --check frontend/app-assets.js
node --check frontend/app-budget.js
node --check frontend/app-analysis.js
node --check frontend/app-bootstrap.js
```

`run_tests_with_path.py`は失敗時に終了コード1を返すため、CIやエージェントからも成功・失敗を正しく判定できます。
