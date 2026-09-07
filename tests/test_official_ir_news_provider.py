from __future__ import annotations

import urllib.error

import pytest

from services.disclosure_providers.official_ir_news import (
    OfficialIRNewsProvider,
    classify_disclosure_type,
    parse_official_ir_news,
)


class Response:
    def __init__(self, body: str, content_type: str = "application/rss+xml") -> None:
        self.body = body.encode()
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return self.body


RSS = """<?xml version="1.0"?><rss><channel><item><title>上方修正を発表</title><link>https://example.com/ir/1.pdf</link><pubDate>Mon, 07 Sep 2026 09:00:00 +0900</pubDate><guid>ir-1</guid><description>業績予想を見直しました</description></item><item><title>タイトルだけ</title></item></channel></rss>"""


def test_parse_official_ir_news_keeps_only_dated_review_candidates() -> None:
    rows = parse_official_ir_news(RSS, ticker="5801.T", source_url="https://example.com/ir")
    assert len(rows) == 1
    assert rows[0]["disclosure_type"] == "業績予想修正"
    assert rows[0]["external_id"] == "ir-1"
    assert rows[0]["document_url"].endswith("1.pdf")


def test_disclosure_type_rules_are_transparent() -> None:
    assert classify_disclosure_type("自己株式取得を決議") == "自己株式"
    assert classify_disclosure_type("無関係なIR") == "その他"


def test_provider_respects_robots_and_fetches_rss() -> None:
    def opener(request, **_kwargs):
        if request.full_url.endswith("/robots.txt"):
            return Response("User-agent: *\nAllow: /")
        return Response(RSS)

    rows = OfficialIRNewsProvider(
        {"ticker": "5801.T", "source_url": "https://example.com/ir"}, opener=opener
    ).fetch()
    assert rows[0]["ticker"] == "5801.T"

    def denied(request, **_kwargs):
        if request.full_url.endswith("/robots.txt"):
            return Response("User-agent: *\nDisallow: /ir")
        return Response(RSS)

    with pytest.raises(PermissionError):
        OfficialIRNewsProvider(
            {"ticker": "5801.T", "source_url": "https://example.com/ir"}, opener=denied
        ).fetch()


def test_provider_does_not_hide_http_failures() -> None:
    def failing(request, **_kwargs):
        if request.full_url.endswith("/robots.txt"):
            return Response("User-agent: *\nAllow: /")
        raise urllib.error.HTTPError(request.full_url, 503, "down", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        OfficialIRNewsProvider(
            {"ticker": "5801.T", "source_url": "https://example.com/ir"}, opener=failing
        ).fetch()
