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


def test_empty_briefing_and_tasks_are_safe() -> None:
    items = build_briefing([], [], [], [], [], {}, 0)
    assert all(item["count"] == 0 for item in items)
    assert build_daily_tasks([], [], [], [], [], 0) == []
