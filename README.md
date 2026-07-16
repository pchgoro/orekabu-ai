# オレ株AI

現在の正式バージョン：v0.4.0

Phase 3Aニュース基盤と毎日のUX改善をv0.4.0として収録しています。

Phase 3B適時開示基盤はv0.5.0候補として開発中です。正式版には確定していません。

Phase 4A企業カルテはv0.6.0候補として開発中です。正式版には確定していません。

オレ株AIは、個人利用専用の日本株分析ツールです。売買判断を自動化するものではなく、保有株と監視銘柄について「今日どれを確認するべきか」を短時間で把握するために使います。

## できること

- RSS・Atom、手動入力、CSVからニュースのメタデータを取り込む
- 記事の未読・お気に入り・タグ・重要度・カテゴリ・メモを管理する
- ticker、会社名、登録キーワードから関連銘柄候補を作り、手動承認する
- ニュース分析用プロンプトを生成する（AI APIは呼び出しません）

- 保有株、監視銘柄、買い検討価格の管理
- yfinanceによる日本株の日足取得
- 評価額、評価損益、RSI、MACD、移動平均、出来高倍率、下落率の表示
- 説明可能なルールベースの注目スコア
- Plotlyチャート
- CSV入出力
- ChatGPTへ手動で貼り付ける分析用プロンプト生成
- SQLite保存とログ出力
- Windows用batによる起動
- 決算日の手動登録、決算までの日数、月別決算カレンダー
- 方向を明示した関連銘柄管理と関連企業の決算予定表示
- 決算・関連銘柄CSV入出力
- yfinanceからの決算予定日候補取得と変更検知
- 候補の承認、保留、却下と取得履歴

## できないこと

- ニュース本文全文の保存、AI自動要約、重要度の自動判定
- TDnet、EDINET、PR TIMESとの自動連携

## ニュース管理

サイドバーの「ニュース」で、RSS/Atomソース、銘柄別キーワード、手動記事を登録できます。RSS取得は「ソース管理」タブで利用者が明示的に実行します。記事にはRSSが配信する要約だけを保存し、リンク先の本文は取得しません。

銘柄コード、会社名、登録キーワードがタイトルまたはRSS要約に含まれると、未承認の関連銘柄候補を作成します。候補は記事詳細で確認し、必要なものだけ手動承認してください。一致は関連性や株価への影響を保証しません。

記事・ソース・キーワードCSVはUTF-8 BOM付きです。列は次の通りです。

```text
title,url,published_at,source,author,summary,importance,category,memo
name,source_type,url,is_enabled,memo
ticker,keyword,is_enabled
```

## 適時開示管理

サイドバーの「適時開示」で、登録済み銘柄の開示メタデータを手動またはCSVで整理できます。TDnetの自動巡回、有料API、PDF本文解析、AI要約は行いません。PDFはDBへ保存せず、公開HTTP(S) URLまたは`data\disclosures`配下のローカルファイルパスだけを保持します。ローカルPDFは10MB以下に制限されます。

開示には既読、お気に入り、重要度、タグ、メモを設定できます。ニュースとの関連候補はURLまたはタイトル一致で作成されますが、自動確定されません。ChatGPT分析用プロンプトはコピー用テキストのみを生成し、AI APIは呼び出しません。

開示CSVはUTF-8 BOM付きで、次の列を使用します。不正行があっても他の行は継続し、重複は更新またはスキップできます。

```text
ticker,disclosure_type,title,disclosed_at,source_name,source_url,document_url,summary,importance,tags,memo,external_id
```

## 企業カルテ

サイドバーの「企業カルテ」では、登録銘柄をticker、会社名、略称で検索し、株価、決算、ニュース、適時開示、関連銘柄、統合タイムラインを1ページで確認できます。市場、業種、略称は「企業情報を編集」から任意登録します。

ニュースは承認済みの銘柄関連だけを表示します。株価は既存のyfinance取得と注目スコアを利用し、取得失敗時も他のカルテ情報は表示します。ChatGPT分析用プロンプトはコピー用テキストのみで、AI APIは呼び出しません。

設定の「モバイル優先表示」が有効な場合は縦構成、無効時はPC向けの2〜3列構成です。

## 今日のブリーフィング

トップ画面の最初に、直近決算、未確認の決算候補、ニュース、買い検討ライン、注目スコア、株価・RSS取得失敗をまとめて表示します。「今日やること」はルールで優先順位を付けた最大10件です。いずれも売買推奨ではなく、確認順序を整理する表示です。

設定画面でダッシュボードの標準・コンパクト、ニュースのカード・表、モバイル優先表示、表示件数、0件項目の非表示を変更できます。モバイル優先表示では、保有株・監視銘柄・決算・ニュースの横長表を主要情報カードへ切り替えます。

- 売買推奨や自動売買
- AI APIによる自動分析
- リアルタイム株価保証
- 投資成果の保証
- 決算日の無確認自動更新、ニュース、通知、AI APIによる自動分析

## 決算管理

サイドバーの「決算」から、登録済み銘柄の決算予定を手動登録します。対象年度、四半期、日付、発表時間、確定状態、確認メモを保存できます。決算予定日は企業発表により変更される可能性があるため、利用者が最新情報を確認して更新してください。本ツールは決算日を自動取得しません。

「関連銘柄」タブでは `影響を受ける銘柄 ← 関連銘柄` の方向で登録します。関連企業の決算が自分の銘柄へ影響することを断定する機能ではありません。

### 決算CSV

```text
ticker,fiscal_year,fiscal_quarter,earnings_date,announcement_time,date_status,memo
```

### 関連銘柄CSV

```text
source_ticker,related_ticker,relation_type,impact_level,memo
```

どちらもUTF-8 BOM付きで出力します。インポート前にプレビューし、不正な行は行番号と理由を表示して他の行を継続します。

## 決算日候補取得

決算管理ページの「決算日自動取得」タブから、個別銘柄または条件に合う銘柄の候補を取得します。外部から取得した日付は `earnings_candidates` に保存され、正式な決算イベントへ自動反映されません。

候補詳細で現在値と候補値を比較し、ユーザーが承認した場合だけ、新規登録または既存予定の更新を行います。手動登録データが優先され、確定データの更新には追加確認が必要です。保留・却下では正式データを変更しません。

yfinanceは候補日を返さない場合、過去日や複数日を返す場合、予定変更が反映されない場合があります。取得失敗は銘柄ごとに記録され、他銘柄の処理は継続します。表示内容は必ず企業の公式発表で確認してください。

候補CSVの列は以下です。このCSVも正式イベントへ直接登録されません。

```text
ticker,earnings_date,announcement_time,fiscal_year,fiscal_quarter,source_name,source_reference,confidence,memo
```

## 必要環境

- Windows PC
- Python 3.11以上
- インターネット接続（株価・決算候補取得時のみ）

## 初回起動方法

PowerShellで以下を実行します。

```powershell
cd C:\Users\goroo\Desktop\orekabu-ai
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

表示されたURLをブラウザで開きます。通常は `http://localhost:8501` です。

終了するときは、PowerShellで `Ctrl + C` を押してください。

## ダブルクリックで起動する方法

`start_orekabu_ai.bat` をダブルクリックすると、仮想環境の作成、必要ライブラリの確認、Streamlit起動まで実行します。

初回起動時はライブラリのインストールで時間がかかる場合があります。

## アプリ更新後の手順

すでに `.venv` が存在する場合は、PowerShellで以下を実行します。

```powershell
cd C:\Users\goroo\Desktop\orekabu-ai
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest -q
streamlit run app.py
```

`.venv` が存在しない場合は、初回起動方法と同じ手順で仮想環境を作成してください。

## 更新前のバックアップ

アプリ更新前にDBをバックアップしてください。`YYYYMMDD` は実際の日付に置き換えます。

```powershell
Copy-Item data\orekabu.db data\orekabu_backup_YYYYMMDD.db
```

例：

```powershell
Copy-Item data\orekabu.db data\orekabu_backup_20260710.db
```

DB更新時は起動時にマイグレーションが実行されます。初回起動前にアプリを終了し、必ず上記バックアップを作成してください。既存DBの削除は不要です。

## コード更新後に確認すること

- 起動できるか
- 登録銘柄が残っているか
- 保有株数と平均取得単価が正しいか
- 設定値が残っているか
- 株価取得できるか
- 注目スコアが表示されるか
- `logs\app.log` に重大エラーがないか

## テスト方法

すべての通常テストは環境変数でテストごとの一時SQLite DBへ切り替わり、`data\orekabu.db`を使用しません。yfinance実通信テストも通常テストから除外されます。

通常テスト：

```powershell
pytest -q
```

構文チェック：

```powershell
python -m compileall .
```

UIテスト：

```powershell
pytest -q tests/ui
```

StreamlitプロセスE2Eテスト：

```powershell
pytest -q tests/e2e
```

yfinance実通信テスト：

```powershell
pytest -q -m integration
```

Windowsでは`run_tests.bat`、`run_ui_tests.bat`、`run_e2e_tests.bat`をダブルクリックして実行できます。

Playwrightは導入していません。将来スクリーンショットを生成する場合の保存先は`artifacts\screenshots\`で、Git管理対象外です。現在残る手動確認は、日本語版Excelの実アプリ表示とDesktop・Tablet・Mobile幅での視覚的な崩れ確認です。

## Gitを使う場合の基本更新方法

このフォルダがGitリポジトリの場合のみ使います。未コミット変更がある状態で `git pull` を安易に実行しないでください。

```powershell
git status
git pull
pip install -r requirements.txt
pytest -q
streamlit run app.py
```

## CSVの使い方

設定ページから銘柄一覧をUTF-8 BOM付きCSVでエクスポートできます。インポート時の列は以下です。

```text
ticker,company_name,category,is_holding,shares,average_price,buy_watch_price,memo
```

既存tickerがある場合は、更新またはスキップを選択できます。不正な行があっても他の行の処理は続行します。

銘柄コードは `5801` のような数字4桁に加え、`285A` のような数字3桁＋英字1文字にも対応します。`.T`は入力時に自動付与されます。

## データ保存先

- DB: `data\orekabu.db`
- ログ: `logs\app.log`

## DBバックアップ

アプリを終了してからコピーします。

```powershell
Copy-Item data\orekabu.db data\orekabu_backup.db
```

復元する場合は、アプリ終了後にバックアップを `data\orekabu.db` へ戻します。

## よくあるエラー

- 株価データなし: ネットワーク、銘柄コード、yfinance側の状態を確認してください。
- ModuleNotFoundError: 仮想環境を有効化し、`pip install -r requirements.txt` を実行してください。
- DBエラー: アプリを複数プロセスで起動していないか確認してください。
- batの文字化け: `start_orekabu_ai.bat` はASCIIのみで作成しています。古いbatを開いている場合は閉じて再実行してください。

## 免責事項

本ツールは投資情報を整理するための個人用ツールです。表示内容や注目スコアは売買推奨ではありません。投資判断は必ずご自身の責任で行ってください。
