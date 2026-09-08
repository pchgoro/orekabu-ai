from services.trusted_sources import build_trusted_source_rows


def test_trusted_source_requires_explicit_matching_approval() -> None:
    sources = [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir/?utm_source=x"}]
    rows = build_trusted_source_rows(
        sources,
        [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir/", "approved": True}],
    )
    assert rows[0]["trusted"] is True
    assert rows[0]["trust_reason"] == "明示承認済み"
    assert rows[0]["normalized_source_url"] == "https://example.com/ir"


def test_trusted_source_never_infers_from_existing_source_fields() -> None:
    rows = build_trusted_source_rows([
        {"stock_id": 1, "source_type": "official_ir_calendar", "source_url": "https://example.com/ir", "enabled": 1}
    ])
    assert rows[0]["trusted"] is False
    assert rows[0]["trust_reason"] == "明示承認なし"
