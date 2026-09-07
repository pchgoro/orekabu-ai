from services.event_grouping import group_material_records, material_group_key


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
