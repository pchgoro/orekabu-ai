"""Official IR extraction, source state, and ordered fallback tests."""

from __future__ import annotations

import sqlite3
import urllib.error
from datetime import date
from pathlib import Path

from services.database import get_stock, init_db, load_settings
from services.earnings import list_earnings
from services.earnings_candidates import list_candidates
from services.earnings_ir_sources import (
    fetch_ir_source_candidate,
    get_ir_source_for_ticker,
    list_ir_sources,
    record_ir_source_result,
    save_ir_source,
    source_is_due,
)
from services.earnings_providers.base import EarningsFetchResult
from services.earnings_providers.fallback_provider import FallbackEarningsProvider
from services.earnings_providers.official_ir_provider import (
    OfficialIREarningsProvider,
    extract_ir_earnings_dates,
)


class Response:
    """Minimal urllib-compatible response."""

    def __init__(
        self,
        body: str,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.body = body.encode("utf-8")
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def source(stock_id: int = 1) -> dict:
    return {
        "id": 1,
        "stock_id": stock_id,
        "source_type": "official_ir_calendar",
        "source_url": "https://example.com/ir/calendar",
    }


def test_extracts_supported_dates_quarters_and_multiple_future_dates() -> None:
    html = """
    <html><body>
    2026年8月13日 2026年9月期 第3四半期決算発表予定
    2026/11/12 2026年9月期 通期決算発表
    2026-05-14 第2四半期決算発表
    </body></html>
    """
    rows = extract_ir_earnings_dates(html, date(2026, 7, 16))
    assert [row.value.isoformat() for row in rows] == ["2026-08-13", "2026-11-12"]
    assert {row.fiscal_quarter for row in rows} == {"Q3", "通期"}
    assert {row.fiscal_year for row in rows} == {2026}


def test_extracts_yearless_date_and_excludes_past_dates() -> None:
    html = "5月14日 第2四半期決算発表 / 8月13日 第3四半期決算発表予定"
    rows = extract_ir_earnings_dates(html, date(2026, 7, 16))
    assert [row.value.isoformat() for row in rows] == ["2026-08-13"]


def test_extracts_dot_date_and_uses_fiscal_year_for_yearless_calendar_rows() -> None:
    html = """
    2026.08.14 2026年12月期 第2四半期決算発表
    8月7日 2026年12月期第2四半期決算発表
    8月8日 2025年12月期第2四半期決算発表
    """
    rows = extract_ir_earnings_dates(html, date(2026, 7, 16))
    assert [row.value.isoformat() for row in rows] == ["2026-08-07", "2026-08-14"]


def test_publication_period_dates_are_not_mistaken_for_earnings_dates() -> None:
    html = """
    公開期間:2026年2月26日から2026年8月26日
    2月13日 2025年12月期通期決算発表
    8月7日 2026年12月期第2四半期決算発表
    """
    rows = extract_ir_earnings_dates(html, date(2026, 7, 16))
    assert [row.value.isoformat() for row in rows] == ["2026-08-07"]


def test_unrelated_dates_and_changed_html_are_not_candidates() -> None:
    html = "<p>2026年8月13日 株主総会のお知らせ</p><p>IR情報を掲載しています</p>"
    assert extract_ir_earnings_dates(html, date(2026, 7, 16)) == []


def test_provider_respects_robots_and_handles_http_failure() -> None:
    def denied(request, **_kwargs):
        return Response("User-agent: *\nDisallow: /ir/")

    denied_result = OfficialIREarningsProvider(
        source(), opener=denied, today=date(2026, 7, 16)
    ).fetch_next_earnings("5801.T")
    assert denied_result.error_code == "robots_denied"

    def failing(request, **_kwargs):
        if request.full_url.endswith("/robots.txt"):
            return Response("User-agent: *\nAllow: /")
        raise urllib.error.HTTPError(request.full_url, 503, "down", {}, None)

    failed_result = OfficialIREarningsProvider(
        source(), opener=failing, today=date(2026, 7, 16)
    ).fetch_next_earnings("5801.T")
    assert failed_result.error_code == "http_503"


def test_provider_fetches_html_without_saving_full_content() -> None:
    def opener(request, **_kwargs):
        if request.full_url.endswith("/robots.txt"):
            return Response("User-agent: *\nAllow: /")
        return Response("<p>2026年8月6日 第1四半期決算発表予定</p>")

    result = OfficialIREarningsProvider(
        source(), opener=opener, today=date(2026, 7, 16)
    ).fetch_next_earnings("5801.T")
    assert result.succeeded
    assert result.earnings_date == date(2026, 8, 6)
    assert result.fiscal_quarter == "Q1"
    assert "<p>" not in result.raw_payload_summary


def test_ir_source_crud_and_24_hour_cache(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    source_id = save_ir_source(
        {
            "stock_id": stock["id"],
            "source_type": "official_ir_calendar",
            "source_url": "https://example.com/ir",
            "enabled": True,
        },
        db,
    )
    selected = get_ir_source_for_ticker("5801.T", db)
    assert selected["id"] == source_id
    assert source_is_due(selected)
    record_ir_source_result(source_id, success=True, db_path=db)
    selected = get_ir_source_for_ticker("5801.T", db)
    assert not source_is_due(selected)
    assert source_is_due(selected, force=True)
    assert len(list_ir_sources(db)) == 1


def future_result(ticker: str, provider: str = "yfinance") -> EarningsFetchResult:
    return EarningsFetchResult(
        ticker=ticker,
        earnings_date=date(2099, 8, 6),
        candidate_dates=(date(2099, 8, 6),),
        source_name=provider,
        source_reference="unit",
        retrieved_at="2099-01-01T00:00:00+09:00",
        confidence="high",
    )


class Primary:
    name = "yfinance"

    def __init__(self, result: EarningsFetchResult) -> None:
        self.result = result

    def fetch_next_earnings(self, _ticker: str) -> EarningsFetchResult:
        return self.result


class OfficialFactory:
    calls = 0

    def __init__(self, _source, **_kwargs) -> None:
        type(self).calls += 1

    def fetch_next_earnings(self, ticker: str) -> EarningsFetchResult:
        return future_result(ticker, "official_ir")


def test_yfinance_success_does_not_call_ir(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    OfficialFactory.calls = 0
    provider = FallbackEarningsProvider(
        Primary(future_result("5801.T")),
        db_path=db,
        official_provider_factory=OfficialFactory,
        today=date(2026, 7, 16),
    )
    assert provider.fetch_next_earnings("5801.T").source_name == "yfinance"
    assert OfficialFactory.calls == 0
    assert provider.stats["yfinance_success"] == 1


def test_yfinance_failure_uses_ir_and_missing_url_is_safe(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    empty = EarningsFetchResult(
        ticker="5801.T",
        source_name="yfinance",
        error_code="empty_data",
        error_message="empty",
    )
    missing = FallbackEarningsProvider(
        Primary(empty),
        db_path=db,
        official_provider_factory=OfficialFactory,
        today=date(2026, 7, 16),
    ).fetch_next_earnings("5801.T")
    assert missing.error_code == "ir_source_missing"

    stock = get_stock("5801.T", db)
    save_ir_source(
        {
            "stock_id": stock["id"],
            "source_type": "official_ir_calendar",
            "source_url": "https://example.com/ir",
        },
        db,
    )
    provider = FallbackEarningsProvider(
        Primary(empty),
        db_path=db,
        official_provider_factory=OfficialFactory,
        today=date(2026, 7, 16),
    )
    result = provider.fetch_next_earnings("5801.T")
    assert result.source_name == "official_ir"
    assert provider.stats["ir_targets"] == 1
    assert provider.stats["ir_success"] == 1


def test_official_candidate_never_updates_formal_earnings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    source_id = save_ir_source(
        {
            "stock_id": stock["id"],
            "source_type": "official_ir_calendar",
            "source_url": "https://example.com/ir",
        },
        db,
    )
    monkeypatch.setattr(
        OfficialIREarningsProvider,
        "fetch_next_earnings",
        lambda self, ticker: future_result(ticker, "official_ir"),
    )
    result = fetch_ir_source_candidate(source_id, load_settings(db), db)
    assert result["success"]
    assert len(list_candidates(db)) == 1
    assert list_earnings(db) == []


def test_source_status_write_can_be_disabled_for_dry_run(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    save_ir_source(
        {
            "stock_id": stock["id"],
            "source_type": "official_ir_calendar",
            "source_url": "https://example.com/ir",
        },
        db,
    )
    empty = EarningsFetchResult(ticker="5801.T", error_code="empty_data")
    provider = FallbackEarningsProvider(
        Primary(empty),
        db_path=db,
        persist_source_status=False,
        official_provider_factory=OfficialFactory,
        today=date(2026, 7, 16),
    )
    provider.fetch_next_earnings("5801.T")
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT last_checked_at FROM stock_ir_sources"
        ).fetchone()[0] is None
