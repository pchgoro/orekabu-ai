"""Company profile aggregation, search, timeline, relation, and prompt tests."""

from __future__ import annotations

from pathlib import Path

from services.company_profile import (
    build_company_profile,
    build_timeline,
    search_companies,
    update_company_metadata,
)
from services.database import connect, get_stock, init_db, load_settings
from services.disclosures import save_disclosure
from services.earnings import add_earnings
from services.news import confirm_stock_match, list_stock_matches, save_article
from services.news_providers.base import NewsItem
from services.relations import add_relation


def seed_profile(db: Path) -> dict:
    stock = get_stock("5801.T", db); related = get_stock("6976.T", db)
    assert stock and related
    update_company_metadata(int(stock["id"]), "古河電工", "東証プライム", "非鉄金属", db)
    add_earnings({"stock_id": stock["id"], "fiscal_year": 2025, "fiscal_quarter": "通期", "earnings_date": "2025-05-12", "date_status": "確定"}, db)
    add_earnings({"stock_id": stock["id"], "fiscal_year": 2027, "fiscal_quarter": "Q1", "earnings_date": "2026-08-05", "date_status": "予定"}, db)
    add_earnings({"stock_id": related["id"], "fiscal_year": 2027, "fiscal_quarter": "Q1", "earnings_date": "2026-08-01", "date_status": "予定"}, db)
    add_relation({"source_stock_id": stock["id"], "related_stock_id": related["id"], "relation_type": "同業", "impact_level": "中", "memo": "比較"}, db)
    _, article_id = save_article(NewsItem(title="5801 古河電気工業の新製品", published_at="2026-07-12T09:00:00"), db_path=db)
    match = next(row for row in list_stock_matches(db, article_id) if int(row["stock_id"]) == int(stock["id"]))
    confirm_stock_match(article_id, int(match["stock_id"]), True, db)
    save_disclosure({"ticker": "5801.T", "disclosure_type": "決算短信", "title": "決算短信を開示", "disclosed_at": "2026-07-13T15:00", "importance": "高"}, db_path=db)
    with connect(db) as conn:
        now = "2026-07-13T10:00:00"
        conn.execute("""INSERT INTO earnings_candidates
            (stock_id,provider_name,source_reference,candidate_date,announcement_time,fiscal_year,fiscal_quarter,
             confidence,comparison_status,review_status,retrieved_at,raw_payload_summary,fingerprint,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (stock["id"], "test", "", "2026-08-06", "", 2027, "Q1", "high", "date_changed", "pending", now, "", "profile-candidate", now, now))
    return stock


def test_search_metadata_and_cross_domain_profile(tmp_path: Path) -> None:
    db = tmp_path / "profile.db"; init_db(db); stock = seed_profile(db)
    assert search_companies("古河電工", db)[0]["ticker"] == "5801.T"
    assert search_companies("5801", db)[0]["company_name"] == stock["company_name"]
    profile = build_company_profile("5801", load_settings(db), db, include_price=False)
    assert profile["stock"]["market"] == "東証プライム"
    assert profile["next_earnings"]["earnings_date"] == "2026-08-05"
    assert profile["earnings_candidates"][0]["comparison_status"] == "date_changed"
    assert profile["related_earnings"][0]["related_ticker"] == "6976.T"
    assert profile["earnings_history"][0]["earnings_date"] == "2025-05-12"
    assert profile["news"][0]["title"] == "5801 古河電気工業の新製品"
    assert profile["disclosures"][0]["title"] == "決算短信を開示"
    assert profile["relations"][0]["relation_type"] == "同業"
    assert profile["relations"][0]["direction_label"] == "この企業 ← 関連銘柄"

    reverse_profile = build_company_profile("6976.T", load_settings(db), db, include_price=False)
    assert reverse_profile["relations"][0]["direction_label"] == "この企業 → 影響を受ける銘柄"
    assert reverse_profile["relations"][0]["related_ticker"] == "5801.T"


def test_timeline_is_newest_first_and_missing_values_are_safe() -> None:
    timeline = build_timeline(
        [{"title": "ニュース", "published_at": "2026-07-12T09:00:00"}],
        [{"title": "開示", "disclosed_at": "2026-07-13T15:00:00"}],
        [{"fiscal_year": 2026, "fiscal_quarter": "Q1", "earnings_date": None}],
    )
    assert [row["event_type"] for row in timeline] == ["適時開示", "ニュース", "決算"]
    assert all("None" not in row["title"] for row in timeline)


def test_company_prompt_contains_required_sections_without_missing_literals(tmp_path: Path) -> None:
    db = tmp_path / "prompt.db"; init_db(db); seed_profile(db)
    profile = build_company_profile("5801.T", load_settings(db), db, include_price=False)
    prompt = profile["prompt"]
    for text in ("最新ニュース", "最新適時開示", "次回決算", "関連銘柄", "保有メモ", "売買を断定せず"):
        assert text in prompt
    assert "None" not in prompt and "nan" not in prompt.lower()
