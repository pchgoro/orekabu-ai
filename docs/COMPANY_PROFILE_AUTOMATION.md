# 企業カルテ自動充填の現状

## 既存のデータ境界

| 項目 | 既存実装 | 自動処理の扱い |
| --- | --- | --- |
| 会社名・略称・市場・業種 | `services.stock_profiles` の yfinance候補 | `stock_profile_candidates` に保存し、承認前は `stocks` を変更しない |
| 株価 | `services.stock_data` | 企業カルテ表示時に取得・整形。売買注文は扱わない |
| 決算 | `earnings` / `earnings_candidates` | 候補・確定・履歴を既存の状態で表示 |
| ニュース | `services.news` | 登録銘柄のニュースと分類候補を表示。手動メタデータを上書きしない |
| 適時開示 | `services.disclosures` | 手動/公式IRニュース候補を重複排除して表示。実ページ確認は未完了 |
| EDINET | `services.edinet` | 既存の書類メタデータを表示。APIキーと実通信は人間確認境界 |
| 関連銘柄 | `services.relations` | 既存の関連付けと候補を表示 |

## 安全な統合境界

`services.company_profile.build_company_profile` が上記データを企業カルテ用の単一view modelへ集約する。自動取得は候補テーブルまたは既存の候補保存処理までとし、確定データへの反映は既存の明示承認処理を通す。企業名・市場・業種などを取得結果で無条件に上書きしない。

次の実装単位は、既存の候補/承認処理を再実装せず、候補の取得時刻・取得元・確認状態を企業カルテ上で追跡できる表示と受け入れテストに限定する。Desktop/Mobile実画面、本番データ、外部API実通信は別の受け入れ境界として残す。

## 受け入れ境界

- 自動テスト: 候補の取得元・取得時刻・`pending` 状態をview modelへ渡し、Desktop/Mobile優先レイアウトの双方で「企業情報候補」セクションが例外なく描画されることを確認する。
- Human Action: 実データで候補値が妥当か、Desktop実画面と390px相当のMobile実画面で折り返し・操作性に問題がないかを確認する。
- 自動承認は行わない。候補の確定は設定画面の明示承認に限定する。

## 現在の証跡

- ローカル自動テスト: `274 passed, 2 deselected`。
- 企業カルテ/設定画面: 候補表示、承認、保留、却下、候補値による確定データ非上書きをfixtureで確認済み。
- 未確認: 本番yfinance/IR/EDINETデータの妥当性、実Desktop表示、実機390px表示。これらはPASS扱いにせずHuman Actionとして残す。
