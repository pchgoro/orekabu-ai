"""Disclosure validation, persistence, CSV, linking, and prompt services."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

from services.database import connect
from utils.constants import (
    DB_PATH,
    DISCLOSURE_IMPORTANCE_LEVELS,
    DISCLOSURE_MAX_FILE_SIZE,
    DISCLOSURE_TYPES,
)
from utils.validators import normalize_ticker

logger = logging.getLogger(__name__)
DISCLOSURE_DIR = Path(__file__).resolve().parents[1] / "data" / "disclosures"
CSV_COLUMNS = [
    "ticker", "disclosure_type", "title", "disclosed_at", "source_name",
    "source_url", "document_url", "summary", "importance", "tags", "memo", "external_id",
]


def validate_web_url(value: Any, *, allow_empty: bool = True) -> str:
    """Allow only public-looking HTTP(S) URLs without credentials or file access."""
    url = str(value or "").strip()
    if not url and allow_empty:
        return ""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError
        host = parts.hostname.casefold()
        if host == "localhost" or host.endswith(".local"):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                raise ValueError
        except ValueError as exc:
            if host.replace(".", "").isdigit() or ":" in host:
                raise ValueError("安全な公開HTTP(S) URLを入力してください。") from exc
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("安全な公開HTTP(S) URLを入力してください。") from exc


def validate_local_pdf(path_value: Any, allowed_dir: Path = DISCLOSURE_DIR) -> str:
    """Accept an existing PDF only when it resolves below the configured directory."""
    value = str(path_value or "").strip()
    if not value:
        return ""
    if value.casefold().startswith("file:"):
        raise ValueError("file URLは使用できません。")
    root = allowed_dir.resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("PDFは指定ディレクトリ配下のみ参照できます。") from exc
    if candidate.suffix.casefold() != ".pdf":
        raise ValueError("PDFファイルだけを指定できます。")
    if not candidate.is_file():
        raise ValueError("指定したPDFが見つかりません。")
    if candidate.stat().st_size > DISCLOSURE_MAX_FILE_SIZE:
        raise ValueError("PDFのサイズ上限は10MBです。")
    try:
        with candidate.open("rb") as pdf_file:
            signature = pdf_file.read(5)
        if signature != b"%PDF-":
            raise ValueError("有効なPDFファイルではありません。")
    except OSError as exc:
        raise ValueError("PDFファイルを読み込めません。") from exc
    return str(candidate)


def save_uploaded_pdf(name: str, content: bytes, allowed_dir: Path = DISCLOSURE_DIR) -> str:
    """Save a validated upload below the disclosure directory without trusting its filename."""
    if Path(name or "").suffix.casefold() != ".pdf":
        raise ValueError("PDFファイルだけをアップロードできます。")
    if not content.startswith(b"%PDF-"):
        raise ValueError("有効なPDFファイルではありません。")
    if len(content) > DISCLOSURE_MAX_FILE_SIZE:
        raise ValueError("PDFのサイズ上限は10MBです。")
    allowed_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem)[:60] or "disclosure"
    digest = hashlib.sha256(content).hexdigest()[:12]
    target = (allowed_dir / f"{safe_stem}_{digest}.pdf").resolve()
    target.relative_to(allowed_dir.resolve())
    if not target.exists():
        target.write_bytes(content)
    return str(target)


def sanitize_text(value: Any, limit: int = 10000) -> str:
    """Store plain text by removing markup and control characters."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()[:limit]


def disclosure_hash(payload: dict[str, Any]) -> str:
    """Build a SHA-256 key using the documented duplicate precedence."""
    external_id = sanitize_text(payload.get("external_id"), 500)
    document_url = validate_web_url(payload.get("document_url"))
    source_url = validate_web_url(payload.get("source_url"))
    if external_id:
        basis = f"external:{external_id}"
    elif document_url:
        basis = f"document:{document_url.casefold()}"
    elif source_url:
        basis = f"source:{source_url.casefold()}"
    else:
        basis = "fallback:{ticker}|{title}|{disclosed_at}".format(
            ticker=str(payload.get("ticker") or payload.get("stock_id") or ""),
            title=sanitize_text(payload.get("title"), 1000).casefold(),
            disclosed_at=str(payload.get("disclosed_at") or ""),
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def validate_payload(payload: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Validate and normalize a disclosure payload without writing it."""
    stock_id = payload.get("stock_id")
    ticker = payload.get("ticker")
    with connect(db_path) as conn:
        if stock_id:
            stock = conn.execute("SELECT id,ticker FROM stocks WHERE id=?", (int(stock_id),)).fetchone()
        else:
            normalized = normalize_ticker(str(ticker or ""))
            stock = conn.execute("SELECT id,ticker FROM stocks WHERE ticker=?", (normalized,)).fetchone()
    if not stock:
        raise ValueError("登録済みの銘柄を指定してください。")
    disclosure_type = str(payload.get("disclosure_type") or "")
    importance = str(payload.get("importance") or "通常")
    if disclosure_type not in DISCLOSURE_TYPES:
        raise ValueError("開示種別が不正です。")
    if importance not in DISCLOSURE_IMPORTANCE_LEVELS:
        raise ValueError("重要度が不正です。")
    title = sanitize_text(payload.get("title"), 1000)
    if not title:
        raise ValueError("タイトルを入力してください。")
    disclosed_at = _normalize_datetime(payload.get("disclosed_at"))
    local_path = validate_local_pdf(payload.get("local_file_path")) if payload.get("local_file_path") else ""
    item = {
        "stock_id": int(stock["id"]), "ticker": str(stock["ticker"]),
        "disclosure_type": disclosure_type, "title": title, "disclosed_at": disclosed_at,
        "source_name": sanitize_text(payload.get("source_name"), 300),
        "source_url": validate_web_url(payload.get("source_url")),
        "document_url": validate_web_url(payload.get("document_url")),
        "local_file_path": local_path,
        "summary": sanitize_text(payload.get("summary")), "importance": importance,
        "is_read": bool(payload.get("is_read", False)), "is_favorite": bool(payload.get("is_favorite", False)),
        "user_memo": sanitize_text(payload.get("user_memo", payload.get("memo"))),
        "external_id": sanitize_text(payload.get("external_id"), 500),
    }
    item["content_hash"] = disclosure_hash(item)
    return item


def save_disclosure(payload: dict[str, Any], update_existing: bool = False, db_path: Path | str = DB_PATH) -> tuple[str, int]:
    """Insert a disclosure or optionally update its detected duplicate."""
    item = validate_payload(payload, db_path)
    now = _now()
    with connect(db_path) as conn:
        existing = conn.execute("SELECT id FROM disclosures WHERE content_hash=?", (item["content_hash"],)).fetchone()
        if existing:
            if not update_existing:
                return "duplicate", int(existing["id"])
            _update_row(conn, int(existing["id"]), item, now)
            disclosure_id = int(existing["id"])
            status = "updated"
        else:
            cursor = conn.execute(
                """INSERT INTO disclosures
                (stock_id,disclosure_type,title,disclosed_at,source_name,source_url,document_url,local_file_path,
                 summary,importance,is_read,is_favorite,user_memo,external_id,content_hash,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                _values(item) + (now, now),
            )
            disclosure_id = int(cursor.lastrowid)
            status = "inserted"
        _match_news(conn, disclosure_id, item)
    return status, disclosure_id


def update_disclosure(disclosure_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Update an existing disclosure and refresh unconfirmed news candidates."""
    item = validate_payload(payload, db_path)
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM disclosures WHERE id=?", (disclosure_id,)).fetchone():
            raise ValueError("更新対象の開示がありません。")
        duplicate = conn.execute("SELECT id FROM disclosures WHERE content_hash=? AND id<>?", (item["content_hash"], disclosure_id)).fetchone()
        if duplicate:
            raise ValueError("同じ開示が登録済みです。")
        _update_row(conn, disclosure_id, item, _now())
        conn.execute("DELETE FROM disclosure_news_links WHERE disclosure_id=? AND confirmed=0", (disclosure_id,))
        _match_news(conn, disclosure_id, item)


def delete_disclosure(disclosure_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete one disclosure; referenced PDF files are intentionally retained."""
    with connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM disclosures WHERE id=?", (disclosure_id,))
        if cursor.rowcount == 0:
            raise ValueError("削除対象の開示がありません。")


def list_disclosures(db_path: Path | str = DB_PATH, filter_name: str = "最新") -> list[dict[str, Any]]:
    """Return disclosure view rows with stock and tag labels."""
    where = ""
    if filter_name == "保有株": where = "WHERE s.is_holding=1"
    elif filter_name == "監視銘柄": where = "WHERE s.is_holding=0"
    elif filter_name == "未読": where = "WHERE d.is_read=0"
    elif filter_name == "お気に入り": where = "WHERE d.is_favorite=1"
    with connect(db_path) as conn:
        rows = conn.execute(f"""
            SELECT d.*,s.ticker,s.company_name,s.is_holding,
              COALESCE(GROUP_CONCAT(DISTINCT t.name),'') AS tags
            FROM disclosures d JOIN stocks s ON s.id=d.stock_id
            LEFT JOIN disclosure_tag_links l ON l.disclosure_id=d.id
            LEFT JOIN disclosure_tags t ON t.id=l.tag_id
            {where} GROUP BY d.id ORDER BY d.disclosed_at DESC,d.id DESC
        """).fetchall()
    return [dict(row) for row in rows]


def get_disclosure(disclosure_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return one disclosure view row."""
    return next((row for row in list_disclosures(db_path) if int(row["id"]) == disclosure_id), None)


def set_tags(disclosure_id: int, names: list[str], db_path: Path | str = DB_PATH) -> None:
    """Replace disclosure tags with normalized unique names."""
    clean = sorted({sanitize_text(name, 80) for name in names if sanitize_text(name, 80)})
    with connect(db_path) as conn:
        conn.execute("DELETE FROM disclosure_tag_links WHERE disclosure_id=?", (disclosure_id,))
        for name in clean:
            conn.execute("INSERT OR IGNORE INTO disclosure_tags(name,created_at) VALUES(?,?)", (name, _now()))
            tag_id = conn.execute("SELECT id FROM disclosure_tags WHERE name=?", (name,)).fetchone()[0]
            conn.execute("INSERT INTO disclosure_tag_links(disclosure_id,tag_id) VALUES(?,?)", (disclosure_id, tag_id))


def list_news_links(disclosure_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return candidate and confirmed news links for one disclosure."""
    with connect(db_path) as conn:
        rows = conn.execute("""SELECT l.*,n.title,n.url,n.published_at FROM disclosure_news_links l
            JOIN news_articles n ON n.id=l.news_article_id WHERE l.disclosure_id=? ORDER BY l.confirmed DESC,n.published_at DESC""", (disclosure_id,)).fetchall()
    return [dict(row) for row in rows]


def set_news_link(disclosure_id: int, news_article_id: int, confirmed: bool, db_path: Path | str = DB_PATH) -> None:
    """Create or update a manual disclosure-news relation."""
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM disclosures WHERE id=?", (disclosure_id,)).fetchone():
            raise ValueError("開示が見つかりません。")
        if not conn.execute("SELECT 1 FROM news_articles WHERE id=?", (news_article_id,)).fetchone():
            raise ValueError("ニュースが見つかりません。")
        now = _now()
        conn.execute("""INSERT INTO disclosure_news_links(disclosure_id,news_article_id,match_reason,confirmed,created_at,updated_at)
            VALUES(?,?,?, ?,?,?) ON CONFLICT(disclosure_id,news_article_id) DO UPDATE SET confirmed=excluded.confirmed,updated_at=excluded.updated_at""",
            (disclosure_id, news_article_id, "手動関連付け", int(confirmed), now, now))


def links_for_news(news_article_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return confirmed disclosures linked from a news detail."""
    with connect(db_path) as conn:
        rows = conn.execute("""SELECT d.id,d.title,d.disclosure_type,d.disclosed_at,s.ticker FROM disclosure_news_links l
            JOIN disclosures d ON d.id=l.disclosure_id JOIN stocks s ON s.id=d.stock_id
            WHERE l.news_article_id=? AND l.confirmed=1 ORDER BY d.disclosed_at DESC""", (news_article_id,)).fetchall()
    return [dict(row) for row in rows]


def dashboard_summary(db_path: Path | str = DB_PATH) -> dict[str, int]:
    """Return disclosure counts for dashboard cards."""
    today = datetime.now().date().isoformat()
    with connect(db_path) as conn:
        row = conn.execute("""SELECT
            SUM(CASE WHEN substr(disclosed_at,1,10)=? THEN 1 ELSE 0 END) today,
            SUM(CASE WHEN is_read=0 THEN 1 ELSE 0 END) unread,
            SUM(CASE WHEN importance='高' THEN 1 ELSE 0 END) high
            FROM disclosures""", (today,)).fetchone()
        holding = conn.execute("SELECT COUNT(*) FROM disclosures d JOIN stocks s ON s.id=d.stock_id WHERE s.is_holding=1").fetchone()[0]
    return {"today": int(row["today"] or 0), "unread": int(row["unread"] or 0), "high": int(row["high"] or 0), "holding": int(holding)}


def parse_csv(uploaded_file: Any) -> tuple[pd.DataFrame, list[str]]:
    """Parse a UTF-8 BOM compatible disclosure CSV for preview."""
    try:
        frame = pd.read_csv(uploaded_file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception as exc:
        logger.exception("開示CSV解析失敗")
        return pd.DataFrame(), [f"CSVを読み込めません: {exc}"]
    missing = [column for column in CSV_COLUMNS if column not in frame.columns]
    return frame, ([f"必須列がありません: {', '.join(missing)}"] if missing else [])


def export_csv(db_path: Path | str = DB_PATH) -> bytes:
    """Export disclosure metadata as formula-safe UTF-8 BOM CSV."""
    rows = list_disclosures(db_path)
    frame = pd.DataFrame([{column: _csv_safe(_csv_value(row, column)) for column in CSV_COLUMNS} for row in rows], columns=CSV_COLUMNS)
    return frame.to_csv(index=False).encode("utf-8-sig")


def import_csv(frame: pd.DataFrame, update_existing: bool, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Import valid rows independently and keep a detailed audit run."""
    result: dict[str, Any] = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    started = _now()
    with connect(db_path) as conn:
        run_id = int(conn.execute("INSERT INTO disclosure_import_runs(started_at,row_count,status,created_at) VALUES(?,?,?,?)", (started, len(frame), "running", started)).lastrowid)
    for offset, raw in frame.iterrows():
        row_number = int(offset) + 2
        ticker = str(raw.get("ticker") or "")
        try:
            payload = {column: raw.get(column, "") for column in CSV_COLUMNS}
            payload["user_memo"] = payload.pop("memo", "")
            status, disclosure_id = save_disclosure(payload, update_existing, db_path)
            if status == "duplicate": status = "skipped"
            result[status] += 1
            if status in {"inserted", "updated"}:
                set_tags(disclosure_id, str(raw.get("tags") or "").split(","), db_path)
            error = ""
        except Exception as exc:
            status, disclosure_id, error = "failed", None, str(exc)
            result["failed"] += 1
            result["errors"].append(f"{row_number}行目: {error}")
            logger.exception("開示CSV行取込失敗 row=%s ticker=%s", row_number, ticker)
        with connect(db_path) as conn:
            conn.execute("INSERT INTO disclosure_import_results(import_run_id,row_number,ticker,status,disclosure_id,error_message,created_at) VALUES(?,?,?,?,?,?,?)", (run_id, row_number, ticker, status, disclosure_id, error, _now()))
    finished = _now()
    with connect(db_path) as conn:
        conn.execute("""UPDATE disclosure_import_runs SET finished_at=?,inserted_count=?,updated_count=?,skipped_count=?,failed_count=?,status=?,error_summary=? WHERE id=?""",
            (finished, result["inserted"], result["updated"], result["skipped"], result["failed"], "partial" if result["failed"] else "success", "\n".join(result["errors"]), run_id))
    return result


def list_import_runs(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return recent disclosure CSV import history."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM disclosure_import_runs ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(row) for row in rows]


def make_prompt(disclosure: dict[str, Any], db_path: Path | str = DB_PATH) -> str:
    """Create a copy-only disclosure analysis prompt without invoking an AI API."""
    disclosure_id = int(disclosure.get("id") or 0)
    news = [row for row in list_news_links(disclosure_id, db_path) if row.get("confirmed")]
    news_text = "\n".join(f"- {row['title']} ({row.get('url') or 'URLなし'})" for row in news) or "なし"
    with connect(db_path) as conn:
        earnings = conn.execute("SELECT earnings_date,fiscal_quarter,date_status FROM earnings_events WHERE stock_id=? AND earnings_date IS NOT NULL ORDER BY earnings_date DESC LIMIT 1", (disclosure.get("stock_id"),)).fetchone()
    earnings_text = f"{earnings['earnings_date']} {earnings['fiscal_quarter']} {earnings['date_status']}" if earnings else "未登録"
    return f"""以下の適時開示について、事実、推測、リスクを分けて整理してください。売買を断定しないでください。

銘柄：{disclosure.get('ticker') or 'データなし'} {disclosure.get('company_name') or ''}
開示種別：{disclosure.get('disclosure_type') or 'データなし'}
タイトル：{disclosure.get('title') or 'データなし'}
開示日時：{disclosure.get('disclosed_at') or 'データなし'}
要約：{disclosure.get('summary') or 'なし'}
関連ニュース：
{news_text}
直近決算：{earnings_text}
ユーザーメモ：{disclosure.get('user_memo') or 'なし'}

1. 開示された事実
2. 前回予想・決算との差
3. 売上、利益、配当、財務への影響候補
4. 一時要因か継続要因か
5. ポジティブ・ネガティブ両面
6. 不足情報
7. 次に確認すべき一次資料
8. 関連企業への影響候補
9. リスク
"""


def _match_news(conn: Any, disclosure_id: int, item: dict[str, Any]) -> None:
    title = item["title"].casefold()
    urls = {url for url in (item["source_url"], item["document_url"]) if url}
    for news in conn.execute("SELECT id,title,url FROM news_articles").fetchall():
        news_title = str(news["title"] or "").casefold()
        reason = ""
        if news["url"] and news["url"] in urls:
            reason = "URL一致"
        elif len(title) >= 8 and (title in news_title or news_title in title):
            reason = "タイトル一致"
        if reason:
            now = _now()
            conn.execute("INSERT OR IGNORE INTO disclosure_news_links(disclosure_id,news_article_id,match_reason,confirmed,created_at,updated_at) VALUES(?,?,?,0,?,?)", (disclosure_id, news["id"], reason, now, now))


def _update_row(conn: Any, disclosure_id: int, item: dict[str, Any], now: str) -> None:
    conn.execute("""UPDATE disclosures SET stock_id=?,disclosure_type=?,title=?,disclosed_at=?,source_name=?,source_url=?,document_url=?,local_file_path=?,summary=?,importance=?,is_read=?,is_favorite=?,user_memo=?,external_id=?,content_hash=?,updated_at=? WHERE id=?""", _values(item) + (now, disclosure_id))


def _values(item: dict[str, Any]) -> tuple[Any, ...]:
    return (item["stock_id"], item["disclosure_type"], item["title"], item["disclosed_at"], item["source_name"], item["source_url"], item["document_url"], item["local_file_path"], item["summary"], item["importance"], int(item["is_read"]), int(item["is_favorite"]), item["user_memo"], item["external_id"], item["content_hash"])


def _normalize_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    text = str(value or "").strip()
    if not text:
        raise ValueError("開示日時を入力してください。")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError("開示日時はISO形式で入力してください。") from exc


def _csv_safe(value: Any) -> str:
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def _csv_value(row: dict[str, Any], column: str) -> Any:
    if column == "memo": return row.get("user_memo", "")
    return row.get(column, "")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
