# UX Automation 現行フロー棚卸し

Issue #11 の P1-A に向けた初回の現行実装棚卸しです。既存providerとserviceを再利用するため、起動時自動更新の実装前に責務と安全境界を固定します。

## 現在の利用フロー

1. `app.py` 起動時にSQLiteを初期化し、保存済み銘柄・決算・ニュース・適時開示・スコアを読み込む。
2. 外部取得は起動時には実行せず、設定ページの「無料データを手動で一括更新」から `scripts/run_daily_update.py` を呼び出す。
3. 一括更新はRSS/Atomニュース、決算候補、EDINET書類メタデータ、企業情報候補、確認済み決算候補の整理を独立実行する。
4. 各処理の結果は`automation_runs`と`automation_run_steps`へ保存し、部分失敗後も後続stepを継続する。
5. 候補取得は正式な決算・銘柄情報を自動上書きせず、設定ページで人間が確認する。

## 再利用する既存部品

| 目的 | 既存部品 | 境界 |
|---|---|---|
| 実行履歴 | `services.automation.run_steps` | step単位の失敗継続と履歴保存 |
| ニュース | `services.automation_jobs.run_news_job` | 有効なRSS/Atomのみ、重複排除は既存service |
| 決算候補 | `services.automation_jobs.run_earnings_job` | 候補DBのみを更新、確定イベントは承認制 |
| EDINET | `services.edinet.run_edinet_range` | APIキー未設定は失敗として記録、API v2を再実装しない |
| 企業情報候補 | `services.stock_profiles.run_profile_refresh` | `stock_profile_candidates`へ保存、正式値は承認制 |
| 一括CLI | `scripts.run_daily_update.main` | provider構築、設定値解決、step順序を集約 |
| UI | `pages/6_設定.py` | 現在は手動ボタン、履歴と候補承認を表示 |

## P1-Aで解消する差分

- 起動時に外部取得を直列実行すると画面表示が長時間blockするため、実行方式と多重起動防止を先に決める。
- 起動時実行を追加しても、手動ボタン、dry-run、候補保護、低頻度制約を同じservice経由で維持する。
- 最終更新時刻、実行中、完了、部分失敗、失敗理由を1か所で表示する。
- 起動時に外部APIキーがない場合は、既存DBを変更せず、設定不備または部分失敗として表示する。

## 今回の結論

初回実装は、既存の`run_daily_update`が持つstep定義を共有可能な関数へ切り出し、CLIと起動時実行が同じオーケストレーションを呼ぶ形が最小です。UIの長時間blockを避ける実行方法と、起動時の自動実行を有効にする設定は別の小タスクとして検証します。
