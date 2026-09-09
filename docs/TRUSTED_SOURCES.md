# Trusted sourceの境界

`services.trusted_sources.build_trusted_source_rows` は、既存のIR取得元設定を変更せず、明示承認の有無だけを表示用に判定します。

`stock_id + source_type + 正規化URL` が一致し、承認レコードに `approved=true` がある場合だけtrustedです。取得成功回数、URLの存在、ユーザーの過去操作などから暗黙にtrustedへ昇格しません。schema v14のappend-only監査イベントへ明示承認・解除を保存します。

永続化する場合も、`normalize_trusted_source_approval` の契約を通し、承認者を暗黙補完せず、`approved=false` を同じキーへ保存して解除可能にします。既存の `stock_ir_sources` 行を上書きせず、migrationとUI承認を別の小さい変更として検証します。

`build_trusted_source_review_rows` はUI表示用の契約です。Settingsでactorと確認チェックを要求して明示approve/revokeを保存します。公式IRニュースの自動取得jobは、現在のlogical keyが明示trustedの取得元だけを自動対象にし、未承認・解除・URL変更・別ticker・別source_typeは確認待ちとしてスキップします。
