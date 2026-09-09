"""Settings page smoke coverage for the local automation section."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.database import add_stock, connect, get_stock, get_stocks
from services.earnings_ir_sources import list_ir_sources, save_ir_source
from services.stock_profiles import list_profile_candidates, run_profile_refresh
from services.trusted_sources import list_trusted_source_approvals

ROOT = Path(__file__).resolve().parents[2]


class Provider:
    name = "mock"

    def fetch(self, _ticker: str) -> dict[str, str]:
        return {
            "company_name": "候補会社名",
            "company_alias": "候補略称",
            "market": "候補市場",
            "industry": "候補業種",
            "retrieved_at": "2026-07-16T10:00:00+09:00",
        }


def test_settings_page_shows_automation_status_without_network(ui_db: Path) -> None:
    at = AppTest.from_file(
        str(ROOT / "pages" / "6_設定.py"), default_timeout=60
    ).run(timeout=60)
    assert not at.exception
    assert any("無料取得自動化" in item.value for item in at.subheader)
    assert any("無料データを手動で一括更新" in item.label for item in at.button)
    assert any("EDINET APIキー:" in item.value for item in at.markdown)
    assert not any("EDINET_API_KEY=" in item.value for item in at.markdown)
    assert any("企業情報候補の確認" in item.value for item in at.markdown)
    assert any("trusted source（確認用）" in item.value for item in at.subheader)
    assert any("actor" in item.value or "承認" in item.value for item in at.caption)
    labels = {item.label: item.value for item in at.number_input}
    assert labels["日次取得日数"] == 3
    assert labels["月次確認日数"] == 30
    assert labels["初回バックフィル日数"] == 90
    assert labels["最大保存件数"] == 20


def test_settings_page_shows_real_ir_source_as_unapproved_without_db_change(ui_db: Path) -> None:
    stock = get_stock("5801.T", ui_db)
    save_ir_source({"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir"}, ui_db)
    before = list_ir_sources(ui_db)
    at = AppTest.from_file(str(ROOT / "pages" / "6_設定.py"), default_timeout=60).run(timeout=60)
    assert not at.exception
    assert any("trusted source（確認用）" in item.value for item in at.subheader)
    rendered = "\n".join(item.value.to_string() for item in at.dataframe)
    assert all(value in rendered for value in ("5801.T", "official_ir_news", "https://example.com/ir", "未承認", "明示承認"))
    assert list_ir_sources(ui_db) == before


def test_settings_page_persists_explicit_trusted_source_approval_and_revoke(ui_db: Path) -> None:
    stock = get_stock("5801.T", ui_db)
    save_ir_source({"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir"}, ui_db)
    at = AppTest.from_file(str(ROOT / "pages" / "6_設定.py"), default_timeout=60).run(timeout=60)
    assert not at.exception
    actor = next(item for item in at.text_input if item.label == "承認者（必須）")
    actor.set_value("tester")
    next(item for item in at.checkbox if item.label == "このtrusted sourceの状態変更を確認しました").set_value(True)
    at = next(item for item in at.button if item.label == "trusted sourceを明示承認").click().run(timeout=60)
    assert not at.exception
    assert list_trusted_source_approvals(ui_db)[0]["approved"] == 1

    actor = next(item for item in at.text_input if item.label == "承認者（必須）")
    actor.set_value("tester")
    next(item for item in at.checkbox if item.label == "このtrusted sourceの状態変更を確認しました").set_value(True)
    at = next(item for item in at.button if item.label == "trusted sourceの承認を解除").click().run(timeout=60)
    assert not at.exception
    assert list_trusted_source_approvals(ui_db)[0]["approved"] == 0


def test_settings_page_can_approve_profile_candidate(ui_db: Path) -> None:
    run_profile_refresh(Provider(), ticker="5801.T", db_path=ui_db)
    at = AppTest.from_file(
        str(ROOT / "pages" / "6_設定.py"), default_timeout=60
    ).run(timeout=60)
    assert not at.exception
    approve = next(
        item for item in at.button if item.label == "全項目を承認"
    )
    at = approve.click().run(timeout=60)
    assert not at.exception
    stock = get_stock("5801.T", ui_db)
    assert stock["market"] == "候補市場"
    assert stock["industry"] == "候補業種"


def test_settings_page_can_hold_profile_candidate_without_updating_stock(ui_db: Path) -> None:
    run_profile_refresh(Provider(), ticker="5801.T", db_path=ui_db)
    before = get_stock("5801.T", ui_db)
    at = AppTest.from_file(str(ROOT / "pages" / "6_設定.py"), default_timeout=60).run(timeout=60)
    at = next(item for item in at.button if item.label == "保留").click().run(timeout=60)
    assert not at.exception
    assert get_stock("5801.T", ui_db) == before
    assert list_profile_candidates(review_status=None, db_path=ui_db)[0]["review_status"] == "held"


def test_settings_page_can_reject_profile_candidate(ui_db: Path) -> None:
    run_profile_refresh(Provider(), ticker="5801.T", db_path=ui_db)
    at = AppTest.from_file(str(ROOT / "pages" / "6_設定.py"), default_timeout=60).run(timeout=60)
    at = next(item for item in at.button if item.label == "却下").click().run(timeout=60)
    assert not at.exception
    assert list_profile_candidates(review_status=None, db_path=ui_db)[0]["review_status"] == "rejected"


def test_settings_page_shows_marketspeed_preview(ui_db: Path) -> None:
    content = (
        '"売り","コード","銘柄名","口座区分","保有数量(株/口)",'
        '"評価損益額(円)","評価損益率(％)","配当利回り(％)",'
        '"PER","PBR","前日比(円)","前日比率(％)","決算日",'
        '"平均取得価額(円)","JAX時価(円)","時価(円)",'
        '"時価評価額(円)","発注数量(株/口)","銘柄情報等","JNX時価(円)"\n'
        '"売り","285A","テストETF","NISA","10","+1,000","+5",'
        '"2","10","1","+1","+1","03/31","2,000","-",'
        '"2,100","21,000","0","-","-"\n'
    ).encode("utf-8-sig")
    at = AppTest.from_file(
        str(ROOT / "pages" / "6_設定.py"), default_timeout=60
    ).run(timeout=60)
    uploader = next(
        item
        for item in at.file_uploader
        if item.label == "マーケットスピードCSVファイル"
    )
    at = uploader.upload("market.csv", content, "text/csv").run(timeout=60)
    assert not at.exception
    assert any("文字コード: UTF-8 BOM" in item.value for item in at.caption)
    frames = " ".join(
        frame.value.fillna("").to_string() for frame in at.dataframe
    )
    assert "285A.T" in frames
    assert "新規" in frames


def test_settings_page_imports_marketspeed_preview_without_destroying_existing_state(ui_db: Path) -> None:
    with connect(ui_db) as conn:
        conn.execute(
            """UPDATE stocks SET company_name='既存会社',is_holding=1,shares=50,
               average_price=1000,buy_watch_price=900,memo='ユーザーメモ',
               company_alias='既存略称',market='東証',industry='電機' WHERE ticker='5801.T'"""
        )
    add_stock({"ticker": "7203", "company_name": "CSV外保有", "category": "保有株", "is_holding": True, "shares": 10, "average_price": 2000, "memo": "維持"}, ui_db)
    content = (
        '"売り","コード","銘柄名","口座区分","保有数量(株/口)","平均取得価額(円)"\n'
        '"売り","5801","更新会社","特定","100","1,500"\n'
        '"売り","285A","新規ETF","NISA","10","2,000"\n'
    ).encode("utf-8-sig")
    at = AppTest.from_file(str(ROOT / "pages" / "6_設定.py"), default_timeout=60).run(timeout=60)
    uploader = next(item for item in at.file_uploader if item.label == "マーケットスピードCSVファイル")
    at = uploader.upload("market-import.csv", content, "text/csv").run(timeout=60)
    assert not at.exception
    import_button = next(item for item in at.button if item.label == "マーケットスピードCSVをインポート")
    at = import_button.click().run(timeout=60)
    assert not at.exception
    updated = get_stock("5801.T", ui_db)
    assert updated["shares"] == 100 and updated["average_price"] == 1500
    assert updated["buy_watch_price"] == 900 and updated["memo"].startswith("ユーザーメモ")
    assert updated["company_alias"] == "既存略称" and updated["market"] == "東証" and updated["industry"] == "電機"
    assert get_stock("285A.T", ui_db)["is_holding"] == 1
    assert get_stock("7203.T", ui_db)["is_holding"] == 1


def test_settings_page_rejects_unknown_marketspeed_csv_without_db_change(ui_db: Path) -> None:
    before = get_stocks(ui_db)
    invalid_content = b'"other_code","other_name"\n"5801","unknown"\n'
    at = AppTest.from_file(str(ROOT / "pages" / "6_設定.py"), default_timeout=60).run(timeout=60)
    uploader = next(item for item in at.file_uploader if item.label == "マーケットスピードCSVファイル")
    at = uploader.upload("unknown-format.csv", invalid_content, "text/csv").run(timeout=60)
    assert not at.exception
    assert any("必要なCSV列が不足しています" in item.value for item in at.error)
    assert not any(item.label == "マーケットスピードCSVをインポート" for item in at.button)
    assert get_stocks(ui_db) == before
