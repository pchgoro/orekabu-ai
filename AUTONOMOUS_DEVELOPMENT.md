# 自動開発運用

## 正本とブランチ

- GitHub `pchgoro/orekabu-ai`を唯一の正本とする。
- `main`を基準ブランチとし、作業は短命な`codex/<issue>-<description>`ブランチで行う。
- force push、履歴rewrite、未確認のfeature branch削除、実データDBの削除・初期化は禁止する。
- mainへ反映する変更は、対象テストが成功し、Critical/High regressionがないことを確認する。

## 1回の実行

定期実行は毎回、最新のGitHub main、open PR、open issue、`EXECUTION_TASK.json`、`ROADMAP.md`を確認する。その後、blockerとhuman actionを確認し、実行可能な最優先issueを1件だけ選ぶ。実装、テスト、レビュー、コミット、push、issue/PRと`EXECUTION_TASK.json`の更新を1単位として扱う。

実APIキー、有料API、本番API、Windowsタスクスケジューラへの実登録、実データの承認は人間確認が必要な境界として記録する。無料で進められる設計、mock、local実装、テスト、ドキュメントは独立して進めてよい。

## 候補と正式版

Candidateは、コードと通常テストが存在しても、実データ、実画面、外部通信、運用受入れが未確認なら正式版へ昇格しない。テスト成功だけで実運用のPASSを主張しない。

## idle停止

実行可能なissue、PR、または独立した作業がない場合は`consecutive_idle_checks`を1増やす。作業を開始または完了したら0へ戻す。5回連続でidleなら`enabled=false`へ変更し、停止理由と最終確認時刻をGitHubへ記録する。停止後はコード変更を行わない。
