"""Settings page smoke coverage for the local automation section."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.database import get_stock
from services.stock_profiles import run_profile_refresh

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
    labels = {item.label: item.value for item in at.number_input}
    assert labels["日次取得日数"] == 3
    assert labels["月次確認日数"] == 30
    assert labels["初回バックフィル日数"] == 90
    assert labels["最大保存件数"] == 20


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
