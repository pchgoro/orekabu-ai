"""Tests for RSS, Atom, manual, and CSV news providers."""

from services.news_providers.csv_provider import CsvNewsProvider
from services.news_providers.manual_provider import ManualNewsProvider
from services.news_providers.rss_provider import RssNewsProvider


def test_rss_parse_metadata() -> None:
    items = RssNewsProvider.parse(b"""<rss><channel><item><title>Test &amp; News</title><link>https://example.com/a</link><guid>x1</guid><pubDate>Sun, 12 Jul 2026 01:00:00 GMT</pubDate><description><![CDATA[<b>summary</b>]]></description></item></channel></rss>""")
    assert items[0].title == "Test & News"
    assert items[0].summary == "summary"
    assert items[0].external_id == "x1"


def test_atom_parse_metadata() -> None:
    items = RssNewsProvider.parse("""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Atom News</title><id>a1</id><link href='https://example.com/atom'/><updated>2026-07-12T10:00:00Z</updated><summary>hello</summary></entry></feed>""")
    assert items[0].url == "https://example.com/atom"
    assert items[0].published_at.startswith("2026-07-12")


def test_manual_and_csv_require_title() -> None:
    assert ManualNewsProvider({"title": "Manual"}).fetch()[0].title == "Manual"
    assert CsvNewsProvider({"title": "CSV"}).fetch()[0].title == "CSV"
    try:
        ManualNewsProvider({"title": ""}).fetch()
        assert False
    except ValueError:
        pass


def test_rss_fetch_limits_saved_items(monkeypatch) -> None:
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            return b"<rss><channel>" + b"".join(
                f"<item><title>News {index}</title></item>".encode() for index in range(8)
            ) + b"</channel></rss>"

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    assert len(RssNewsProvider("https://example.com/rss", max_items=5).fetch()) == 5
