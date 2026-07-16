"""Streamlit AppTest smoke test for the news page."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def test_news_page_opens_with_all_tabs(ui_db) -> None:
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    assert not at.exception
    labels = [tab.label for tab in at.tabs]
    assert labels == ["最新", "保有株", "監視銘柄", "未読", "お気に入り", "ソース管理", "キーワード管理", "手動登録", "CSV", "取得履歴"]


def test_manual_registration_refreshes_latest_tab(ui_db) -> None:
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    manual_tab = next(tab for tab in at.tabs if tab.label == "手動登録")
    title = next(widget for widget in manual_tab.text_input if widget.label == "タイトル")
    title.set_value("画面更新テスト記事")
    next(button for button in manual_tab.button if button.label == "記事を登録").click()
    at.run(timeout=60)
    assert any("登録しました" in success.value for success in at.success)
    latest_tab = next(tab for tab in at.tabs if tab.label == "最新")
    assert any("画面更新テスト記事" in item.value for item in latest_tab.markdown)


def test_article_detail_has_original_link(ui_db) -> None:
    from services.news import save_article
    from services.news_providers.base import NewsItem

    save_article(NewsItem(title="リンク確認", url="https://example.com/news"))
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    links = at.get("link_button")
    assert any(link.label == "元記事を開く" and link.url == "https://example.com/news" for link in links)


def test_stock_match_renders_company_profile_action(ui_db) -> None:
    """A rule-matched stock must not break the article detail view."""
    from services.news import save_article
    from services.news_providers.base import NewsItem

    save_article(NewsItem(title="5801 古河電気工業のニュース"))
    at = AppTest.from_file(
        str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60
    ).run(timeout=60)
    assert any(button.label == "企業カルテ" for button in at.button)
    assert not at.exception


def test_switching_article_refreshes_prompt_and_state(ui_db) -> None:
    from services.news import save_article
    from services.news_providers.base import NewsItem

    save_article(NewsItem(title="記事A", url="https://example.com/a"))
    save_article(NewsItem(title="記事B", url="https://example.com/b"), metadata={"importance": "高", "category": "業績"})
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    selector = next(item for item in at.selectbox if item.label == "管理する記事")
    selector.set_value(next(option for option in selector.options if "記事B" in option))
    at.run(timeout=60)
    prompt = next(item for item in at.text_area if item.label == "ChatGPTニュース分析用プロンプト")
    assert "タイトル：記事B" in prompt.value and "記事A" not in prompt.value
    assert next(item for item in at.selectbox if item.label == "重要度").value == "高"
    assert next(item for item in at.selectbox if item.label == "カテゴリ").value == "業績"


def test_switching_source_refreshes_edit_fields(ui_db) -> None:
    from services.news import add_source

    add_source({"name": "ソースA", "source_type": "RSS", "url": "https://example.com/a.xml", "is_enabled": True, "memo": "メモA"})
    add_source({"name": "ソースB", "source_type": "Atom", "url": "https://example.com/b.xml", "is_enabled": False, "memo": "メモB"})
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    selector = next(item for item in at.selectbox if item.label == "編集するソース")
    selector.set_value(next(option for option in selector.options if "ソースB" in option))
    at.run(timeout=60)
    keyed_inputs = {item.key: item.value for item in at.text_input if item.key and item.key.startswith("source_edit_")}
    assert any(value == "ソースB" for value in keyed_inputs.values())
    assert any(value == "https://example.com/b.xml" for value in keyed_inputs.values())
    assert any(value == "メモB" for value in keyed_inputs.values())
    edit_type = next(item for item in at.selectbox if item.key and item.key.startswith("source_edit_") and item.key.endswith("_type"))
    assert edit_type.value == "Atom"
    edit_enabled = next(item for item in at.checkbox if item.key and item.key.startswith("source_edit_") and item.key.endswith("_enabled"))
    assert edit_enabled.value is False


def test_news_card_direct_read_action(ui_db) -> None:
    from services.news import list_articles, save_article
    from services.news_providers.base import NewsItem

    save_article(NewsItem(title="直接操作テスト"))
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    button = next(item for item in at.button if item.label == "既読にする")
    button.click(); at.run(timeout=60)
    assert list_articles()[0]["is_read"] == 1
    assert any(item.label == "未読に戻す" for item in at.button)


def test_news_card_direct_favorite_and_importance(ui_db) -> None:
    from services.news import list_articles, save_article
    from services.news_providers.base import NewsItem

    save_article(NewsItem(title="お気に入り操作テスト"))
    at = AppTest.from_file(str(ROOT / "pages" / "7_ニュース.py"), default_timeout=60).run(timeout=60)
    next(item for item in at.button if item.label == "お気に入り登録").click(); at.run(timeout=60)
    assert list_articles()[0]["is_favorite"] == 1
    direct_importance = next(item for item in at.selectbox if item.key.startswith("direct_最新_importance_"))
    direct_importance.set_value("高"); at.run(timeout=60)
    assert list_articles()[0]["importance"] == "高"
