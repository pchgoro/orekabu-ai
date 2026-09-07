"""News database, matching, deduplication, state, and CSV tests."""

from __future__ import annotations

import io
from pathlib import Path

from services.database import get_stock, init_db
from services.news import (
    add_keyword, add_source, confirm_stock_match, export_csv, get_article_tags, import_csv,
    build_stock_match_candidates, list_articles, list_stock_matches, make_news_prompt, parse_csv, save_article,
    set_article_tags, update_article,
)
from services.news_providers.base import NewsItem


def test_stock_match_candidates_rank_and_hold_ambiguous_matches() -> None:
    stocks = [
        {"id": 1, "ticker": "5801.T", "company_name": "古河電気工業"},
        {"id": 2, "ticker": "6976.T", "company_name": "太陽誘電"},
    ]
    candidates = build_stock_match_candidates(
        "5801 古河電気工業と光ファイバー業界",
        stocks,
        [{"stock_id": 1, "keyword": "光ファイバー", "is_enabled": 1}],
    )
    assert candidates[0]["ticker"] == "5801.T"
    assert candidates[0]["confidence"] == "high"
    assert candidates[0]["review_status"] == "pending"
    assert candidates[0]["matched_terms"] == ["5801", "光ファイバー", "古河電気工業"]

    ambiguous = build_stock_match_candidates(
        "電線業界のニュース",
        stocks,
        [
            {"stock_id": 1, "keyword": "電線", "is_enabled": 1},
            {"stock_id": 2, "keyword": "電線", "is_enabled": 1},
        ],
    )
    assert [row["ticker"] for row in ambiguous] == ["5801.T", "6976.T"]
    assert all(row["ambiguous"] for row in ambiguous)


def test_stock_match_candidates_do_not_return_missing_or_disabled_keywords() -> None:
    stocks = [{"id": 1, "ticker": "5801.T", "company_name": "古河電気工業"}]
    assert build_stock_match_candidates("無関係な記事", stocks) == []
    assert build_stock_match_candidates(
        "光ファイバー", stocks, [{"stock_id": 1, "keyword": "光ファイバー", "is_enabled": 0}]
    ) == []


def test_dedup_matching_state_and_tags(tmp_path: Path) -> None:
    db = tmp_path / "news.db"; init_db(db)
    stock = get_stock("5801.T", db); assert stock
    add_keyword(int(stock["id"]), "光ファイバー", db_path=db)
    item = NewsItem(title="5801 古河電気工業の光ファイバー", url="https://example.com/a?utm_source=x", published_at="2026-07-13T09:00:00")
    status, article_id = save_article(item, db_path=db)
    assert status == "inserted"
    assert save_article(item, db_path=db)[0] == "duplicate"
    matches = list_stock_matches(db, article_id)
    assert matches and not matches[0]["confirmed"]
    confirm_stock_match(article_id, int(stock["id"]), True, db)
    update_article(article_id, {"is_read": True, "is_favorite": True, "importance": "高", "category": "業界", "memo": "確認"}, db)
    set_article_tags(article_id, ["電線", "注目"], db)
    row = list_articles(db)[0]
    assert row["is_read"] and row["is_favorite"] and row["importance"] == "高"
    assert get_article_tags(article_id, db) == ["注目", "電線"]
    prompt = make_news_prompt(row, db)
    assert "売買を断定せず" in prompt and "None" not in prompt and "nan" not in prompt.lower()


def test_source_and_all_csv_exports_have_bom(tmp_path: Path) -> None:
    db = tmp_path / "csv.db"; init_db(db)
    add_source({"name": "Example", "source_type": "RSS", "url": "https://example.com/rss", "is_enabled": True}, db)
    save_article(NewsItem(title="記事", published_at="2026-07-13"), db_path=db)
    stock = get_stock("5801.T", db); add_keyword(int(stock["id"]), "電線", db_path=db)
    for kind in ("articles", "sources", "keywords"):
        content = export_csv(kind, db)
        assert content.startswith(b"\xef\xbb\xbf")
        frame, errors = parse_csv(io.BytesIO(content), kind)
        assert not errors and not frame.empty


def test_exported_rss_article_reimport_is_duplicate_by_canonical_url(tmp_path: Path) -> None:
    db = tmp_path / "article-roundtrip.db"; init_db(db)
    save_article(NewsItem(title="RSS記事", url="https://example.com/news?utm_source=rss", external_id="feed-guid", published_at="2026-07-13"), db_path=db)
    frame, errors = parse_csv(io.BytesIO(export_csv("articles", db)), "articles")
    assert not errors
    result = import_csv(frame, "articles", False, db)
    assert result["inserted"] == 0 and result["skipped"] == 1
    assert len(list_articles(db)) == 1


def test_csv_import_continues_after_invalid_keyword(tmp_path: Path) -> None:
    db = tmp_path / "import.db"; init_db(db)
    raw = "ticker,keyword,is_enabled\n5801.T,光通信,1\n9999.T,存在しない,1\n".encode("utf-8-sig")
    frame, errors = parse_csv(io.BytesIO(raw), "keywords")
    assert not errors
    result = import_csv(frame, "keywords", False, db)
    assert result["inserted"] == 1 and result["failed"] == 1
