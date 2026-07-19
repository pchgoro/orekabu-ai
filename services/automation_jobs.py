"""Adapters that expose existing data collectors as automation jobs."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from services.automation import JobResult
from services.database import connect, get_stocks, load_settings
from services.earnings_candidates import purge_reviewed_candidates, run_candidate_fetch
from services.earnings_providers.base import EarningsProvider
from services.news import fetch_enabled_sources, list_sources
from services.news_providers.base import NewsProvider
from utils.constants import DB_PATH


def select_earnings_targets(
    stocks: list[dict[str, Any]],
    *,
    ticker: str | None = None,
    limit: int = 20,
    include_all_holdings: bool = False,
) -> list[dict[str, Any]]:
    """Select earnings targets while allowing daily jobs to cover every holding."""
    if ticker is not None:
        return [stock for stock in stocks if stock["ticker"] == ticker][:1]
    safe_limit = max(1, int(limit))
    if not include_all_holdings:
        return stocks[:safe_limit]
    holdings = [stock for stock in stocks if stock.get("is_holding")]
    watching = [stock for stock in stocks if not stock.get("is_holding")]
    remaining = max(0, safe_limit - len(holdings))
    return [*holdings, *watching[:remaining]]


def run_news_job(
    provider_factory: Callable[[dict[str, Any]], NewsProvider],
    *,
    limit: int = 20,
    dry_run: bool = False,
    db_path: Path | str = DB_PATH,
) -> JobResult:
    """Fetch enabled RSS/Atom sources, preserving existing deduplication behavior."""
    enabled = [
        source
        for source in list_sources(db_path)
        if source["is_enabled"] and source["source_type"] in {"RSS", "Atom"}
    ][: max(1, int(limit))]
    if dry_run:
        processed = articles = failed = 0
        errors: list[str] = []
        for source in enabled:
            processed += 1
            try:
                articles += len(provider_factory(source).fetch())
            except Exception as exc:
                failed += 1
                errors.append(f"{source['name']}: {exc}")
        return JobResult(
            processed=processed,
            inserted=articles,
            failed=failed,
            message=" / ".join(errors),
        )

    result = fetch_enabled_sources(
        provider_factory,
        db_path,
        sources=enabled,
        interval_seconds=1.0,
    )
    return JobResult(
        processed=len(enabled),
        inserted=int(result["inserted"]),
        duplicates=int(result["duplicates"]),
        failed=int(result["failed"]),
        message=" / ".join(result["errors"]),
        details={"run_id": result["run_id"]},
    )


def run_earnings_job(
    provider: EarningsProvider,
    *,
    ticker: str | None = None,
    limit: int = 20,
    force: bool = False,
    dry_run: bool = False,
    include_all_holdings: bool = False,
    db_path: Path | str = DB_PATH,
) -> JobResult:
    """Fetch yfinance earnings candidates without touching formal earnings events."""
    targets = select_earnings_targets(
        get_stocks(db_path),
        ticker=ticker,
        limit=limit,
        include_all_holdings=include_all_holdings,
    )
    if dry_run:
        succeeded = failed = candidates = 0
        errors: list[str] = []
        for stock in targets:
            try:
                result = provider.fetch_next_earnings(stock["ticker"])
                if result.succeeded:
                    succeeded += 1
                    candidates += len(result.candidate_dates or ((result.earnings_date,) if result.earnings_date else ()))
                else:
                    failed += 1
                    errors.append(f"{stock['ticker']}: {result.error_code}")
            except Exception as exc:
                failed += 1
                errors.append(f"{stock['ticker']}: {exc}")
        return JobResult(
            processed=len(targets),
            inserted=candidates,
            failed=failed,
            message=" / ".join(errors),
            details={"succeeded": succeeded},
        )

    settings = load_settings(db_path)
    settings["earnings_auto_fetch"]["max_tickers_per_run"] = len(targets)
    settings["earnings_auto_fetch"]["request_interval_seconds"] = 1.0
    result = run_candidate_fetch(
        targets,
        provider,
        settings,
        db_path,
        sleep=time.sleep,
        force_fetch=force,
    )
    counts = result["counts"]
    provider_stats = result.get("provider_stats", {})
    return JobResult(
        processed=len(targets),
        inserted=int(counts["candidates"]),
        duplicates=int(counts["unchanged"]) + int(counts["cached"]),
        failed=int(counts["failed"]),
        message=" / ".join(result["errors"]),
        details={
            "run_id": result["run_id"],
            "target_count": len(targets),
            "holding_count": sum(bool(stock.get("is_holding")) for stock in targets),
            "yfinance_success": int(provider_stats.get("yfinance_success", 0)),
            "ir_targets": int(provider_stats.get("ir_targets", 0)),
            "ir_success": int(provider_stats.get("ir_success", 0)),
            "missing_tickers": list(provider_stats.get("missing", [])),
        },
    )


def run_candidate_cleanup(
    retention_days: int,
    *,
    dry_run: bool = False,
    db_path: Path | str = DB_PATH,
) -> JobResult:
    """Remove only old reviewed earnings candidates, never pending or formal data."""
    if dry_run:
        threshold = (
            datetime.now().astimezone() - timedelta(days=max(1, int(retention_days)))
        ).isoformat(timespec="seconds")
        with connect(db_path) as conn:
            count = int(
                conn.execute(
                    """SELECT COUNT(*) FROM earnings_candidates
                    WHERE review_status<>'pending' AND reviewed_at IS NOT NULL AND reviewed_at<?""",
                    (threshold,),
                ).fetchone()[0]
            )
        return JobResult(processed=count, inserted=0, message=f"削除候補 {count}件")
    deleted = purge_reviewed_candidates(retention_days, db_path)
    return JobResult(processed=deleted, inserted=0, message=f"削除 {deleted}件")
