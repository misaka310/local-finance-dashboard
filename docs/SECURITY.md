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
- UIは `127.0.0.1` でだけ起動
