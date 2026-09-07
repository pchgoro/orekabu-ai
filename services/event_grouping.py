"""Read-only grouping of equivalent external material records."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date
from typing import Any

from services.news import canonicalize_url


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _semantic_date(record: dict[str, Any]) -> str:
    for field in ("event_date", "published_at", "disclosed_at"):
        raw = str(record.get(field) or "").strip()
        if not raw:
            continue
        try:
            return date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            return ""
    return ""


def material_group_key(record: dict[str, Any]) -> str:
    """Build a deterministic cross-source key without deleting source records."""
    ticker = _text(record.get("ticker"))
    title = _text(record.get("title"))
    event_date = _semantic_date(record)
    if ticker and title and event_date:
        identity = f"material|{ticker}|{title}|{event_date}"
    else:
        url = canonicalize_url(str(record.get("url") or record.get("source_url") or record.get("document_url") or ""))
        identity = f"url|{url}" if url else ""
    if not identity:
        return ""
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def group_material_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display groups while retaining every original record and provenance."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, record in enumerate(records):
        key = material_group_key(record) or f"ambiguous|{index}"
        grouped[key].append(record)
    result = []
    for group_key, items in grouped.items():
        first = items[0]
        provenance = [
            {
                "source": item.get("source") or item.get("source_name") or "unknown",
                "url": item.get("url") or item.get("source_url") or item.get("document_url") or "",
                "record_id": item.get("id"),
            }
            for item in items
        ]
        result.append({
            "group_key": group_key,
            "ticker": first.get("ticker"),
            "title": first.get("title"),
            "event_date": first.get("event_date") or first.get("published_at") or first.get("disclosed_at"),
            "records": items,
            "provenance": provenance,
            "source_count": len({entry["source"] for entry in provenance}),
        })
    return result
