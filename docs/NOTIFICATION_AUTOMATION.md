# 通知自動化の安全な境界

`services.notification_candidates.build_notification_candidates` は、既存の買い検討ライン、決算接近、出来高倍率、スコア履歴から説明可能な通知候補を作るだけの純粋なview modelである。外部送信、DB保存、売買注文、投資判断は行わない。

候補には銘柄、種別、理由、重複抑制キー、優先度を含める。Windows通知やDiscord送信は別adapterとして設計し、送信先、Webhook、通知頻度、重複抑制の人間確認が済むまで実行しない。実データ・実送信・有料サービスはHuman Actionとして残す。
