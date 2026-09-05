## AI-Knowledge

作業開始時:
- C:/Users/goroo/Desktop/Project/AI-Knowledge/INDEX.md を確認する。
- 今回のタスクに直接関係するKnowledgeだけ参照する。

作業終了時:
- 今回の作業で再利用価値のある知見が得られたか評価する。
- 過去の失敗の再発防止、重要な設計判断、高コストな調査結果、再利用可能なパターンだけをKnowledge化する。
- 既存Knowledgeがあれば新規作成より更新を優先する。
- プロジェクト固有知識は projects/<project>/ へ保存する。
- 他プロジェクトにも適用できそうだが未確認の知見は candidates/ へ保存する。
- 単なる変更履歴や一時的な作業内容は保存しない。
- global Ruleへ勝手に昇格しない。

## 作業終了時Knowledge Capture

再発防止、設計理由、高コストな調査結果、再利用可能なパターン、重要なテスト挙動だけを `.ai-knowledge-outbox/` にMarkdownで保存する。単なる変更履歴、一時メモ、trivialな修正、secrets、APIキー、個人情報、`.env`内容は保存しない。ファイル名には日時または一意な識別子を含める。Knowledgeには `project`, `type`, `title`, `observed_at`, `problem`, `cause`, `resolution`, `reusable_lesson`, `evidence`, `cross_project_candidate` を含める。

## ChatGPT Web High 自動委任ルール

共通ルールは [AI-Knowledge/templates/AGENTS.md](../AI-Knowledge/templates/AGENTS.md) に従う。通常実装、ファイル編集、テスト、軽微な修正、単純な調査は親Codexが担当し、高度な設計・分析・レビューなど必要な場合のみ、native subagent `multi_agent_v1__spawn_agent` から `model: chatgpt-web/high` を指定して委任する。

Web Highには目的、必要なコンテキスト、対象ファイル、制約、確認観点を明示し、回答を実リポジトリと照合してから採用する。ファイル編集、コマンド実行、テストは親Codexが担当する。`chatgpt-delegate`、Chrome bridge、Skill経由、`create_thread`系、直接CLIによる呼び出しは使用しない。同じ問題の不要な再委任を繰り返さず、重要実装後は必要に応じてCritical / High相当の指摘をレビューする。

目的は、通常の実装では親Codex側のクォータ消費を抑え、高度な設計・分析・レビューだけをChatGPT Web — Highへnative subagentとして委任することである。

1. 通常の実装、ファイル編集、テスト、軽微な修正、単純な調査は親のCodexモデル自身で行う。
2. 次の場合のみ、Codex native subagent機能を使用して `chatgpt-web/high`（ChatGPT Web — High）へ委任する。
   - 新規アーキテクチャや重要な設計判断
   - 複数モジュールにまたがる大規模変更
   - 原因特定が難しいバグ
   - 複数の実装案から重要な選択を行う場合
   - 大規模リファクタリング
   - セキュリティ・データ破損・後方互換性に関わる判断
   - 実装後の重要なコードレビュー
   - 親モデル自身の判断に十分な確信がない場合
3. ChatGPT Web — Highの主な役割は、設計・推論・分析・レビューとする。
4. 原則として、実際のファイル編集、コマンド実行、テストは親のCodexモデルが担当する。
5. 軽微な作業ではChatGPT Web — Highを使用しない。
6. 同じ問題について不要な再委任を繰り返さない。
7. Web Highへ委任するときは、必要なコンテキスト、対象ファイル、目的、制約、確認観点を明確に渡す。
8. Web Highの回答を無条件に採用せず、親Codexが現在のリポジトリ状態と照合してから実装判断を行う。
9. 重要な実装完了後は必要に応じてWeb Highへdiffまたは変更内容のレビューを依頼し、Critical / High相当の指摘を優先して解消する。
10. `chatgpt-delegate` やChrome bridge方式は使用せず、native subagent + `chatgpt-web/high` を使用する。
