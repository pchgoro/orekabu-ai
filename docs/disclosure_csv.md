# 適時開示CSV

## 文字コード

エクスポートはUTF-8 BOM付きです。日本語版Excelで開きやすい形式ですが、正式版判定前に実環境で確認してください。

## 列

```text
ticker,disclosure_type,title,disclosed_at,source_name,source_url,document_url,summary,importance,tags,memo,external_id
```

- `ticker`: 登録済み銘柄。`.T`なしは正規化されます
- `disclosure_type`: 定義済み開示種別
- `disclosed_at`: ISO形式の日時
- `importance`: 高、通常、低
- `tags`: カンマ区切り
- `external_id`: 取得元で一意なID。任意

## インポート

実行前にプレビューし、各行を独立して処理します。不正行は行番号と理由を表示し、他の行は継続します。重複時は更新またはスキップを選択します。結果は`disclosure_import_runs`と`disclosure_import_results`へ記録されます。

ローカルPDFのパスはCSV対象外です。信頼できないCSVからローカルファイルを参照させないためです。
