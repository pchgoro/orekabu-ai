"""CSV row news provider."""

from __future__ import annotations

from typing import Any

from services.news_providers.manual_provider import ManualNewsProvider


class CsvNewsProvider(ManualNewsProvider):
    """Normalize a CSV row using the manual provider validation."""

    name = "csv"

    def __init__(self, row: dict[str, Any]) -> None:
        super().__init__(row)
