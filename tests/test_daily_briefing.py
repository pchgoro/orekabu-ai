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
    assert [task["priority"] for task in tasks] == [1,2,3,4,5]
    assert len(tasks) == 5


def test_empty_briefing_and_tasks_are_safe() -> None:
    items = build_briefing([], [], [], [], [], {}, 0)
    assert all(item["count"] == 0 for item in items)
    assert build_daily_tasks([], [], [], [], [], 0) == []
