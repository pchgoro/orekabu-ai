"""Company profile aggregation, search, timeline, relation, and prompt tests."""

from __future__ import annotations

from pathlib import Path

from services.company_profile import (
    add_company_note,
    build_company_profile,
    build_timeline,
    delete_company_note,
    save_company_intelligence,
    search_companies,
    update_company_metadata,
)
from services.database import connect, get_stock, init_db, load_settings
from services.disclosures import save_disclosure
from services.earnings import add_earnings
from services.news import confirm_stock_match, list_stock_matches, save_article
from services.news_providers.base import NewsItem
from services.relations import add_relation
from services.investment_playbooks import save_playbook
from services.strategy_rules import (
    list_tags,
    replace_stock_tags,
    save_rule_set,
)


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
        conn.execute(
            """INSERT INTO edinet_documents
            (doc_id,stock_id,edinet_code,sec_code,filer_name,document_type,
             submitted_at,description,reference_url,retrieved_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "DOC-PROFILE", stock["id"], "E00001", "58010",
                stock["company_name"], "有価証券報告書",
                "2026-07-14T10:00:00", "有価証券報告書を提出",
                "https://example.com/edinet", now, now,
            ),
        )
    save_company_intelligence(
        int(stock["id"]),
        "AI、データセンター\nAI",
        "需要拡大と設備投資を確認する。",
        {
            "earnings_checked": True,
            "disclosure_checked": False,
            "news_checked": True,
            "edinet_checked": False,
            "ai_analyzed": True,
        },
        db,
    )
    add_company_note(
        int(stock["id"]), "受注動向を次回決算で確認", "2026-07-15T00:00:00", db
    )
    save_playbook(
        int(stock["id"]),
        {
            "buy_reason": "設備投資需要",
            "investment_themes": ["AI", "データセンター"],
            "target_price_1": 3500,
            "target_price_1_sell_percent": 30,
            "stop_loss_price": 2900,
            "holding_period": "中期",
            "exit_conditions": {
                "selected": ["テーマ崩壊"],
                "custom": "受注鈍化",
            },
            "risk_notes": "決算を確認",
        },
        db,
    )
    ai_tag = next(
        row for row in list_tags(db)
        if row["name"] == "AI" and row["tag_group"] == "theme"
    )
    replace_stock_tags(int(stock["id"]), [int(ai_tag["id"])], db)
    save_rule_set(
        int(ai_tag["id"]),
        {
            "stop_loss_type": "percent_from_average_price",
            "stop_loss_value": 8,
            "take_profit_type": "percent_from_average_price",
            "take_profit_value": 30,
            "add_position_type": "percent_from_average_price",
            "add_position_value": 12,
            "priority": 10,
        },
        db,
    )
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
    assert profile["edinet_documents"][0]["doc_id"] == "DOC-PROFILE"
    assert profile["relations"][0]["relation_type"] == "同業"
    assert profile["relations"][0]["direction_label"] == "この企業 ← 関連銘柄"
    assert profile["intelligence"]["themes"] == "AI, データセンター"
    assert profile["intelligence"]["investment_story"] == "需要拡大と設備投資を確認する。"
    assert profile["intelligence"]["earnings_checked"] == 1
    assert profile["notes"][0]["note"] == "受注動向を次回決算で確認"
    assert profile["investment_playbook"]["buy_reason"] == "設備投資需要"
    assert profile["playbook_evaluation"]["status_code"] == "no_price"
    assert profile["strategy_tags"][0]["name"] == "AI"
    assert profile["strategy_rule_resolution"]["source_tag_id"] == _tag_id(
        db, "AI", "theme"
    )
    assert any(row["event_type"] == "メモ" for row in profile["timeline"])

    reverse_profile = build_company_profile("6976.T", load_settings(db), db, include_price=False)
    assert reverse_profile["relations"][0]["direction_label"] == "この企業 → 影響を受ける銘柄"
    assert reverse_profile["relations"][0]["related_ticker"] == "5801.T"


def test_timeline_is_newest_first_and_missing_values_are_safe() -> None:
    timeline = build_timeline(
        [{"title": "ニュース", "published_at": "2026-07-12T09:00:00"}],
        [{"title": "開示", "disclosed_at": "2026-07-13T15:00:00"}],
        [{"fiscal_year": 2026, "fiscal_quarter": "Q1", "earnings_date": None}],
        [{"document_type": "臨時報告書", "submitted_at": "2026-07-14T10:00:00"}],
        [{"id": 1, "note": "確認メモ", "occurred_at": "2026-07-15T09:00:00"}],
    )
    assert [row["event_type"] for row in timeline] == ["メモ", "EDINET", "適時開示", "ニュース", "決算"]
    assert all("None" not in row["title"] for row in timeline)


def test_company_prompt_contains_required_sections_without_missing_literals(tmp_path: Path) -> None:
    db = tmp_path / "prompt.db"; init_db(db); seed_profile(db)
    profile = build_company_profile("5801.T", load_settings(db), db, include_price=False)
    prompt = profile["prompt"]
    for text in ("最新ニュース", "最新適時開示", "最新EDINET書類", "次回決算", "関連銘柄", "保有メモ", "テーマ", "投資ストーリー", "確認チェックリスト", "時系列メモ", "買った理由", "利確①", "損切り価格", "戦略タグ", "戦略ルール損切価格", "戦略ルール買い増し価格", "上記ルールを前提として", "売買推奨は禁止", "売買を断定せず"):
        assert text in prompt
    assert "None" not in prompt and "nan" not in prompt.lower()


def test_company_note_can_be_deleted(tmp_path: Path) -> None:
    db = tmp_path / "notes.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    assert stock
    note_id = add_company_note(int(stock["id"]), "削除対象", db_path=db)
    delete_company_note(note_id, db)
    profile = build_company_profile(
        "5801.T", load_settings(db), db, include_price=False
    )
    assert profile["notes"] == []


def _tag_id(db: Path, name: str, group: str) -> int:
    return int(
        next(
            row for row in list_tags(db)
            if row["name"] == name and row["tag_group"] == group
        )["id"]
    )
