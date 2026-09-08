"""Explicit, non-learning trusted-source view models."""

from __future__ import annotations

from typing import Any, Iterable

from services.news import canonicalize_url


def normalize_trusted_source_approval(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an explicit approval payload without persisting or inferring it."""
    stock_id = int(payload.get("stock_id") or 0)
    source_type = str(payload.get("source_type") or "").strip()
    source_url = canonicalize_url(str(payload.get("source_url") or ""))
    approved_by = str(payload.get("approved_by") or "").strip()
    if stock_id < 1 or not source_type or not source_url or not approved_by:
        raise ValueError("trusted sourceの承認には銘柄・種別・URL・承認者が必要です。")
    return {
        "stock_id": stock_id,
        "source_type": source_type,
        "source_url": source_url,
        "approved": bool(payload.get("approved")),
        "approved_by": approved_by,
    }


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


def build_trusted_source_review_rows(
    sources: Iterable[dict[str, Any]],
    approvals: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Add explicit UI action labels without performing persistence."""
    return [
        {
            **row,
            "review_action": "revoke" if row["trusted"] else "approve",
            "review_action_label": "承認を解除" if row["trusted"] else "明示承認",
            "human_confirmation_required": True,
        }
        for row in build_trusted_source_rows(sources, approvals)
    ]
