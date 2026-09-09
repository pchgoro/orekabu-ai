"""Explicit, non-learning trusted-source view models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from services.database import _now, connect
from services.news import canonicalize_url
from utils.constants import DB_PATH


def _is_explicitly_approved(value: Any) -> bool:
    """Accept only the persisted boolean forms, never arbitrary truthy strings."""
    return value is True or (isinstance(value, int) and not isinstance(value, bool) and value == 1)


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
        if _is_explicitly_approved(row.get("approved"))
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


def list_trusted_source_approvals(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return the latest explicit approval state for each logical source key."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT e.* FROM trusted_source_approval_events e
            JOIN (
                SELECT stock_id, source_type, source_url, MAX(id) AS latest_id
                FROM trusted_source_approval_events
                GROUP BY stock_id, source_type, source_url
            ) latest ON latest.latest_id=e.id
            ORDER BY e.stock_id, e.source_type, e.source_url"""
        ).fetchall()
    return [dict(row) for row in rows]


def set_trusted_source_approval(
    payload: dict[str, Any],
    *,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Append an explicit approval/revoke event; identical current state is idempotent."""
    item = normalize_trusted_source_approval(payload)
    with connect(db_path) as conn:
        stock = conn.execute("SELECT id FROM stocks WHERE id=?", (item["stock_id"],)).fetchone()
        if stock is None:
            raise ValueError("登録済みの銘柄を指定してください。")
        previous = conn.execute(
            """SELECT approved, approved_by, approved_at FROM trusted_source_approval_events
            WHERE stock_id=? AND source_type=? AND source_url=? ORDER BY id DESC LIMIT 1""",
            (item["stock_id"], item["source_type"], item["source_url"]),
        ).fetchone()
        if previous is not None and bool(previous["approved"]) == item["approved"]:
            return {"changed": False, **item, "approved_at": previous["approved_at"]}
        approved_at = _now()
        conn.execute(
            """INSERT INTO trusted_source_approval_events
            (stock_id,source_type,source_url,approved,approved_by,approved_at)
            VALUES(?,?,?,?,?,?)""",
            (item["stock_id"], item["source_type"], item["source_url"], int(item["approved"]), item["approved_by"], approved_at),
        )
    return {"changed": True, **item, "approved_at": approved_at}
