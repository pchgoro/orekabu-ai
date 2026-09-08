"""Explicit, non-learning trusted-source view models."""

from __future__ import annotations

from typing import Any, Iterable

from services.news import canonicalize_url


def build_trusted_source_rows(
    sources: Iterable[dict[str, Any]],
    approvals: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Mark only explicit matching approvals as trusted; never infer trust."""
    approved = {
        (
            str(row.get("stock_id") or ""),
            str(row.get("source_type") or ""),
            canonicalize_url(str(row.get("source_url") or "")),
        )
        for row in approvals or []
        if row.get("approved") is True
    }
    result = []
    for source in sources:
        key = (
            str(source.get("stock_id") or ""),
            str(source.get("source_type") or ""),
            canonicalize_url(str(source.get("source_url") or "")),
        )
        trusted = bool(key[0] and key[1] and key[2] and key in approved)
        result.append({
            **source,
            "normalized_source_url": key[2],
            "trusted": trusted,
            "trust_reason": "明示承認済み" if trusted else "明示承認なし",
        })
    return result
