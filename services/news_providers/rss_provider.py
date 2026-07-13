"""RSS 2.0 and Atom metadata provider using the Python standard library."""

from __future__ import annotations

import html
import re
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
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return self.parse(response.read())[: self.max_items]

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
