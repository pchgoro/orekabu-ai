"""Official EDINET API v2 metadata collection for registered stocks."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from services.automation import JobResult
from services.database import _now, connect, get_stocks
from utils.constants import DB_PATH

logger = logging.getLogger(__name__)
EDINET_API_URL = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
EDINET_REFERENCE_URL = "https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx"
SUPPORTED_DESCRIPTION_WORDS = (
    "有価証券報告書",
    "半期報告書",
    "臨時報告書",
    "大量保有報告書",
    "訂正",
)


def api_key_configured(env_path: Path | str | None = None) -> bool:
    """Return only whether an EDINET API key is configured."""
    if env_path is not None:
        load_dotenv(Path(env_path), override=False)
    return bool(os.getenv("EDINET_API_KEY", "").strip())


class EdinetApiClient:
    """Small standard-library client for the official EDINET API v2."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: int = 20,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not api_key.strip():
            raise ValueError("EDINET_API_KEYが設定されていません。")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.opener = opener

    def fetch_documents(self, target_date: date) -> list[dict[str, Any]]:
        """Fetch the document list for one date without downloading document bodies."""
        query = urllib.parse.urlencode(
            {"date": target_date.isoformat(), "type": "2", "Subscription-Key": self.api_key}
        )
        request = urllib.request.Request(
            f"{EDINET_API_URL}?{query}",
            headers={"User-Agent": "orekabu-ai/local-personal-use"},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"EDINET API HTTPエラー: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"EDINET API接続エラー: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("EDINET APIのJSONを解析できませんでした。") from exc
        metadata = payload.get("metadata") or {}
        if str(metadata.get("status") or "200") not in {"200", "0"}:
            raise RuntimeError(str(metadata.get("message") or "EDINET API error"))
        results = payload.get("results")
        return results if isinstance(results, list) else []


def normalize_security_code(value: Any) -> str:
    """Normalize EDINET's five-digit security code to a four-digit ticker code."""
    text = str(value or "").strip()
    return text[:4] if re.fullmatch(r"\d{5}", text) else ""


def normalize_stock_ticker_code(value: Any) -> str:
    """Return a four-digit numeric stock code or an empty string."""
    base = str(value or "").strip().upper().split(".", 1)[0]
    return base if re.fullmatch(r"\d{4}", base) else ""


def classify_document(description: str) -> str | None:
    """Return the supported report label inferred from EDINET's description."""
    text = str(description or "").strip()
    if not text or not any(word in text for word in SUPPORTED_DESCRIPTION_WORDS):
        return None
    if "訂正" in text:
        return "訂正書類"
    for label in SUPPORTED_DESCRIPTION_WORDS[:-1]:
        if label in text:
            return label
    return None


def filter_registered_documents(
    documents: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    *,
    ticker: str | None = None,
    limit: int | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """Match supported EDINET metadata to registered ticker codes."""
    selected = [stock for stock in stocks if ticker is None or stock["ticker"] == ticker]
    stock_by_code = {
        code: stock
        for stock in selected
        if (code := normalize_stock_ticker_code(stock.get("ticker")))
    }
    matches: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for document in documents:
        document_type = classify_document(str(document.get("docDescription") or ""))
        stock = stock_by_code.get(normalize_security_code(document.get("secCode")))
        if stock and document_type and document.get("docID"):
            matches.append((stock, document, document_type))
            if limit is not None and len(matches) >= max(0, int(limit)):
                break
    return matches


def count_security_matches(
    documents: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    *,
    ticker: str | None = None,
) -> int:
    """Count documents matching selected numeric stock codes before type filtering."""
    selected = [stock for stock in stocks if ticker is None or stock["ticker"] == ticker]
    codes = {
        code
        for stock in selected
        if (code := normalize_stock_ticker_code(stock.get("ticker")))
    }
    return sum(
        normalize_security_code(document.get("secCode")) in codes
        for document in documents
        if normalize_security_code(document.get("secCode"))
    )


def save_document(
    stock: dict[str, Any],
    document: dict[str, Any],
    document_type: str,
    db_path: Path | str = DB_PATH,
) -> str:
    """Save one EDINET metadata record using docID as the idempotency key."""
    doc_id = str(document.get("docID") or "").strip()
    if not doc_id:
        raise ValueError("docIDがありません。")
    reference_url = f"{EDINET_REFERENCE_URL}?{urllib.parse.quote(doc_id, safe='')}"
    now = _now()
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM edinet_documents WHERE doc_id=?", (doc_id,)
        ).fetchone()
        if existing:
            return "duplicate"
        conn.execute(
            """INSERT INTO edinet_documents
            (doc_id,stock_id,edinet_code,sec_code,filer_name,document_type,submitted_at,
             description,reference_url,retrieved_at,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                doc_id,
                stock["id"],
                str(document.get("edinetCode") or "").strip(),
                str(document.get("secCode") or "").strip(),
                str(document.get("filerName") or "").strip(),
                document_type,
                str(document.get("submitDateTime") or document.get("submitDate") or "").strip(),
                str(document.get("docDescription") or "").strip(),
                reference_url,
                now,
                now,
            ),
        )
    return "inserted"


def run_edinet_fetch(
    client: EdinetApiClient,
    *,
    target_date: date,
    ticker: str | None = None,
    limit: int = 50,
    dry_run: bool = False,
    db_path: Path | str = DB_PATH,
) -> JobResult:
    """Fetch and save registered-stock metadata while isolating row failures."""
    stocks = get_stocks(db_path)
    raw_documents = client.fetch_documents(target_date)
    security_matches = count_security_matches(raw_documents, stocks, ticker=ticker)
    matches = filter_registered_documents(
        raw_documents, stocks, ticker=ticker, limit=max(1, int(limit))
    )
    inserted = duplicates = failed = 0
    errors: list[str] = []
    if not dry_run:
        now = _now()
        with connect(db_path) as conn:
            run_id = int(
                conn.execute(
                    """INSERT INTO edinet_fetch_runs
                    (started_at,target_date,target_count,status,created_at)
                    VALUES (?,?,?,?,?)""",
                    (now, target_date.isoformat(), len(stocks), "running", now),
                ).lastrowid
            )
    else:
        run_id = None
    for stock, document, document_type in matches:
        try:
            status = "preview" if dry_run else save_document(
                stock, document, document_type, db_path
            )
            inserted += status in {"inserted", "preview"}
            duplicates += status == "duplicate"
            if run_id is not None:
                with connect(db_path) as conn:
                    conn.execute(
                        """INSERT INTO edinet_fetch_results
                        (fetch_run_id,stock_id,ticker,status,document_count,inserted_count,
                         duplicate_count,error_message,retrieved_at,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            run_id,
                            stock["id"],
                            stock["ticker"],
                            status,
                            1,
                            int(status == "inserted"),
                            int(status == "duplicate"),
                            "",
                            _now(),
                            _now(),
                        ),
                    )
        except Exception as exc:
            failed += 1
            errors.append(f"{stock['ticker']}: {exc}")
            logger.exception(
                "EDINET document save failed ticker=%s doc_id=%s",
                stock["ticker"],
                document.get("docID"),
            )
            if run_id is not None:
                with connect(db_path) as conn:
                    conn.execute(
                        """INSERT INTO edinet_fetch_results
                        (fetch_run_id,stock_id,ticker,status,document_count,inserted_count,
                         duplicate_count,error_message,retrieved_at,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            run_id,
                            stock["id"],
                            stock["ticker"],
                            "failed",
                            1,
                            0,
                            0,
                            f"{type(exc).__name__}: {exc}"[:1000],
                            _now(),
                            _now(),
                        ),
                    )
    if run_id is not None:
        status = "failed" if failed and not inserted else ("partial" if failed else "completed")
        with connect(db_path) as conn:
            conn.execute(
                """UPDATE edinet_fetch_runs SET finished_at=?,document_count=?,inserted_count=?,
                   duplicate_count=?,failed_count=?,status=?,error_summary=? WHERE id=?""",
                (
                    _now(),
                    len(matches),
                    inserted,
                    duplicates,
                    failed,
                    status,
                    " / ".join(errors)[:1000],
                    run_id,
                ),
            )
    return JobResult(
        processed=len(matches),
        inserted=inserted,
        duplicates=duplicates,
        failed=failed,
        message=" / ".join(errors),
        details={
            "target_date": target_date.isoformat(),
            "api_documents": len(raw_documents),
            "security_matches": security_matches,
            "target_documents": len(matches),
            "run_id": run_id,
        },
    )


def lookback_dates(today: date, days: int) -> list[date]:
    """Return today through the prior N-1 days in descending order."""
    count = int(days)
    if count < 1 or count > 365:
        raise ValueError("--lookback-daysは1から365で指定してください。")
    return [today - timedelta(days=offset) for offset in range(count)]


def run_edinet_range(
    client: EdinetApiClient,
    *,
    target_dates: list[date],
    ticker: str | None = None,
    limit: int = 50,
    dry_run: bool = False,
    db_path: Path | str = DB_PATH,
    interval_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> JobResult:
    """Fetch each date independently and continue after date-level failures."""
    totals = {
        "processed": 0,
        "inserted": 0,
        "duplicates": 0,
        "failed": 0,
        "api_documents": 0,
        "security_matches": 0,
        "target_documents": 0,
    }
    errors: list[str] = []
    daily: list[dict[str, Any]] = []
    dates = list(target_dates)
    for index, target_date in enumerate(dates):
        try:
            result = run_edinet_fetch(
                client,
                target_date=target_date,
                ticker=ticker,
                limit=limit,
                dry_run=dry_run,
                db_path=db_path,
            )
            row = {
                "date": target_date.isoformat(),
                "api_documents": int(result.details.get("api_documents", 0)),
                "security_matches": int(result.details.get("security_matches", 0)),
                "target_documents": int(result.details.get("target_documents", result.processed)),
                "inserted": result.inserted,
                "duplicates": result.duplicates,
                "failed": result.failed,
                "status": result.status,
            }
            totals["processed"] += result.processed
            totals["inserted"] += result.inserted
            totals["duplicates"] += result.duplicates
            totals["failed"] += result.failed
            totals["api_documents"] += row["api_documents"]
            totals["security_matches"] += row["security_matches"]
            totals["target_documents"] += row["target_documents"]
            if result.message:
                errors.append(f"{target_date.isoformat()}: {result.message}")
        except Exception as exc:
            row = {
                "date": target_date.isoformat(),
                "api_documents": 0,
                "security_matches": 0,
                "target_documents": 0,
                "inserted": 0,
                "duplicates": 0,
                "failed": 1,
                "status": "failed",
            }
            totals["failed"] += 1
            errors.append(f"{target_date.isoformat()}: {type(exc).__name__}: {exc}")
            logger.exception("EDINET date fetch failed target_date=%s", target_date)
        daily.append(row)
        if progress:
            progress(row)
        if index < len(dates) - 1 and interval_seconds > 0:
            sleep(float(interval_seconds))
    return JobResult(
        processed=totals["processed"],
        inserted=totals["inserted"],
        duplicates=totals["duplicates"],
        failed=totals["failed"],
        message=" / ".join(errors),
        details={
            "dates": daily,
            "api_documents": totals["api_documents"],
            "security_matches": totals["security_matches"],
            "target_documents": totals["target_documents"],
        },
    )


def list_documents(limit: int = 100, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List saved EDINET metadata newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT d.*,s.ticker,s.company_name FROM edinet_documents d
            JOIN stocks s ON s.id=d.stock_id
            ORDER BY d.submitted_at DESC,d.id DESC LIMIT ?""",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
    return [dict(row) for row in rows]


def list_fetch_runs(limit: int = 50, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List EDINET fetch runs."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM edinet_fetch_runs ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [dict(row) for row in rows]
