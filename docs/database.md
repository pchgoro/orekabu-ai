# Database

## DBファイル場所

`data/orekabu.db`

個人データが入るためGit管理対象外。

## stocksテーブル

| カラム | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 内部ID |
| ticker | TEXT | NOT NULL UNIQUE | 銘柄コード |
| company_name | TEXT | NOT NULL | 会社名 |
| category | TEXT | NOT NULL | 保有株、監視銘柄、関連銘柄、その他 |
| is_holding | INTEGER | NOT NULL DEFAULT 0 | 保有株フラグ |
| shares | INTEGER | NOT NULL DEFAULT 0 | 保有株数 |
| average_price | REAL | NOT NULL DEFAULT 0 | 平均取得単価 |
| buy_watch_price | REAL | NOT NULL DEFAULT 0 | 買い検討価格 |
| memo | TEXT | NOT NULL DEFAULT '' | メモ |
| created_at | TEXT | NOT NULL | 作成日時 |
| updated_at | TEXT | NOT NULL | 更新日時 |

## app_settingsテーブル

| カラム | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| key | TEXT | PRIMARY KEY | 設定キー |
| value | TEXT | NOT NULL | JSONまたは文字列 |
| updated_at | TEXT | NOT NULL | 更新日時 |

## earnings_eventsテーブル

| カラム | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| id | INTEGER | PRIMARY KEY | 内部ID |
| stock_id | INTEGER | NOT NULL, stocks.id参照 | 対象銘柄 |
| fiscal_year | INTEGER | NOT NULL | 対象年度 |
| fiscal_quarter | TEXT | NOT NULL | Q1、Q2、Q3、通期、未設定 |
| earnings_date | TEXT | NULL可 | ISO形式の決算予定日 |
| announcement_time | TEXT | NOT NULL | 発表時間・時間帯 |
| date_status | TEXT | NOT NULL | 確定、予定、未確認 |
| memo | TEXT | NOT NULL | 確認メモ |
| created_at / updated_at | TEXT | NOT NULL | 作成・更新日時 |

`stock_id, fiscal_year, fiscal_quarter` は一意です。

## stock_relationsテーブル

`source_stock_id` は影響を受ける側、`related_stock_id` は影響を与える可能性がある側です。同一組み合わせは一意で、自己参照は禁止します。関係タイプ、影響度、メモ、作成・更新日時を保持します。

## schema_versionテーブル

現在のDBスキーマ番号を1行で保持します。Phase 2B候補取得対応のスキーマはversion 3です。

## earnings_candidatesテーブル

外部取得・CSV取込の候補を保存します。銘柄、取得元、参照情報、候補日、時刻、年度、四半期、信頼度、比較状態、確認状態、対応する正式イベント、取得・確認日時、確認メモ、取得要約を保持します。fingerprintのUNIQUE制約で同一候補の無制限な重複を防ぎます。

## earnings_fetch_runsテーブル

一回の取得開始・終了、対象件数、成功、候補作成、変更なし、失敗、実行状態、エラー要約を保持します。

## earnings_fetch_resultsテーブル

取得実行ごとの銘柄別結果、候補ID、エラーコード、エラー文、取得日時を保持します。

## 初期化方法

アプリ起動時に `services.database.init_db()` が実行される。テーブルは `CREATE TABLE IF NOT EXISTS` で作成されるため、複数回実行しても壊れない。

DBが空の場合のみ、以下のサンプル銘柄を登録する。

・5801.T 古河電気工業  
・6976.T 太陽誘電  
・4062.T イビデン

## バックアップ

アプリを終了してからコピーする。

```powershell
Copy-Item data\orekabu.db data\orekabu_backup.db
```

## 復元

アプリを終了し、バックアップを `data\orekabu.db` に戻す。

```powershell
Copy-Item data\orekabu_backup.db data\orekabu.db
```

## マイグレーション方針

`services/migrations.py` がversionを確認し、未適用の変更だけを実行します。version 3は既存テーブルをDROPせず、候補・取得履歴テーブルとインデックスを追加します。同じ処理を複数回実行しても重複作成されません。

## 破損時の注意

DB破損が疑われる場合は、アプリを停止し、バックアップから復元する。復元前に破損DBを別名で保存しておく。
