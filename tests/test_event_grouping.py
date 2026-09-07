from services.event_grouping import build_event_display_groups, collapse_news_rows, group_material_records, material_group_key


def test_group_material_records_keeps_cross_source_provenance() -> None:
    records = [
        {"id": 1, "source": "RSS", "ticker": "5801.T", "title": "決算短信 発表", "published_at": "2026-09-07T08:00:00+09:00", "url": "https://rss.example/item"},
        {"id": 2, "source_name": "EDINET", "ticker": "5801.T", "title": "決算短信 発表", "disclosed_at": "2026-09-07T15:00:00+09:00", "document_url": "https://edinet.example/doc"},
    ]
    groups = group_material_records(records)
    assert len(groups) == 1
    assert groups[0]["source_count"] == 2
    assert [item["record_id"] for item in groups[0]["provenance"]] == [1, 2]
    assert len(groups[0]["records"]) == 2


def test_material_group_key_changes_for_different_ticker_or_date() -> None:
    base = {"ticker": "5801.T", "title": "決算短信", "event_date": "2026-09-07"}
    assert material_group_key(base) == material_group_key({**base, "url": "https://different.example"})
    assert material_group_key(base) != material_group_key({**base, "ticker": "6976.T"})
    assert material_group_key(base) != material_group_key({**base, "event_date": "2026-09-08"})


def test_ambiguous_or_retrieval_only_dates_are_not_auto_grouped() -> None:
    records = [
        {"id": 1, "ticker": "5801.T", "title": "同じ題名", "retrieved_at": "2026-09-07T10:00:00"},
        {"id": 2, "ticker": "5801.T", "title": "同じ題名", "retrieved_at": "2026-09-07T10:01:00"},
        {"id": 3, "ticker": "5801.T", "title": "不正日付", "event_date": "not-a-date"},
    ]
    assert material_group_key(records[0]) == ""
    groups = group_material_records(records)
    assert len(groups) == 3
    assert all(len(group["records"]) == 1 for group in groups)


def test_display_adapter_preserves_state_without_mutating_records() -> None:
    records = [
        {"id": 1, "ticker": "5801.T", "title": "決算", "event_date": "2026-09-07", "importance": "通常", "is_read": 1, "is_favorite": 0},
        {"id": 2, "ticker": "5801.T", "title": "決算", "event_date": "2026-09-07", "importance": "高", "is_read": 0, "is_favorite": 1},
    ]
    rows = build_event_display_groups(records)
    assert rows[0]["record_count"] == 2
    assert rows[0]["importance"] == "高"
    assert rows[0]["is_read"] is False and rows[0]["is_favorite"] is True
    assert [item["id"] for item in rows[0]["records"]] == [1, 2]


def test_news_collapse_keeps_editable_representative_and_provenance() -> None:
    rows = collapse_news_rows([
        {"id": 1, "ticker": "5801.T", "title": "決算", "published_at": "2026-09-07", "url": "https://a.example"},
        {"id": 2, "ticker": "5801.T", "title": "決算", "published_at": "2026-09-07", "url": "https://b.example"},
    ])
    assert rows[0]["id"] == 1
    assert rows[0]["event_record_count"] == 2
    assert [entry["record_id"] for entry in rows[0]["event_provenance"]] == [1, 2]
