# Trusted source承認の永続化設計（未適用）

## 方針

既存の `stock_ir_sources` は取得元設定と取得状態を担うため、承認状態を上書きしない。trusted sourceは `stock_id + source_type + normalized_source_url` を論理キーとし、明示承認・解除の履歴を別管理する。

## 候補比較

| 候補 | 既存データ影響 | 解除 | 監査 | 採否 |
| --- | --- | --- | --- | --- |
| `stock_ir_sources`へ列追加 | migrationが必要、既存行の意味が変わる | 可能 | 列だけでは弱い | 採用しない |
| 承認テーブルを新設 | 既存行を変更しない | `approved=false`で可能 | approved_by / timestampを保持可能 | 採用候補 |
| JSON設定へ保存 | DBとの整合が弱い | 可能 | 競合・バックアップが弱い | 採用しない |

## 実装境界

現時点ではmigration・書き込み・自動承認を行わない。`normalize_trusted_source_approval` と `build_trusted_source_review_rows` の契約で、必須キー・明示承認・解除可能性・承認者必須を検証する。

将来の実装では、既存DBをバックアップ可能な通常migrationとして承認テーブルを追加し、設定画面で人間が承認/解除したときだけ保存する。既存のIR取得設定、候補、ニュース、開示、ユーザーデータは変更しない。
