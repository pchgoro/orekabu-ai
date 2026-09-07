from __future__ import annotations

from pathlib import Path

from services.automation_jobs import run_official_ir_news_job
from services.database import get_stock, init_db
from services.disclosures import list_disclosures
from services.earnings_ir_sources import list_ir_sources, save_ir_source


class Provider:
    def __init__(self, source):
        self.source = source

    def fetch(self):
        if self.source["ticker"] == "6976.T":
            raise RuntimeError("fixture failure")
        return [{
            "ticker": self.source["ticker"],
            "disclosure_type": "業績予想修正",
            "title": "上方修正を発表",
            "disclosed_at": "2026-09-07T09:00:00+09:00",
            "source_name": "fixture",
            "source_url": self.source["source_url"],
            "document_url": self.source["source_url"] + "/1",
            "summary": "fixture",
            "importance": "通常",
            "external_id": "fixture-1",
        }]


def test_official_ir_news_job_isolates_failures_and_deduplicates(tmp_path: Path) -> None:
    db = tmp_path / "disclosure.db"
    init_db(db)
    for ticker in ("5801.T", "6976.T"):
        stock = get_stock(ticker, db)
        save_ir_source(
            {
                "stock_id": stock["id"],
                "source_type": "official_ir_news",
                "source_url": f"https://example.com/{ticker}/rss",
                "enabled": True,
            },
            db,
        )

    first = run_official_ir_news_job(Provider, force=True, db_path=db)
    assert first.processed == 2
    assert first.inserted == 1 and first.failed == 1
    assert len(list_disclosures(db)) == 1
    failed = next(row for row in list_ir_sources(db) if row["ticker"] == "6976.T")
    assert failed["last_success_at"] is None and failed["last_error"]

    second = run_official_ir_news_job(Provider, force=True, db_path=db)
    assert second.inserted == 0 and second.duplicates == 1 and second.failed == 1
    assert len(list_disclosures(db)) == 1

