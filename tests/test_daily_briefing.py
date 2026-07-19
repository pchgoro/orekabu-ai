"""Daily briefing aggregation and priority tests."""

from services.daily_briefing import build_briefing, build_daily_tasks


def fixtures():
    stocks = [{"ticker":"A.T","company_name":"A","score":80,"data_status":"OK"},{"ticker":"B.T","company_name":"B","score":10,"data_status":"データなし"}]
    earnings = [{"ticker":"A.T","company_name":"A","days_until":0},{"ticker":"B.T","company_name":"B","days_until":3}]
    candidates = [{"ticker":"A.T","company_name":"A","review_status":"pending","comparison_status":"conflict"}]
    news = [{"title":"重要","is_read":0,"importance":"高","has_holding_match":1}]
    buy = [{"ticker":"B.T","company_name":"B","buy_watch_status":"到達"}]
    return stocks, earnings, candidates, news, buy


def test_briefing_aggregates_counts_and_missing_values() -> None:
    stocks, earnings, candidates, news, buy = fixtures()
    items = build_briefing(stocks, earnings, candidates, news, buy, {"today":1,"unread":1,"favorites":0}, 1)
    counts = {item["label"]: item["count"] for item in items}
    assert counts["本日決算"] == 1
    assert counts["競合候補"] == 1
    assert counts["株価取得失敗"] == 1
    assert counts["RSS取得失敗"] == 1


def test_daily_tasks_follow_documented_priority_and_limit() -> None:
    stocks, earnings, candidates, news, buy = fixtures()
    tasks = build_daily_tasks(stocks, earnings, candidates, news, buy, 1, limit=5)
    assert [task["priority"] for task in tasks] == [1, 2, 3, 5, 6]
    assert len(tasks) == 5


def test_daily_tasks_order_all_simultaneous_conditions() -> None:
    """Every rule must remain ordered even when input rows arrive out of order."""
    stocks = [{"ticker": "SCORE.T", "company_name": "Score", "score": 90}]
    earnings = [
        {"ticker": "SOON.T", "company_name": "Soon", "days_until": 3},
        {"ticker": "TODAY.T", "company_name": "Today", "days_until": 0},
    ]
    candidates = [
        {"id": 2, "ticker": "CHANGE.T", "review_status": "pending", "comparison_status": "date_changed"},
        {"id": 1, "ticker": "CONFLICT.T", "review_status": "pending", "comparison_status": "conflict"},
    ]
    buy_watch = [{"ticker": "BUY.T", "buy_watch_status": "到達"}]
    news = [
        {"id": 2, "title": "保有株ニュース", "is_read": 0, "importance": "通常", "has_holding_match": 1},
        {"id": 1, "title": "重要ニュース", "is_read": 0, "importance": "高", "has_holding_match": 0},
    ]

    tasks = build_daily_tasks(stocks, earnings, candidates, news, buy_watch, rss_failed_count=2, limit=10)

    assert [task["label"] for task in tasks] == [
        "本日決算",
        "決算まであと3日",
        "決算候補の競合",
        "決算日の変更候補",
        "買い検討ライン到達",
        "重要ニュースを確認",
        "保有株ニュースを確認",
        "注目スコア 90",
        "RSS取得失敗を確認",
    ]
    assert [task["priority"] for task in tasks] == list(range(1, 10))


def test_daily_tasks_keep_stable_order_within_same_priority() -> None:
    earnings = [
        {"ticker": "B.T", "days_until": 0},
        {"ticker": "A.T", "days_until": 0},
    ]
    tasks = build_daily_tasks([], earnings, [], [], [], limit=10)
    assert [task["detail"] for task in tasks] == ["B.T", "A.T"]


def test_daily_tasks_enforce_limit_and_handle_missing_values() -> None:
    stocks = [
        {"ticker": f"{index}.T", "company_name": None, "score": 70 + index}
        for index in range(12)
    ]
    tasks = build_daily_tasks(stocks, [{"days_until": None}], [{}], [{"title": None}], [{}], 0, limit=4)
    assert len(tasks) == 4
    assert all("None" not in task["detail"] for task in tasks)


def test_daily_tasks_suppress_duplicate_targets() -> None:
    news = [
        {"id": 10, "title": "同じ記事", "is_read": 0, "importance": "高", "has_holding_match": 1},
        {"id": 10, "title": "同じ記事", "is_read": 0, "importance": "高", "has_holding_match": 1},
    ]
    earnings = [
        {"id": 20, "ticker": "A.T", "days_until": 0},
        {"id": 20, "ticker": "A.T", "days_until": 0},
    ]
    tasks = build_daily_tasks([], earnings, [], news, [], limit=10)
    assert [task["label"] for task in tasks] == ["本日決算", "重要ニュースを確認"]


def test_disclosure_tasks_follow_existing_tasks_without_reordering_them() -> None:
    disclosures = [
        {"id": 4, "ticker": "D.T", "disclosure_type": "決算短信", "is_read": 0},
        {"id": 3, "ticker": "C.T", "disclosure_type": "配当修正", "is_read": 0},
        {"id": 2, "ticker": "B.T", "disclosure_type": "業績予想修正", "is_read": 0},
        {"id": 1, "ticker": "A.T", "disclosure_type": "その他", "importance": "高", "is_holding": 1, "is_read": 0},
    ]
    existing = [{"ticker": "S.T", "score": 80}]
    tasks = build_daily_tasks(existing, [], [], [], [], rss_failed_count=1, limit=10, disclosure_rows=disclosures)
    assert [task["label"] for task in tasks] == [
        "注目スコア 80", "RSS取得失敗を確認", "業績予想修正を確認", "配当修正を確認",
        "決算短信を確認", "保有株の重要開示を確認",
    ]
    assert [task["priority"] for task in tasks] == [8, 9, 10, 11, 12, 13]


def test_empty_briefing_and_tasks_are_safe() -> None:
    items = build_briefing([], [], [], [], [], {}, 0)
    assert all(item["count"] == 0 for item in items)
    assert build_daily_tasks([], [], [], [], [], 0) == []


def test_playbook_tasks_and_briefing_are_integrated_before_existing_rules() -> None:
    playbook_rows = [
        {
            "id": 1,
            "ticker": "STOP.T",
            "company_name": "Stop",
            "is_holding": 1,
            "playbook_evaluation": {
                "configured": True,
                "stop_loss_reached": True,
                "take_profit_reached": False,
                "stop_loss_near": False,
                "take_profit_near": False,
            },
        },
        {
            "id": 2,
            "ticker": "PROFIT.T",
            "company_name": "Profit",
            "is_holding": 1,
            "playbook_evaluation": {
                "configured": True,
                "stop_loss_reached": False,
                "take_profit_reached": True,
                "stop_loss_near": False,
                "take_profit_near": False,
            },
        },
        {
            "id": 3,
            "ticker": "NEAR.T",
            "company_name": "Near",
            "is_holding": 1,
            "playbook_evaluation": {
                "configured": True,
                "stop_loss_reached": False,
                "take_profit_reached": False,
                "stop_loss_near": False,
                "take_profit_near": True,
            },
        },
        {
            "id": 4,
            "ticker": "UNSET.T",
            "company_name": "Unset",
            "is_holding": 1,
            "playbook_evaluation": {
                "configured": False,
                "stop_loss_reached": False,
                "take_profit_reached": False,
                "stop_loss_near": False,
                "take_profit_near": False,
            },
        },
    ]
    tasks = build_daily_tasks(
        [], [], [], [], [], playbook_rows=playbook_rows, limit=10
    )
    assert [task["label"] for task in tasks] == [
        "損切りライン到達",
        "利確ライン到達",
        "利確まで5%以内",
        "投資ルール未設定",
    ]
    assert [task["ticker"] for task in tasks] == [
        "STOP.T", "PROFIT.T", "NEAR.T", "UNSET.T"
    ]
    items = build_briefing(
        [], [], [], [], [], {}, playbook_rows=playbook_rows
    )
    counts = {item["label"]: item["count"] for item in items}
    assert counts["損切りライン到達"] == 1
    assert counts["利確ライン到達"] == 1
    assert counts["利確まで5%以内"] == 1
    assert counts["投資ルール未設定"] == 1


def test_multiple_unset_playbooks_are_aggregated_into_one_task() -> None:
    playbook_rows = [
        {
            "id": index,
            "ticker": f"{index:04d}.T",
            "company_name": f"Company {index}",
            "is_holding": 1,
            "playbook_evaluation": {"configured": False},
        }
        for index in range(1, 4)
    ]

    tasks = build_daily_tasks(
        [], [], [], [], [], playbook_rows=playbook_rows, limit=10
    )

    assert tasks == [
        {
            "priority": 7,
            "label": "投資ルール未設定",
            "detail": "3銘柄",
            "page": "保有株",
            "ticker": "",
        }
    ]


def test_strategy_tasks_and_counts_use_fixed_priority() -> None:
    strategy_rows = [
        {
            "id": 1,
            "ticker": "STOP.T",
            "company_name": "Stop",
            "is_holding": 1,
            "strategy_rule_resolution": {"conflict": False},
            "strategy_lines": {"configured": True, "stop_loss_reached": True},
        },
        {
            "id": 2,
            "ticker": "TAKE.T",
            "company_name": "Take",
            "is_holding": 1,
            "strategy_rule_resolution": {"conflict": False},
            "strategy_lines": {"configured": True, "take_profit_reached": True},
        },
        {
            "id": 3,
            "ticker": "CONFLICT.T",
            "company_name": "Conflict",
            "is_holding": 1,
            "strategy_rule_resolution": {"conflict": True},
            "strategy_lines": {"configured": False},
        },
        {
            "id": 4,
            "ticker": "UNSET.T",
            "company_name": "Unset",
            "is_holding": 1,
            "strategy_rule_resolution": {"conflict": False},
            "strategy_lines": {"configured": False},
        },
    ]
    tasks = build_daily_tasks(
        [], [], [], [], [], strategy_rows=strategy_rows, limit=10
    )
    assert [task["label"] for task in tasks] == [
        "戦略損切ライン到達",
        "戦略利確ライン到達",
        "戦略ルール競合",
        "戦略ルール未設定",
    ]
    assert [task["priority"] for task in tasks] == [-8, -7, 0, 14]

    items = build_briefing(
        [], [], [], [], [], {}, strategy_rows=strategy_rows
    )
    counts = {item["label"]: item["count"] for item in items}
    assert counts["戦略損切到達"] == 1
    assert counts["戦略利確到達"] == 1
    assert counts["戦略ルール競合"] == 1
    assert counts["戦略ルール未設定"] == 1
