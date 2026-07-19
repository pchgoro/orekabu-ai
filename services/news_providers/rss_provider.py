"""RSS 2.0 and Atom metadata provider using the Python standard library."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from services.news_providers.base import NewsItem


class RssNewsProvider:
    """Fetch RSS/Atom without persisting article bodies."""

    name = "rss"

    def __init__(self, url: str, timeout: int = 15, max_items: int = 5) -> None:
        self.url = url
        self.timeout = timeout
        self.max_items = max(1, min(int(max_items), 50))

    def fetch(self) -> list[NewsItem]:
        """Download and parse an RSS or Atom feed."""
        request = urllib.request.Request(self.url, headers={"User-Agent": "orekabu-ai/0.4 (+local personal use)"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content = response.read()
                waf_action = response.headers.get("x-amzn-waf-action", "")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"RSS/Atomの取得に失敗しました（HTTP {exc.code}）。配信元のアクセス制限を確認してください。") from exc

        if waf_action:
            raise RuntimeError("RSS/Atomの配信元でWAF認証が要求されたため、自動取得できませんでした。")
        if not content.strip():
            raise RuntimeError("RSS/Atomの応答本文が空でした。配信元のアクセス制限または配信状況を確認してください。")
        try:
            return self.parse(content)[: self.max_items]
        except ET.ParseError as exc:
            raise RuntimeError("RSS/AtomのXMLを解析できませんでした。配信元の応答内容を確認してください。") from exc

    @staticmethod
    def parse(content: bytes | str) -> list[NewsItem]:
        """Parse RSS/Atom bytes into normalized metadata."""
        root = ET.fromstring(content)
        entries = root.findall(".//item")
        atom = not entries
        if atom:
            entries = [node for node in root.iter() if _local(node.tag) == "entry"]
        items: list[NewsItem] = []
        for entry in entries:
            values = {_local(child.tag): (child.text or "").strip() for child in entry}
            link = values.get("link", "")
            if atom:
                link_node = next((child for child in entry if _local(child.tag) == "link"), None)
                if link_node is not None:
                    link = link_node.attrib.get("href", link)
            title = _plain(values.get("title", ""))
            if not title:
                continue
            items.append(NewsItem(
                title=title, url=link, published_at=_date(values.get("pubDate") or values.get("published") or values.get("updated")),
                author=_plain(values.get("author") or values.get("creator", "")),
                summary=_plain(values.get("description") or values.get("summary") or values.get("content", ""))[:4000],
                external_id=values.get("guid") or values.get("id", ""),
            ))
        return items


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def _date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.isoformat(timespec="seconds")
