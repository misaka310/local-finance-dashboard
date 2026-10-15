# 読み取り専用HTMLエクスポート

Galaxyなどでオフライン閲覧するため、現在のローカルデータから単一HTMLを作成できます。

```powershell
.\scripts\12_export_readonly_html.ps1
```

生成物は `dist/readonly/mfblue_readonly.html` と `dist/readonly/mfblue_readonly.zip` です。ZIPを端末へ転送して展開し、HTMLをブラウザで開きます。

このHTMLは書き出し時点の固定データです。編集・同期・再分析はできません。内容を更新する場合はPCで再エクスポートします。生成物に実データが含まれるため、Git管理や公開アップロードはしません。
