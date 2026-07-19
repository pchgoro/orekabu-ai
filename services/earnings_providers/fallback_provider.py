"""Ordered yfinance then official-IR earnings provider."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from services.database import get_stock
from services.earnings import japan_today
from services.earnings_ir_sources import (
    get_ir_source_for_ticker,
    latest_official_candidate,
    record_ir_source_result,
    source_is_due,
)
from services.earnings_providers.base import EarningsFetchResult, EarningsProvider
from services.earnings_providers.official_ir_provider import OfficialIREarningsProvider
from utils.constants import DB_PATH


class FallbackEarningsProvider:
    """Use official IR only when yfinance has no future date."""

    name = "yfinance+official_ir"

    def __init__(
        self,
        primary: EarningsProvider,
        *,
        db_path: Path | str = DB_PATH,
        persist_source_status: bool = True,
        force_ir: bool = False,
        today: date | None = None,
        official_provider_factory: Any = OfficialIREarningsProvider,
    ) -> None:
        self.primary = primary
        self.db_path = db_path
        self.persist_source_status = persist_source_status
        self.force_ir = force_ir
        self.today = today or japan_today()
        self.official_provider_factory = official_provider_factory
        self.stats = {
            "yfinance_success": 0,
            "ir_targets": 0,
            "ir_success": 0,
            "missing": [],
        }

    def fetch_next_earnings(self, ticker: str) -> EarningsFetchResult:
        """Return a future yfinance date or try one configured official IR source."""
        primary_result = self.primary.fetch_next_earnings(ticker)
        if _has_future_date(primary_result, self.today):
            self.stats["yfinance_success"] += 1
            return primary_result

        self.stats["ir_targets"] += 1
        source = get_ir_source_for_ticker(ticker, self.db_path)
        if source is None:
            self.stats["missing"].append(ticker)
            return _fallback_failure(
                ticker,
                "ir_source_missing",
                "yfinanceに将来日がなく、公式IR URLも未登録です。",
                primary_result,
            )
        if not source_is_due(source, force=self.force_ir):
            cached = latest_official_candidate(int(source["stock_id"]), self.db_path)
            if cached:
                self.stats["ir_success"] += 1
                candidate_date = date.fromisoformat(cached["candidate_date"])
                return EarningsFetchResult(
                    ticker=ticker,
                    earnings_date=candidate_date,
                    candidate_dates=(candidate_date,),
                    announcement_time=cached.get("announcement_time") or "",
                    fiscal_year=cached.get("fiscal_year"),
                    fiscal_quarter=cached.get("fiscal_quarter") or "未設定",
                    source_name="official_ir",
                    source_reference=cached.get("source_reference") or source["source_url"],
                    retrieved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    confidence=cached.get("confidence") or "unknown",
                    raw_payload_summary="24時間以内の公式IR候補を再利用",
                )
            return _fallback_failure(
                ticker,
                "ir_cache_active",
                "公式IRは24時間以内に確認済みです。",
                primary_result,
            )

        result = self.official_provider_factory(
            source,
            today=self.today,
        ).fetch_next_earnings(ticker)
        if self.persist_source_status:
            record_ir_source_result(
                int(source["id"]),
                success=result.succeeded,
                error="" if result.succeeded else result.error_message,
                db_path=self.db_path,
            )
        if result.succeeded:
            self.stats["ir_success"] += 1
            return result
        self.stats["missing"].append(ticker)
        return _fallback_failure(
            ticker,
            result.error_code or "ir_failed",
            result.error_message or "公式IRから決算予定日を取得できませんでした。",
            primary_result,
            source_reference=result.source_reference,
            summary=result.raw_payload_summary,
        )


def _has_future_date(result: EarningsFetchResult, today: date) -> bool:
    dates = result.candidate_dates or (
        (result.earnings_date,) if result.earnings_date else ()
    )
    return any(item >= today for item in dates)


def _fallback_failure(
    ticker: str,
    code: str,
    message: str,
    primary: EarningsFetchResult,
    *,
    source_reference: str = "",
    summary: str = "",
) -> EarningsFetchResult:
    return EarningsFetchResult(
        ticker=ticker,
        source_name="official_ir",
        source_reference=source_reference,
        retrieved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        confidence="unknown",
        error_code=code,
        error_message=message,
        raw_payload_summary=(
            f"yfinance={primary.error_code or 'future_dateなし'}"
            + (f" / IR={summary}" if summary else "")
        )[:1000],
    )


def build_default_earnings_provider(
    *,
    db_path: Path | str = DB_PATH,
    dry_run: bool = False,
    force_ir: bool = False,
) -> FallbackEarningsProvider:
    """Build the free ordered provider chain used by UI and CLI."""
    from services.earnings_providers.yfinance_provider import YFinanceEarningsProvider

    return FallbackEarningsProvider(
        YFinanceEarningsProvider(),
        db_path=db_path,
        persist_source_status=not dry_run,
        force_ir=force_ir,
    )
