"""Candidate persistence, review transactions, fetch runs, and CSV intake."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from services.database import _now, connect, get_stock
from services.earnings import get_stock_earnings, japan_today, parse_earnings_date
from services.earnings_providers.base import EarningsFetchResult, EarningsProvider
from services.earnings_providers.csv_provider import result_from_csv_row
from services.earnings_reconciliation import reconcile_candidate
from utils.constants import DB_PATH, EARNINGS_CONFIDENCE_LEVELS, EARNINGS_QUARTERS

logger = logging.getLogger(__name__)
_FETCH_LOCK = threading.Lock()
CANDIDATE_CSV_COLUMNS = ["ticker", "earnings_date", "announcement_time", "fiscal_year", "fiscal_quarter", "source_name", "source_reference", "confidence", "memo"]


def save_candidate(
    stock: dict[str, Any], result: EarningsFetchResult, candidate_date: Any,
    min_date_difference_days: int = 1, save_same: bool = False,
    include_confirmed_events: bool = True,
    db_path: Path | str = DB_PATH,
) -> tuple[str, int | None, str]:
    """Compare and save one candidate without updating formal earnings data."""
    parsed = parse_earnings_date(candidate_date)
    events = get_stock_earnings(int(stock["id"]), db_path)
    comparison = reconcile_candidate(
        parsed, result.fiscal_year, result.fiscal_quarter, result.announcement_time,
        events, min_date_difference_days,
    )
    if not include_confirmed_events and comparison.matched_event_id:
        matched = next((event for event in events if int(event["id"]) == comparison.matched_event_id), None)
        if matched and matched.get("date_status") == "確定":
            return "unchanged", None, "確定データは取得対象外です。"
    if comparison.comparison_status == "same" and not save_same:
        return "unchanged", None, comparison.warning
    fingerprint = _fingerprint(stock["id"], result, parsed)
    now = _now()
    try:
        with connect(db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO earnings_candidates
                (stock_id,provider_name,source_reference,candidate_date,announcement_time,fiscal_year,
                 fiscal_quarter,confidence,comparison_status,review_status,matched_earnings_event_id,
                 retrieved_at,reviewed_at,review_note,raw_payload_summary,fingerprint,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'pending',?,?,NULL,'',?,?,?,?)""",
                (
                    stock["id"], result.source_name, result.source_reference,
                    parsed.isoformat() if parsed else None, result.announcement_time,
                    result.fiscal_year, result.fiscal_quarter or "未設定", result.confidence,
                    comparison.comparison_status, comparison.matched_event_id, result.retrieved_at,
                    result.raw_payload_summary[:1000], fingerprint, now, now,
                ),
            )
            candidate_id = int(cursor.lastrowid)
        logger.info("決算候補作成 ticker=%s provider=%s comparison=%s candidate_id=%s", stock["ticker"], result.source_name, comparison.comparison_status, candidate_id)
        return "created", candidate_id, comparison.warning
    except sqlite3.IntegrityError:
        logger.info("決算候補重複 ticker=%s provider=%s date=%s", stock["ticker"], result.source_name, parsed)
        return "duplicate", None, "同一候補は保存済みです。"


def list_candidates(db_path: Path | str = DB_PATH, review_status: str | None = None) -> list[dict[str, Any]]:
    """List candidates with current formal event values for display."""
    where, params = ("WHERE c.review_status=?", [review_status]) if review_status else ("", [])
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT c.*, s.ticker, s.company_name, s.category, s.is_holding,
                e.earnings_date existing_date, e.announcement_time existing_time,
                e.fiscal_quarter existing_quarter, e.date_status existing_date_status
                FROM earnings_candidates c JOIN stocks s ON s.id=c.stock_id
                LEFT JOIN earnings_events e ON e.id=c.matched_earnings_event_id
                {where} ORDER BY CASE c.comparison_status WHEN 'conflict' THEN 0 WHEN 'date_changed' THEN 1
                WHEN 'new' THEN 2 ELSE 3 END, c.retrieved_at DESC""", params
        ).fetchall()
    return [dict(row) for row in rows]


def get_candidate(candidate_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return one joined candidate."""
    return next((row for row in list_candidates(db_path) if int(row["id"]) == int(candidate_id)), None)


def review_candidate(candidate_id: int, status: str, note: str = "", db_path: Path | str = DB_PATH) -> None:
    """Mark a candidate held or rejected without touching formal data."""
    if status not in {"held", "rejected"}:
        raise ValueError("確認状態が不正です。")
    with connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE earnings_candidates SET review_status=?,reviewed_at=?,review_note=?,updated_at=? WHERE id=? AND review_status='pending'",
            (status, _now(), note.strip(), _now(), candidate_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("候補が存在しないか、すでに確認済みです。")
    logger.info("決算候補確認 candidate_id=%s status=%s", candidate_id, status)


def approve_candidate(
    candidate_id: int, action: str, confirm_fixed_update: bool = False,
    note: str = "", db_path: Path | str = DB_PATH,
) -> int | None:
    """Apply an approved candidate and review state in one transaction."""
    allowed = {"new_event", "update_existing", "date_only", "time_only", "quarter_only", "keep_existing"}
    if action not in allowed:
        raise ValueError("承認方法が不正です。")
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM earnings_candidates WHERE id=? AND review_status='pending'", (candidate_id,)).fetchone()
        if row is None:
            raise ValueError("候補が存在しないか、すでに確認済みです。")
        candidate = dict(row)
        event_id = candidate.get("matched_earnings_event_id")
        event = conn.execute("SELECT * FROM earnings_events WHERE id=?", (event_id,)).fetchone() if event_id else None
        if event_id and event is None and action != "new_event":
            raise ValueError("更新対象の既存決算が削除されています。")
        if event and event["date_status"] == "確定" and action not in {"keep_existing", "new_event"} and not confirm_fixed_update:
            raise ValueError("確定データの更新には追加確認が必要です。")
        now = _now()
        if action == "new_event":
            if not candidate.get("candidate_date"):
                raise ValueError("候補日がないため新規登録できません。")
            cursor = conn.execute(
                """INSERT INTO earnings_events
                (stock_id,fiscal_year,fiscal_quarter,earnings_date,announcement_time,date_status,memo,created_at,updated_at)
                VALUES (?,?,?,?,?,'予定',?,?,?)""",
                (
                    candidate["stock_id"], candidate.get("fiscal_year") or int(candidate["candidate_date"][:4]),
                    candidate.get("fiscal_quarter") or "未設定", candidate["candidate_date"],
                    candidate.get("announcement_time") or "", "外部候補を承認して登録", now, now,
                ),
            )
            event_id = int(cursor.lastrowid)
        elif action != "keep_existing":
            updates: dict[str, Any] = {}
            if action in {"update_existing", "date_only"}:
                if not candidate.get("candidate_date"):
                    raise ValueError("候補日がありません。")
                updates["earnings_date"] = candidate["candidate_date"]
            if action in {"update_existing", "time_only"}:
                updates["announcement_time"] = candidate.get("announcement_time") or ""
            if action in {"update_existing", "quarter_only"}:
                updates["fiscal_quarter"] = candidate.get("fiscal_quarter") or "未設定"
            if not updates:
                raise ValueError("更新項目がありません。")
            assignments = ",".join(f"{key}=?" for key in updates)
            conn.execute(f"UPDATE earnings_events SET {assignments},updated_at=? WHERE id=?", (*updates.values(), now, event_id))
        conn.execute(
            """UPDATE earnings_candidates SET review_status='approved',matched_earnings_event_id=?,
               reviewed_at=?,review_note=?,updated_at=? WHERE id=?""",
            (event_id, now, note.strip(), now, candidate_id),
        )
    logger.info("決算候補承認 candidate_id=%s action=%s event_id=%s", candidate_id, action, event_id)
    return int(event_id) if event_id else None


def start_fetch_run(provider_name: str, target_count: int, db_path: Path | str = DB_PATH) -> int:
    """Create an auditable fetch run."""
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO earnings_fetch_runs (provider_name,started_at,target_count,status,created_at) VALUES (?,?,?,'running',?)",
            (provider_name, now, target_count, now),
        )
        return int(cursor.lastrowid)


def add_fetch_result(run_id: int, stock: dict[str, Any], status: str, candidate_id: int | None = None, error_code: str = "", error_message: str = "", retrieved_at: str = "", db_path: Path | str = DB_PATH) -> None:
    """Store one ticker result for a fetch run."""
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO earnings_fetch_results
            (fetch_run_id,stock_id,ticker,status,candidate_id,error_code,error_message,retrieved_at,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_id, stock["id"], stock["ticker"], status, candidate_id, error_code, error_message[:500], retrieved_at or _now(), _now()),
        )


def finish_fetch_run(run_id: int, counts: dict[str, int], errors: list[str], db_path: Path | str = DB_PATH) -> None:
    """Finish a fetch run with success, partial, or failed state."""
    failed = counts.get("failed", 0)
    status = "failed" if failed and not counts.get("success", 0) else ("partial" if failed else "completed")
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE earnings_fetch_runs SET finished_at=?,success_count=?,candidate_count=?,
               unchanged_count=?,failed_count=?,status=?,error_summary=? WHERE id=?""",
            (_now(), counts.get("success", 0), counts.get("candidates", 0), counts.get("unchanged", 0), failed, status, " / ".join(errors)[:1000], run_id),
        )


def list_fetch_runs(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List fetch runs newest first."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM earnings_fetch_runs ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def list_fetch_results(run_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List ticker results for one run."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM earnings_fetch_results WHERE fetch_run_id=? ORDER BY id", (run_id,)).fetchall()
    return [dict(row) for row in rows]


def run_candidate_fetch(
    stocks: list[dict[str, Any]], provider: EarningsProvider, settings: dict[str, Any],
    db_path: Path | str = DB_PATH, progress: Callable[[int, int, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep, force_fetch: bool = False,
) -> dict[str, Any]:
    """Fetch candidates explicitly, with limits, cache, isolation, and audit history."""
    if not _FETCH_LOCK.acquire(blocking=False):
        raise RuntimeError("決算候補の取得処理はすでに実行中です。")
    auto = settings.get("earnings_auto_fetch", settings)
    targets = stocks[: int(auto.get("max_tickers_per_run", 20))]
    run_id = start_fetch_run(provider.name, len(targets), db_path)
    counts = {"success": 0, "candidates": 0, "unchanged": 0, "failed": 0, "cached": 0}
    errors: list[str] = []
    logger.info("決算候補取得開始 run_id=%s provider=%s target_count=%s", run_id, provider.name, len(targets))
    try:
        for index, stock in enumerate(targets, start=1):
            ticker = stock["ticker"]
            if progress:
                progress(index, len(targets), ticker)
            if not force_fetch and not _can_fetch(stock["id"], int(auto.get("cache_hours", 6)), db_path):
                counts["cached"] += 1
                add_fetch_result(run_id, stock, "cached", error_message="キャッシュ期間内です。", db_path=db_path)
                continue
            try:
                result = provider.fetch_next_earnings(ticker)
            except Exception as exc:
                counts["failed"] += 1
                message = "プロバイダー処理で予期しないエラーが発生しました。"
                errors.append(f"{ticker}: {message}")
                add_fetch_result(run_id, stock, "failed", error_code="provider_error", error_message=message, db_path=db_path)
                logger.exception("決算候補プロバイダー例外 ticker=%s provider=%s", ticker, provider.name)
                continue
            if not result.succeeded:
                counts["failed"] += 1
                errors.append(f"{ticker}: {result.error_message}")
                add_fetch_result(run_id, stock, "failed", error_code=result.error_code, error_message=result.error_message, retrieved_at=result.retrieved_at, db_path=db_path)
                logger.warning("決算候補取得失敗 ticker=%s provider=%s code=%s", ticker, provider.name, result.error_code)
            else:
                counts["success"] += 1
                candidate_dates = result.candidate_dates or ((result.earnings_date,) if result.earnings_date else ())
                last_candidate_id = None
                result_status = "unchanged"
                for candidate_date in candidate_dates:
                    status, candidate_id, warning = save_candidate(
                        stock, result, candidate_date, int(auto.get("date_change_min_days", 1)),
                        bool(auto.get("save_same_candidates", False)),
                        bool(auto.get("include_confirmed_events", True)), db_path,
                    )
                    if status == "created":
                        counts["candidates"] += 1
                        last_candidate_id, result_status = candidate_id, "candidate_created"
                    elif status == "unchanged":
                        counts["unchanged"] += 1
                    elif status == "duplicate":
                        result_status = "duplicate"
                add_fetch_result(run_id, stock, result_status, last_candidate_id, retrieved_at=result.retrieved_at, db_path=db_path)
            if index < len(targets):
                sleep(float(auto.get("request_interval_seconds", 1.0)))
        finish_fetch_run(run_id, counts, errors, db_path)
        logger.info("決算候補取得終了 run_id=%s counts=%s", run_id, counts)
        return {
            "run_id": run_id,
            "counts": counts,
            "errors": errors,
            "provider_stats": getattr(provider, "stats", {}),
        }
    except Exception:
        logger.exception("決算候補一括取得エラー run_id=%s", run_id)
        counts["failed"] += 1
        errors.append("取得処理全体でエラーが発生しました。")
        finish_fetch_run(run_id, counts, errors, db_path)
        raise
    finally:
        _FETCH_LOCK.release()


def candidate_dashboard_summary(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Return compact candidate/fetch summary for the dashboard."""
    with connect(db_path) as conn:
        pending = conn.execute("SELECT COUNT(*) FROM earnings_candidates WHERE review_status='pending'").fetchone()[0]
        changed = conn.execute("SELECT COUNT(*) FROM earnings_candidates WHERE review_status='pending' AND comparison_status='date_changed'").fetchone()[0]
        conflicts = conn.execute("SELECT COUNT(*) FROM earnings_candidates WHERE review_status='pending' AND comparison_status='conflict'").fetchone()[0]
        run = conn.execute("SELECT finished_at,failed_count FROM earnings_fetch_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {"pending": pending, "date_changed": changed, "conflicts": conflicts, "last_fetched_at": run["finished_at"] if run else None, "last_failed": run["failed_count"] if run else 0}


def purge_reviewed_candidates(retention_days: int, db_path: Path | str = DB_PATH) -> int:
    """Delete only old reviewed candidates; pending candidates and formal events are untouched."""
    threshold = (datetime.now().astimezone() - timedelta(days=max(1, retention_days))).isoformat(timespec="seconds")
    with connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM earnings_candidates WHERE review_status<>'pending' AND reviewed_at IS NOT NULL AND reviewed_at<?",
            (threshold,),
        )
        deleted = int(cursor.rowcount)
    logger.info("確認済み決算候補整理 retention_days=%s deleted=%s", retention_days, deleted)
    return deleted


def build_fetch_targets(
    stocks: list[dict[str, Any]], mode: str, selected_stock_id: int | None = None,
    include_related: bool = True, within_days: int = 30, stale_days: int = 7,
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """Select explicit fetch targets from a user-facing mode."""
    targets = list(stocks)
    if not include_related:
        targets = [stock for stock in targets if stock.get("category") != "関連銘柄"]
    if mode == "個別銘柄":
        targets = [stock for stock in targets if int(stock["id"]) == int(selected_stock_id or -1)]
    elif mode == "保有株のみ":
        targets = [stock for stock in targets if stock.get("is_holding")]
    elif mode == "監視銘柄のみ":
        targets = [stock for stock in targets if not stock.get("is_holding")]
    elif mode in {"決算日未登録のみ", "決算日が一定期間内"}:
        from services.earnings import next_earnings_by_stock

        next_map = next_earnings_by_stock(db_path)
        if mode == "決算日未登録のみ":
            targets = [stock for stock in targets if int(stock["id"]) not in next_map or not next_map[int(stock["id"])].get("earnings_date")]
        else:
            limit = japan_today() + timedelta(days=max(0, within_days))
            targets = [stock for stock in targets if (event := next_map.get(int(stock["id"]))) and event.get("earnings_date") and parse_earnings_date(event["earnings_date"]) <= limit]
    elif mode == "最終取得から一定日数経過":
        threshold = (datetime.now().astimezone() - timedelta(days=max(1, stale_days))).isoformat(timespec="seconds")
        with connect(db_path) as conn:
            latest = {int(row["stock_id"]): row["retrieved_at"] for row in conn.execute("SELECT stock_id,MAX(retrieved_at) retrieved_at FROM earnings_fetch_results GROUP BY stock_id").fetchall()}
        targets = [stock for stock in targets if int(stock["id"]) not in latest or latest[int(stock["id"])] < threshold]
    return sorted(targets, key=lambda stock: stock["ticker"])


def parse_candidate_csv(uploaded_file: Any) -> tuple[pd.DataFrame, list[str]]:
    """Parse a BOM-compatible candidate CSV for preview."""
    try:
        rows = list(csv.DictReader(io.StringIO(uploaded_file.getvalue().decode("utf-8-sig"))))
        frame = pd.DataFrame(rows)
        missing = [column for column in CANDIDATE_CSV_COLUMNS if column not in frame.columns]
        return (frame, [f"CSV列が不足しています: {', '.join(missing)}"]) if missing else (frame[CANDIDATE_CSV_COLUMNS], [])
    except Exception as exc:
        logger.exception("決算候補CSV読み込みエラー")
        return pd.DataFrame(), [f"CSVを読み込めませんでした: {exc}"]


def validate_candidate_csv_preview(frame: pd.DataFrame, db_path: Path | str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split candidate CSV preview into valid and invalid rows before import."""
    valid_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        values = row.to_dict()
        try:
            normalized = result_from_csv_row(values)
            if get_stock(normalized.ticker, db_path) is None:
                raise ValueError("登録銘柄に存在しないtickerです。")
            if normalized.confidence not in EARNINGS_CONFIDENCE_LEVELS:
                raise ValueError("信頼度が不正です。")
            if normalized.fiscal_quarter not in EARNINGS_QUARTERS:
                raise ValueError("四半期が不正です。")
            valid_rows.append(values)
        except Exception as exc:
            invalid_rows.append({**values, "行番号": int(index) + 2, "エラー理由": str(exc)})
    return pd.DataFrame(valid_rows, columns=frame.columns), pd.DataFrame(invalid_rows)


def import_candidate_csv(frame: pd.DataFrame, settings: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Import CSV rows into candidates only, never formal events."""
    result: dict[str, Any] = {"created": 0, "duplicate": 0, "warnings": 0, "failed": 0, "errors": []}
    auto = settings.get("earnings_auto_fetch", settings)
    for index, row in frame.iterrows():
        line = int(index) + 2
        try:
            normalized = result_from_csv_row(row.to_dict())
            stock = get_stock(normalized.ticker, db_path)
            if stock is None:
                raise ValueError("登録銘柄に存在しないtickerです。")
            if normalized.confidence not in EARNINGS_CONFIDENCE_LEVELS:
                raise ValueError("信頼度が不正です。")
            if normalized.fiscal_quarter not in EARNINGS_QUARTERS:
                raise ValueError("四半期が不正です。")
            status, _, warning = save_candidate(
                stock, normalized, normalized.earnings_date,
                int(auto.get("date_change_min_days", 1)), bool(auto.get("save_same_candidates", False)),
                bool(auto.get("include_confirmed_events", True)), db_path,
            )
            if status == "created":
                result["created"] += 1
                if normalized.earnings_date and normalized.earnings_date < japan_today():
                    result["warnings"] += 1
            elif status in {"duplicate", "unchanged"}:
                result["duplicate"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{line}行目: {exc}")
            logger.exception("決算候補CSV行エラー line=%s", line)
    return result


def _fingerprint(stock_id: int, result: EarningsFetchResult, candidate_date: Any) -> str:
    raw = "|".join(str(value or "") for value in (stock_id, result.source_name, candidate_date, result.fiscal_year, result.fiscal_quarter, result.announcement_time))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _can_fetch(stock_id: int, cache_hours: int, db_path: Path | str) -> bool:
    threshold = (datetime.now().astimezone() - timedelta(hours=max(1, cache_hours))).isoformat(timespec="seconds")
    with connect(db_path) as conn:
        row = conn.execute("SELECT retrieved_at FROM earnings_fetch_results WHERE stock_id=? AND status<>'cached' ORDER BY id DESC LIMIT 1", (stock_id,)).fetchone()
    return row is None or not row["retrieved_at"] or row["retrieved_at"] < threshold
