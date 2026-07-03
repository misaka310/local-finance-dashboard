# 設計メモ

## 目的

PayPayカード利用通知メールから支出を取り込み、月別・カテゴリ別に「今月何に使ったか」を見る。

マネーフォワードMEの基本構造を参考に、次の形に寄せています。

```text
月選択
  → 支出
    → カテゴリ別合計
      → カテゴリを押す
        → 明細一覧
```

## データモデル

### transactions

カード利用や支出1件を表します。

- `source_id`: 取得元。例: `paypay-card`
- `account_id`: 支払い元。例: `paypay-card`
- `external_id`: Gmail message id
- `direction`: `expense` / `income`
- `occurred_at`: 利用日
- `merchant`: 店名
- `amount_yen`: 金額
- `category_id`: 大項目
- `subcategory`: 中項目

### categories / subcategories

大項目は固定、中項目は追加可能という扱いです。

### category_rules

店名や明細文言からカテゴリを決めるルールです。

例:

```text
セブン → 食費 / コンビニ
Spotify → 趣味・娯楽 / サブスク
```

UIでカテゴリを手動変更した場合、同じ店名を次回から同じカテゴリにするルールを追加できます。

## 後から別カードを増やす前提

明細は `source_id` と `account_id` を持っているため、次のように増やせます。

- `paypay-card`
- `smbc-card`
- `rakuten-card`
- `amazon`

ただし、メール本文の形式がカード会社ごとに違うため、パーサーはソースごとに追加する必要があります。

## UI

- PCブラウザで起動
- 表示幅はスマホアプリ風
- 青系アクセント
- 月別支出、円グラフ、カテゴリ一覧、明細一覧、カテゴリ修正を実装
