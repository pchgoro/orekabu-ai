"""Manual article input provider."""

from __future__ import annotations

from typing import Any

from services.news_providers.base import NewsItem


class ManualNewsProvider:
    """Normalize one user-entered article."""

    name = "manual"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def fetch(self) -> list[NewsItem]:
        """Return the manually supplied item."""
        title = str(self.payload.get("title") or "").strip()
        if not title:
            raise ValueError("タイトルは必須です。")
        return [NewsItem(
            title=title, url=str(self.payload.get("url") or "").strip(),
            published_at=self.payload.get("published_at"), author=str(self.payload.get("author") or "").strip(),
            summary=str(self.payload.get("summary") or "").strip(), external_id=str(self.payload.get("external_id") or "").strip(),
        )]
