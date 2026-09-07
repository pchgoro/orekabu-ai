"""Conservative RSS/Atom adapter for configured official IR news sources."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime
from typing import Any, Callable

from services.news_providers.base import NewsItem
from services.news_providers.rss_provider import RssNewsProvider

USER_AGENT = "orekabu-ai/local-personal-use"
MAX_FEED_BYTES = 2 * 1024 * 1024
DISCLOSURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("決算短信", ("決算短信", "四半期決算", "通期決算")),
    ("業績予想修正", ("上方修正", "下方修正", "業績予想")),
    ("配当修正", ("増配", "減配", "配当")),
    ("自己株式", ("自社株買い", "自己株式取得")),
    ("M&A", ("M&A", "買収", "合併", "TOB")),
    ("提携", ("業務提携", "資本提携", "提携")),
    ("人事", ("代表取締役", "人事異動", "人事")),
)


def classify_disclosure_type(title: str, summary: str = "") -> str:
    """Return a transparent disclosure type without making investment claims."""
    text = f"{title or ''} {summary or ''}".casefold()
    for disclosure_type, terms in DISCLOSURE_RULES:
        if any(term.casefold() in text for term in terms):
            return disclosure_type
    return "その他"


def parse_official_ir_news(
    content: bytes | str,
    *,
    ticker: str,
    source_url: str,
    source_name: str = "official_ir_news",
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Normalize RSS/Atom entries into review-only disclosure payloads."""
    items = RssNewsProvider.parse(content)[: max(1, min(int(max_items), 50))]
    return [
        payload
        for item in items
        if (payload := _payload(item, ticker, source_url, source_name)) is not None
    ]


class OfficialIRNewsProvider:
    """Fetch one configured official IR RSS/Atom source after robots.txt check."""

    name = "official_ir_news"

    def __init__(
        self,
        source: dict[str, Any],
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: int = 20,
        max_items: int = 20,
    ) -> None:
        self.source = source
        self.opener = opener
        self.timeout = timeout
        self.max_items = max_items

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch candidates; inaccessible or malformed sources fail closed."""
        source_url = str(self.source.get("source_url") or "")
        if not source_url:
            raise ValueError("公式IRニュースURLが設定されていません。")
        if not self._robots_allowed(source_url):
            raise PermissionError("robots.txtにより公式IRニュースの自動取得が許可されていません。")
        request = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT})
        with self.opener(request, timeout=self.timeout) as response:
            content = response.read(MAX_FEED_BYTES + 1)
        if len(content) > MAX_FEED_BYTES:
            raise ValueError("公式IRニュースの応答がサイズ上限を超えています。")
        return parse_official_ir_news(
            content,
            ticker=str(self.source.get("ticker") or ""),
            source_url=source_url,
            source_name=str(self.source.get("company_name") or self.name),
            max_items=self.max_items,
        )

    def _robots_allowed(self, source_url: str) -> bool:
        parts = urllib.parse.urlsplit(source_url)
        robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                content = response.read(MAX_FEED_BYTES).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return True
            if exc.code in {401, 403}:
                return False
            raise
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(content.splitlines())
        return parser.can_fetch(USER_AGENT, source_url)


def _payload(item: NewsItem, ticker: str, source_url: str, source_name: str) -> dict[str, Any] | None:
    if not item.title or not item.published_at:
        return None
    return {
        "ticker": ticker,
        "disclosure_type": classify_disclosure_type(item.title, item.summary),
        "title": item.title,
        "disclosed_at": item.published_at,
        "source_name": source_name,
        "source_url": source_url,
        "document_url": item.url or source_url,
        "summary": item.summary,
        "importance": "通常",
        "external_id": item.external_id,
    }
