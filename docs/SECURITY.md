# セキュリティ方針

## このアプリで扱う情報

保存するのは原則として次だけです。

- 利用日
- 店名
- 金額
- 支払い元
- カテゴリ
- Gmail message id
- 取り込み日時

メール本文全文は保存しません。

## 認証情報

Gmail OAuthトークンは `keyring` 経由でOSの資格情報保管領域に保存します。
WindowsではWindows資格情報マネージャー相当の保存先が使われます。

リポジトリ内に保存してはいけないもの:

- `secrets/google_oauth_client.json`
- Gmail OAuthトークン
- `data/*.sqlite3`
- 実明細CSV/JSON
- `.env`

## Gmail権限

Gmail APIスコープは読み取り専用の `gmail.readonly` に固定します。
メール送信、ラベル変更、削除などはしません。

## ローカルHTTP境界

- UIサーバーは `127.0.0.1` または `localhost` だけにbindできます。`0.0.0.0`、LAN IP、外部IPは起動時に拒否します。
- 全HTTPリクエストで `Host` を検証し、起動中のローカルポートを指す `127.0.0.1` / `localhost` 以外は拒否します。
- `POST` / `PATCH` は `Content-Type: application/json` のみ受け付けます。
- ブラウザが `Origin` を送る `POST` / `PATCH` は、起動中の同一ローカルoriginだけを受け付けます。不正なoriginは副作用処理の前に拒否します。
- PowerShellなど同一PC上のネイティブクライアントは `Origin` を省略できます。
- LAN公開、ポートフォワード、リバースプロキシ、トンネル経由の公開はサポートしません。
- 静的ファイル配信は、`frontend/` 配下を先に列挙した信頼済みインデックスからURLパスを引く方式とし、HTTP入力からファイルシステムPathを組み立てません。
- 読み取り専用デモのHTMLテンプレートへ動的値を埋め込む場合は、属性値・本文ともHTMLエスケープを通します。

## やらないこと

- PayPayカードサイトへログインしない
- 銀行サイトへログインしない
- Web明細ページをスクレイピングしない
- GitHub ActionsにGmailトークンや明細DBを置かない
- Codexに実データやトークンを読ませない

## 事故を防ぐ設計

- `.gitignore` で `data/` と `secrets/` の実ファイルを除外
- `AGENTS.md` でエージェント用の禁止事項を固定
- DBにはメール本文全文を保存しない
- UIはループバックでだけ起動し、HTTP側でも `Host` / `Origin` / `Content-Type` を検証する
