# EDINET連携

## 利用範囲

金融庁の公式EDINET API v2だけを使用します。APIキーは`.env`の`EDINET_API_KEY`から読み込み、ログやGitへ保存しません。

## 対象

登録銘柄の証券コードとEDINETの`secCode`を照合し、次の書類メタデータを保存します。

- 有価証券報告書
- 半期報告書
- 臨時報告書
- 大量保有報告書
- 訂正書類

## 保存項目

- docID
- EDINETコード
- 証券コード
- 提出者
- 書類種別
- 提出日時
- description
- 公式参照URL
- 取得日時

本文、PDF、XBRL、AI要約は保存・解析しません。`docID`のUNIQUE制約で再実行時の重複を防ぎます。

## 日付指定

1日だけ確認する場合:

```powershell
python scripts\fetch_edinet.py --date 2026-07-16 --limit 20
```

日本時間の今日を含む直近N日を確認する場合:

```powershell
python scripts\fetch_edinet.py --ticker 5801.T --lookback-days 90 --dry-run --limit 20 --verbose
```

`--date`と`--lookback-days`は同時指定できません。lookbackは1〜365日で、今日から過去へ1日ずつ取得します。tickerに一致する書類が見つかっても期間の残りを確認し、日付間には待機を入れます。verboseでは日付ごとのAPI取得件数、ticker照合件数、対象書類件数を表示します。

## 運用設定

設定ページで次を変更できます。

- `edinet_daily_lookback_days`: 1〜30、初期値3
- `edinet_monthly_lookback_days`: 1〜365、初期値30
- `edinet_initial_backfill_days`: 1〜365、初期値90
- `edinet_fetch_limit`: 1〜500、初期値20

日次一括処理と`run_edinet_daily.bat`は日次設定、`--preset monthly`は月次設定、`run_edinet_backfill.py`と`run_edinet_backfill.bat`は初回設定を使用します。CLIで日数やlimitを指定した場合はCLI値が優先されます。

verboseでは、使用日数、処理上限、設定由来かCLI指定か、API取得件数、ticker一致件数、保存件数、重複件数、失敗件数を表示します。

証券コードは日本株の数字4桁だけをEDINETの数字5桁`secCode`先頭4桁と照合します。例えば`5801.T`と`5801`は`58010`に一致します。`285A.T`のような英字コードや、欠損・形式不正の`secCode`は安全にスキップします。

## エラー処理

APIキーなし、HTTP失敗、JSON不正、書類保存失敗をログへ記録します。書類単位の保存失敗は`edinet_fetch_results`へ失敗明細を残し、他の書類を継続します。日次一括処理ではEDINETが失敗しても他の処理を続けます。APIキー自体は画面、ログ、報告へ出力しません。

## 実通信確認

通常のpytestはEDINETへ接続しません。`.env`にAPIキーがある場合だけ、次のintegrationテストが一時DBを使って最大5件のdry-runを行います。

```powershell
pytest -q -m integration
```

APIキー未設定時はEDINET実通信テストをskipします。

## 制限

現在は指定日1日分を取得します。休日やPC停止日に提出された書類の自動遡及、本文検索、XBRL数値抽出、TDnet・EDINET間の自動関連付けは未実装です。
