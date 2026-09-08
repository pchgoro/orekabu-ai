# Trusted sourceの境界

`services.trusted_sources.build_trusted_source_rows` は、既存のIR取得元設定を変更せず、明示承認の有無だけを表示用に判定します。

`stock_id + source_type + 正規化URL` が一致し、承認レコードに `approved=true` がある場合だけtrustedです。取得成功回数、URLの存在、ユーザーの過去操作などから暗黙にtrustedへ昇格しません。承認情報の永続化は、後方互換な設計とユーザー確認を経て別タスクで行います。

永続化する場合も、`normalize_trusted_source_approval` の契約を通し、承認者を暗黙補完せず、`approved=false` を同じキーへ保存して解除可能にします。既存の `stock_ir_sources` 行を上書きせず、migrationとUI承認を別の小さい変更として検証します。

`build_trusted_source_review_rows` はUIに「明示承認」「承認を解除」を表示するための契約だけを提供し、押下処理や保存は行いません。永続化前の段階で、承認操作を自動実行しない境界を固定します。
