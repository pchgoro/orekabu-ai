"""Provider-neutral news item contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NewsItem:
    """Normalized metadata stored by the local news service."""

    title: str
    url: str = ""
    published_at: str | None = None
    author: str = ""
    summary: str = ""
    external_id: str = ""


class NewsProvider(Protocol):
    """Interface implemented by external and local news inputs."""

    name: str

    def fetch(self) -> list[NewsItem]:
        """Return normalized article metadata."""
