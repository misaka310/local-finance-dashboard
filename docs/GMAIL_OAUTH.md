# Gmail OAuth設定

## 必要なもの

- Googleアカウント
- Google Cloudプロジェクト
- Gmail APIの有効化
- OAuthクライアントJSON

## OAuthクライアント

作成するクライアントの種類は「デスクトップアプリ」です。

保存先:

```text
secrets\google_oauth_client.json
```

## スコープ

このアプリで使うスコープは次だけです。

```text
https://www.googleapis.com/auth/gmail.readonly
```

この権限では、メールの読み取りはできますが、送信・削除・ラベル変更はしません。

## トークン保存

`.\scripts\02_authorize_gmail.ps1` を実行するとブラウザ認証が走ります。
認証後のトークンはOSの資格情報保管領域に保存します。

削除する場合:

```powershell
.\scripts\06_reset_gmail_token.ps1
```
