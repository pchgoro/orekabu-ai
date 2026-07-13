"""Mocked multi-source news fetch audit tests."""

from pathlib import Path

from services.database import init_db
from services.news import add_source, fetch_enabled_sources, list_fetch_runs
from services.news_providers.base import NewsItem


class Provider:
    name = "mock"
    def __init__(self, fail: bool = False) -> None: self.fail = fail
    def fetch(self):
        if self.fail: raise RuntimeError("network down")
        return [NewsItem(title="mock article", external_id="mock-1", published_at="2026-07-13")]


def test_fetch_isolates_source_failure_and_records_run(tmp_path: Path) -> None:
    db = tmp_path / "fetch.db"; init_db(db)
    add_source({"name": "ok", "source_type": "RSS", "url": "https://ok.example/rss"}, db)
    add_source({"name": "ng", "source_type": "Atom", "url": "https://ng.example/feed"}, db)
    result = fetch_enabled_sources(lambda source: Provider(source["name"] == "ng"), db)
    assert result["inserted"] == 1 and result["failed"] == 1
    assert list_fetch_runs(db)[0]["status"] == "partial"
