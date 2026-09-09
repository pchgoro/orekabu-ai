# Trusted source承認の永続化とruntime利用

## 方針

既存の `stock_ir_sources` は取得元設定と取得状態を担うため、承認状態を上書きしない。trusted sourceは `stock_id + source_type + normalized_source_url` を論理キーとし、明示承認・解除の履歴を別管理する。

## 候補比較

| 候補 | 既存データ影響 | 解除 | 監査 | 採否 |
| --- | --- | --- | --- | --- |
| `stock_ir_sources`へ列追加 | migrationが必要、既存行の意味が変わる | 可能 | 列だけでは弱い | 採用しない |
| 承認テーブルを新設 | 既存行を変更しない | `approved=false`で可能 | approved_by / timestampを保持可能 | 採用候補 |
| JSON設定へ保存 | DBとの整合が弱い | 可能 | 競合・バックアップが弱い | 採用しない |

## 実装境界

schema v14で `trusted_source_approval_events` を追加した。既存の `stock_ir_sources` は変更せず、`stock_id + source_type + normalized_source_url` ごとのappend-onlyイベントから最新状態を読む。承認者は必須で、approve/revokeはSettingsのactor入力と確認チェックを通した明示操作だけが行う。同一状態の再操作はidempotent、解除は物理削除しない。

公式IRニュース自動取得jobは、現在の明示trusted状態とsourceの正規化URLが一致する場合だけ自動取得する。未承認・revoke・URL変更・別ticker・別source_typeは自動取得せず、Settingsでの確認待ちとして残す。既存のIR取得設定、候補、ニュース、開示、ユーザーデータは変更しない。
