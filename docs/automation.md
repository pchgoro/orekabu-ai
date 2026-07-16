# 無料取得自動化

## 目的

毎日のRSS、決算日候補、EDINET書類メタデータ、企業情報候補の取得をローカルPCでまとめて実行します。有料API、AI API、クラウドサービスは使用しません。

## CLI

- `scripts/fetch_news.py`: 登録済みの有効なRSS・Atomソース
- `scripts/fetch_earnings.py`: yfinanceの決算日候補
- `scripts/fetch_edinet.py`: EDINET公式API v2の書類メタデータ
- `scripts/refresh_stock_profiles.py`: yfinanceの企業情報候補
- `scripts/run_daily_update.py`: 上記と古い確認済み決算候補整理の一括実行
- `scripts/run_edinet_backfill.py`: EDINET初回バックフィル

共通オプションは`--dry-run`、`--ticker`、`--limit`、`--force`、`--verbose`です。

## データ保護

- 決算日は`earnings_candidates`へ保存し、`earnings_events`を更新しない
- 企業情報は`stock_profile_candidates`へ保存し、`stocks`を更新しない
- EDINETは`docID`で重複排除する
- RSSは既存のdeduplication_keyで重複排除する
- dry-runはDBと実行履歴を変更しない
- 1件・1ステップの失敗後も残りを継続する

## 企業情報候補の確認

設定画面では候補取得時の値と現在の`stocks`を並べて表示します。

- 選択項目を承認
- 候補値がある全項目を承認
- 保留
- 却下

承認対象は会社名、略称、市場、業種です。承認時は銘柄更新と候補状態更新を同じSQLiteトランザクションで実行し、途中で失敗した場合は両方をロールバックします。保留と却下では銘柄情報を変更しません。

## 日次処理順

1. RSS
2. 決算候補
3. EDINET
4. 企業情報候補
5. 古い確認済み決算候補の整理

## EDINET推奨運用

- 毎日: `run_edinet_daily.bat`で直近3日
- 月1回: `python scripts/fetch_edinet.py --preset monthly`で直近30日
- 初回のみ: `run_edinet_backfill.bat`で直近90日

日数と最大保存件数は設定画面から変更できます。初期値は日次3日、月次30日、初回90日、最大20件です。CLIで日数または`--limit`を明示した場合はCLI値を優先します。

## Windows

`run_daily_update.bat`は全取得処理、`run_edinet_daily.bat`はEDINET日次取得、`run_edinet_backfill.bat`は初回バックフィルを実行します。タスクスケジューラへの登録は利用者が行い、アプリは勝手に登録しません。

## 終了コード

- `0`: 全処理成功
- `1`: 一部失敗または実行失敗
- `2`: 引数、登録銘柄、APIキー等の設定不備

## 画面

設定画面には最終一括実行、各ステップの明細、新着EDINET数、未確認決算候補数、企業情報候補数、手動一括更新を表示します。EDINET APIキーは設定済みかどうかだけを表示し、値は表示しません。

## 制限

PC停止中の再実行、休日分の自動遡及、通知、常駐処理は行いません。外部サービスの仕様・利用制限に従い、低頻度で実行してください。
