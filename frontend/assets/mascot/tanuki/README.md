# Tanuki Mascot Assets for mfblue-local-budget

このZIPは、家計簿フロントに入れるための「たぬき風マスコット」案の切り出し素材です。

## 置き場所のおすすめ

リポジトリ内では、画像をここに置くのが自然です。

```text
frontend/assets/mascot/tanuki/
```

例:

```text
frontend/
  assets/
    mascot/
      tanuki/
        tanuki_main_full.png
        tanuki_thinking.png
        tanuki_happy_pouch.png
        tanuki_mail_wink.png
        tanuki_cheer.png
        tanuki_icon_128.png
        tanuki_icon_256.png
```

## 入れる場所のおすすめ

### 1. 月次分析・年間分析カードのヘッダー
最優先。分析が「キャラクターが言っている感じ」になりやすいです。

推奨ファイル:
- `tanuki_cheer.png`
- `tanuki_thinking.png`

表示イメージ:
```text
[たぬきアイコン] 今月のチェックポイント
```

### 2. 分析結果が未作成の空状態
「まだ分析されていません」の横に置くと、空白が寂しくなりません。

推奨ファイル:
- `tanuki_thinking.png`

### 3. stale分析の注意表示
「前回分析を表示中です」の横に、小さく入れると意味が伝わりやすいです。

推奨ファイル:
- `tanuki_mail_wink.png`

### 4. カテゴリ変更モーダル
中分類チップの近くに大きく入れると邪魔なので、入れるなら右上に小さく。

推奨ファイル:
- `tanuki_icon_128.png`

## 入れすぎ注意

画面の常時表示部分には1〜2箇所で十分です。
おすすめは「分析カードヘッダー」と「空状態」だけです。

## ファイル一覧

- `source/finance_fox_mascot_concept_sheet.png`: 元のコンセプトシート
- `png/tanuki_main_full.png`: メイン全身
- `png/tanuki_thinking.png`: 考え中
- `png/tanuki_happy_pouch.png`: 財布/貯金っぽい表情
- `png/tanuki_mail_wink.png`: お知らせ/前回分析向き
- `png/tanuki_cheer.png`: 分析完了/おすすめ向き
- `png/tanuki_icon_128.png`, `png/tanuki_icon_256.png`, `png/tanuki_icon_512.png`: アイコン
- `webp/`: Web向け軽量版
