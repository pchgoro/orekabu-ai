"""Reviewable company profile candidates from free yfinance metadata."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import yfinance as yf

from services.automation import JobResult
from services.database import _now, connect, get_stocks
from utils.constants import DB_PATH

logger = logging.getLogger(__name__)
PROFILE_FIELDS = ("company_name", "company_alias", "market", "industry")
REVIEWABLE_STATUSES = {"pending", "held"}


class StockProfileProvider(Protocol):
    """Provider contract used by the CLI and tests."""

    name: str

    def fetch(self, ticker: str) -> dict[str, Any]:
        """Return normalized candidate fields."""


class YFinanceStockProfileProvider:
    """Read only the free company metadata already exposed by yfinance."""

    name = "yfinance"

    def fetch(self, ticker: str) -> dict[str, Any]:
        """Return a normalized candidate without changing the stocks table."""
        info = yf.Ticker(ticker).info or {}
        return {
            "company_name": str(info.get("longName") or "").strip(),
            "company_alias": str(info.get("shortName") or "").strip(),
            "market": str(info.get("fullExchangeName") or info.get("exchange") or "").strip(),
            "industry": str(info.get("industry") or "").strip(),
            "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }


def _fingerprint(stock_id: int, provider_name: str, candidate: dict[str, Any]) -> str:
    values = [
        stock_id,
        provider_name,
        candidate.get("company_name", ""),
        candidate.get("company_alias", ""),
        candidate.get("market", ""),
        candidate.get("industry", ""),
    ]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


def save_profile_candidate(
    stock: dict[str, Any],
    provider_name: str,
    candidate: dict[str, Any],
    db_path: Path | str = DB_PATH,
) -> str:
    """Save a new review candidate and never update confirmed stock fields."""
    if not any(str(candidate.get(key) or "").strip() for key in ("company_name", "company_alias", "market", "industry")):
        return "empty"
    fingerprint = _fingerprint(int(stock["id"]), provider_name, candidate)
    now = _now()
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM stock_profile_candidates WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if existing:
            return "duplicate"
        conn.execute(
            """INSERT INTO stock_profile_candidates
            (stock_id,provider_name,company_name,company_alias,market,industry,
             current_company_name,current_company_alias,current_market,current_industry,
             review_status,retrieved_at,fingerprint,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?,?,?)""",
            (
                stock["id"],
                provider_name,
                str(candidate.get("company_name") or "").strip(),
                str(candidate.get("company_alias") or "").strip(),
                str(candidate.get("market") or "").strip(),
                str(candidate.get("industry") or "").strip(),
                str(stock.get("company_name") or "").strip(),
                str(stock.get("company_alias") or "").strip(),
                str(stock.get("market") or "").strip(),
                str(stock.get("industry") or "").strip(),
                str(candidate.get("retrieved_at") or now),
                fingerprint,
                now,
                now,
            ),
        )
    return "inserted"


def run_profile_refresh(
    provider: StockProfileProvider,
    *,
    ticker: str | None = None,
    limit: int = 20,
    dry_run: bool = False,
    db_path: Path | str = DB_PATH,
    interval_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> JobResult:
    """Fetch profile candidates independently for registered stocks."""
    stocks = [stock for stock in get_stocks(db_path) if ticker is None or stock["ticker"] == ticker]
    targets = stocks[: max(1, int(limit))]
    inserted = duplicates = failed = 0
    errors: list[str] = []
    for index, stock in enumerate(targets):
        try:
            candidate = provider.fetch(stock["ticker"])
            status = "preview" if dry_run else save_profile_candidate(
                stock, provider.name, candidate, db_path
            )
            inserted += status in {"inserted", "preview"}
            duplicates += status in {"duplicate", "empty"}
        except Exception as exc:
            failed += 1
            errors.append(f"{stock['ticker']}: {exc}")
            logger.exception("Profile candidate fetch failed ticker=%s", stock["ticker"])
        if index < len(targets) - 1 and interval_seconds > 0:
            sleep(float(interval_seconds))
    return JobResult(
        processed=len(targets),
        inserted=inserted,
        duplicates=duplicates,
        failed=failed,
        message=" / ".join(errors),
    )


def list_profile_candidates(
    review_status: str | None = "pending",
    limit: int = 100,
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """List reviewable profile candidates."""
    where = "WHERE c.review_status=?" if review_status else ""
    params: tuple[Any, ...] = (review_status,) if review_status else ()
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT c.*,s.ticker,
            s.company_name AS live_company_name,
            s.company_alias AS live_company_alias,
            s.market AS live_market,
            s.industry AS live_industry
            FROM stock_profile_candidates c
            JOIN stocks s ON s.id=c.stock_id {where}
            ORDER BY c.retrieved_at DESC,c.id DESC LIMIT ?""",
            (*params, max(1, min(int(limit), 1000))),
        ).fetchall()
    return [dict(row) for row in rows]


def review_profile_candidate(
    candidate_id: int,
    action: str,
    *,
    approved_fields: list[str] | tuple[str, ...] | None = None,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Approve selected fields, hold, or reject a profile candidate atomically."""
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"approve", "hold", "reject"}:
        raise ValueError("候補の操作が不正です。")

    selected = tuple(dict.fromkeys(approved_fields or ()))
    if any(field not in PROFILE_FIELDS for field in selected):
        raise ValueError("承認対象の項目が不正です。")
    if normalized_action == "approve" and not selected:
        raise ValueError("承認する項目を1つ以上選択してください。")

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM stock_profile_candidates WHERE id=?",
            (int(candidate_id),),
        ).fetchone()
        if row is None:
            raise ValueError("企業情報候補が見つかりません。")
        candidate = dict(row)
        if candidate["review_status"] not in REVIEWABLE_STATUSES:
            raise ValueError("この候補はすでに確認済みです。")

        now = _now()
        if normalized_action == "approve":
            updates: dict[str, str] = {}
            for field in selected:
                value = str(candidate.get(field) or "").strip()
                if not value:
                    raise ValueError(f"{field}の候補値が空です。")
                updates[field] = value[:200]
            assignments = ", ".join(f"{field}=?" for field in updates)
            cursor = conn.execute(
                f"UPDATE stocks SET {assignments},updated_at=? WHERE id=?",
                (*updates.values(), now, int(candidate["stock_id"])),
            )
            if cursor.rowcount != 1:
                raise ValueError("更新対象の銘柄が見つかりません。")
            review_status = "approved"
        else:
            review_status = "held" if normalized_action == "hold" else "rejected"

        conn.execute(
            "UPDATE stock_profile_candidates SET review_status=?,updated_at=? WHERE id=?",
            (review_status, now, int(candidate_id)),
        )
    logger.info(
        "Profile candidate reviewed candidate_id=%s action=%s fields=%s",
        candidate_id,
        normalized_action,
        ",".join(selected),
    )
    return {
        "candidate_id": int(candidate_id),
        "status": review_status,
        "approved_fields": list(selected) if normalized_action == "approve" else [],
    }
