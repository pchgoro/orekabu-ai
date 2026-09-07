from services.notification_candidates import build_notification_candidates


def test_notification_candidates_are_explainable_and_non_actionable() -> None:
    rows = build_notification_candidates(
        buy_watch_rows=[{"ticker": "5801.T", "company_name": "古河", "buy_watch_status": "到達"}],
        earnings_rows=[{"ticker": "6976.T", "company_name": "太陽", "days_until": 2}],
        score_rows=[
            {"ticker": "4062.T", "company_name": "イビデン", "volume_ratio": 2.5, "score": 70, "prev_score": 55},
        ],
    )
    assert [(row["kind"], row["ticker"]) for row in rows] == [
        ("buy_watch", "5801.T"),
        ("earnings", "6976.T"),
        ("volume", "4062.T"),
        ("score", "4062.T"),
    ]
    assert all("dedupe_key" in row and "reason" in row for row in rows)
    assert not any("注文" in row["title"] or "推奨" in row["title"] for row in rows)


def test_notification_candidates_ignore_below_threshold_and_missing_ticker() -> None:
    rows = build_notification_candidates(
        score_rows=[
            {"company_name": "コードなし", "volume_ratio": 9},
            {"ticker": "5801.T", "volume_ratio": 1.9, "score": 60, "prev_score": 55},
        ]
    )
    assert rows == []
