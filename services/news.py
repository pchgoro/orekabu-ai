"""News persistence, matching, CSV exchange, and fetch orchestration."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

from services.database import _now, connect, get_stock, get_stocks
from services.news_providers.base import NewsItem, NewsProvider
from services.news_providers.csv_provider import CsvNewsProvider
from utils.constants import DB_PATH, NEWS_CATEGORIES, NEWS_IMPORTANCE_LEVELS, NEWS_SOURCE_TYPES

logger = logging.getLogger(__name__)
ARTICLE_COLUMNS = ["title", "url", "published_at", "source", "author", "summary", "importance", "category", "memo"]
SOURCE_COLUMNS = ["name", "source_type", "url", "is_enabled", "memo"]
KEYWORD_COLUMNS = ["ticker", "keyword", "is_enabled"]


def canonicalize_url(url: str) -> str:
    """Normalize a URL while removing common tracking parameters."""
    value = (url or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def deduplication_key(item: NewsItem) -> str:
    """Build a stable key from external id, canonical URL, title, and date."""
    published_date = (item.published_at or "")[:10]
    identity = item.external_id.strip() or canonicalize_url(item.url) or re.sub(r"\s+", " ", item.title.strip().lower())
    return hashlib.sha256(f"{identity}|{published_date}".encode("utf-8")).hexdigest()


def add_source(payload: dict[str, Any], db_path: Path | str = DB_PATH) -> int:
    """Create a news source."""
    name = str(payload.get("name") or "").strip()
    source_type = str(payload.get("source_type") or "").strip()
    if not name or source_type not in NEWS_SOURCE_TYPES:
        raise ValueError("ソース名または種別が不正です。")
    url = str(payload.get("url") or "").strip()
    if source_type in {"RSS", "Atom"} and not url.startswith(("http://", "https://")):
        raise ValueError("RSS/Atomにはhttp(s) URLが必要です。")
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute("INSERT INTO news_sources(name,source_type,url,is_enabled,memo,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (name, source_type, url, int(bool(payload.get("is_enabled", True))), str(payload.get("memo") or "").strip(), now, now))
        return int(cursor.lastrowid)


def update_source(source_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Update a news source after validating through the same rules as creation."""
    name, source_type = str(payload.get("name") or "").strip(), str(payload.get("source_type") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not name or source_type not in NEWS_SOURCE_TYPES or (source_type in {"RSS", "Atom"} and not url.startswith(("http://", "https://"))):
        raise ValueError("ソース設定が不正です。")
    with connect(db_path) as conn:
        cursor = conn.execute("UPDATE news_sources SET name=?,source_type=?,url=?,is_enabled=?,memo=?,updated_at=? WHERE id=?", (name, source_type, url, int(bool(payload.get("is_enabled", True))), str(payload.get("memo") or "").strip(), _now(), source_id))
        if not cursor.rowcount:
            raise ValueError("対象ソースが存在しません。")


def delete_source(source_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete a source while preserving articles through SET NULL."""
    with connect(db_path) as conn:
        if not conn.execute("DELETE FROM news_sources WHERE id=?", (source_id,)).rowcount:
            raise ValueError("対象ソースが存在しません。")


def list_sources(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List configured news sources."""
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM news_sources ORDER BY name").fetchall()]


def save_article(item: NewsItem, source_id: int | None = None, metadata: dict[str, Any] | None = None, db_path: Path | str = DB_PATH) -> tuple[str, int]:
    """Save one article metadata record and generate unconfirmed stock matches."""
    if not item.title.strip():
        raise ValueError("タイトルは必須です。")
    metadata = metadata or {}
    importance = str(metadata.get("importance") or "通常")
    category = str(metadata.get("category") or "その他")
    if importance not in NEWS_IMPORTANCE_LEVELS or category not in NEWS_CATEGORIES:
        raise ValueError("重要度またはカテゴリが不正です。")
    key, canonical_url, now = deduplication_key(item), canonicalize_url(item.url), _now()
    with connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM news_articles WHERE deduplication_key=? OR (?<>'' AND canonical_url=?)",
            (key, canonical_url, canonical_url),
        ).fetchone()
        if existing:
            return "duplicate", int(existing["id"])
        cursor = conn.execute(
            """INSERT INTO news_articles(source_id,external_id,title,url,canonical_url,published_at,author,summary,retrieved_at,
               deduplication_key,is_read,is_favorite,importance,category,memo,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?,?)""",
            (source_id, item.external_id, item.title.strip(), item.url.strip(), canonical_url, item.published_at,
             item.author.strip(), item.summary.strip()[:4000], now, key, importance, category, str(metadata.get("memo") or "").strip(), now, now),
        )
        article_id = int(cursor.lastrowid)
        _match_article(conn, article_id, f"{item.title} {item.summary}")
    logger.info("ニュース記事保存 article_id=%s source_id=%s", article_id, source_id)
    return "inserted", article_id


def list_articles(db_path: Path | str = DB_PATH, filter_name: str = "最新") -> list[dict[str, Any]]:
    """List articles with source and stock labels."""
    conditions: list[str] = []
    if filter_name == "未読": conditions.append("a.is_read=0")
    if filter_name == "お気に入り": conditions.append("a.is_favorite=1")
    if filter_name == "保有株": conditions.append("EXISTS(SELECT 1 FROM news_article_stocks x JOIN stocks st ON st.id=x.stock_id WHERE x.article_id=a.id AND st.is_holding=1)")
    if filter_name == "監視銘柄": conditions.append("EXISTS(SELECT 1 FROM news_article_stocks x JOIN stocks st ON st.id=x.stock_id WHERE x.article_id=a.id AND st.is_holding=0)")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with connect(db_path) as conn:
        rows = conn.execute(f"""SELECT a.*,COALESCE(s.name,'手動') source_name,
            GROUP_CONCAT(DISTINCT st.ticker || ' ' || st.company_name) stock_labels,
            MAX(CASE WHEN st.is_holding=1 THEN 1 ELSE 0 END) has_holding_match,
            MAX(CASE WHEN st.id IS NOT NULL AND st.is_holding=0 THEN 1 ELSE 0 END) has_watch_match
            FROM news_articles a LEFT JOIN news_sources s ON s.id=a.source_id
            LEFT JOIN news_article_stocks ast ON ast.article_id=a.id
            LEFT JOIN stocks st ON st.id=ast.stock_id {where}
            GROUP BY a.id ORDER BY COALESCE(a.published_at,a.retrieved_at) DESC,a.id DESC""").fetchall()
    return [dict(row) for row in rows]


def update_article(article_id: int, values: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Update user-managed article state."""
    importance, category = values.get("importance", "通常"), values.get("category", "その他")
    if importance not in NEWS_IMPORTANCE_LEVELS or category not in NEWS_CATEGORIES:
        raise ValueError("重要度またはカテゴリが不正です。")
    with connect(db_path) as conn:
        cursor = conn.execute("UPDATE news_articles SET is_read=?,is_favorite=?,importance=?,category=?,memo=?,updated_at=? WHERE id=?", (int(bool(values.get("is_read"))), int(bool(values.get("is_favorite"))), importance, category, str(values.get("memo") or "").strip(), _now(), article_id))
        if not cursor.rowcount: raise ValueError("対象記事が存在しません。")


def add_keyword(stock_id: int, keyword: str, enabled: bool = True, db_path: Path | str = DB_PATH) -> int:
    """Add a stock-specific matching keyword."""
    value = keyword.strip()
    if len(value) < 2: raise ValueError("キーワードは2文字以上で入力してください。")
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute("INSERT INTO stock_news_keywords(stock_id,keyword,is_enabled,created_at,updated_at) VALUES(?,?,?,?,?)", (stock_id, value, int(enabled), now, now))
        return int(cursor.lastrowid)


def list_keywords(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List stock matching keywords."""
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute("SELECT k.*,s.ticker,s.company_name FROM stock_news_keywords k JOIN stocks s ON s.id=k.stock_id ORDER BY s.ticker,k.keyword").fetchall()]


def delete_keyword(keyword_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete one matching keyword."""
    with connect(db_path) as conn: conn.execute("DELETE FROM stock_news_keywords WHERE id=?", (keyword_id,))


def confirm_stock_match(article_id: int, stock_id: int, confirmed: bool, db_path: Path | str = DB_PATH) -> None:
    """Approve or return a rule-generated stock match to candidate state."""
    with connect(db_path) as conn:
        if not conn.execute("UPDATE news_article_stocks SET confirmed=?,updated_at=? WHERE article_id=? AND stock_id=?", (int(confirmed), _now(), article_id, stock_id)).rowcount:
            raise ValueError("対象の銘柄候補が存在しません。")


def list_stock_matches(db_path: Path | str = DB_PATH, article_id: int | None = None) -> list[dict[str, Any]]:
    """List rule matches for manual confirmation."""
    where, params = ("WHERE x.article_id=?", (article_id,)) if article_id else ("", ())
    with connect(db_path) as conn:
        rows = conn.execute(f"SELECT x.*,s.ticker,s.company_name,a.title FROM news_article_stocks x JOIN stocks s ON s.id=x.stock_id JOIN news_articles a ON a.id=x.article_id {where} ORDER BY x.article_id DESC,s.ticker", params).fetchall()
    return [dict(row) for row in rows]


def set_article_tags(article_id: int, names: list[str], db_path: Path | str = DB_PATH) -> None:
    """Replace article tags, creating tag definitions as needed."""
    clean = sorted({name.strip() for name in names if name.strip()})
    with connect(db_path) as conn:
        conn.execute("DELETE FROM news_article_tags WHERE article_id=?", (article_id,))
        for name in clean:
            conn.execute("INSERT OR IGNORE INTO news_tags(name,created_at) VALUES(?,?)", (name, _now()))
            tag_id = conn.execute("SELECT id FROM news_tags WHERE name=?", (name,)).fetchone()[0]
            conn.execute("INSERT INTO news_article_tags(article_id,tag_id) VALUES(?,?)", (article_id, tag_id))


def get_article_tags(article_id: int, db_path: Path | str = DB_PATH) -> list[str]:
    """Return tag names for one article."""
    with connect(db_path) as conn:
        return [row[0] for row in conn.execute("SELECT t.name FROM news_tags t JOIN news_article_tags x ON x.tag_id=t.id WHERE x.article_id=? ORDER BY t.name", (article_id,)).fetchall()]


def fetch_enabled_sources(provider_factory: Any, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Fetch enabled RSS/Atom sources independently and retain an audit trail."""
    sources = [s for s in list_sources(db_path) if s["is_enabled"] and s["source_type"] in {"RSS", "Atom"}]
    now = _now()
    with connect(db_path) as conn:
        run_id = int(conn.execute("INSERT INTO news_fetch_runs(started_at,source_count,status,created_at) VALUES(?,?,?,?)", (now, len(sources), "running", now)).lastrowid)
    inserted = duplicates = failed = 0
    errors: list[str] = []
    for source in sources:
        source_inserted = source_duplicates = 0
        try:
            provider: NewsProvider = provider_factory(source)
            for item in provider.fetch():
                status, _ = save_article(item, int(source["id"]), db_path=db_path)
                source_inserted += status == "inserted"
                source_duplicates += status == "duplicate"
            status, error = "completed", ""
        except Exception as exc:
            failed += 1; status, error = "failed", str(exc)[:500]; errors.append(f"{source['name']}: {error}")
            logger.exception("ニュース取得失敗 source_id=%s source=%s", source["id"], source["name"])
        inserted += source_inserted; duplicates += source_duplicates
        with connect(db_path) as conn:
            conn.execute("INSERT INTO news_fetch_results(fetch_run_id,source_id,status,article_count,duplicate_count,error_message,retrieved_at,created_at) VALUES(?,?,?,?,?,?,?,?)", (run_id, source["id"], status, source_inserted, source_duplicates, error, _now(), _now()))
    final_status = "failed" if failed == len(sources) and sources else ("partial" if failed else "completed")
    with connect(db_path) as conn:
        conn.execute("UPDATE news_fetch_runs SET finished_at=?,article_count=?,duplicate_count=?,failed_count=?,status=?,error_summary=? WHERE id=?", (_now(), inserted, duplicates, failed, final_status, " / ".join(errors)[:1000], run_id))
    return {"run_id": run_id, "inserted": inserted, "duplicates": duplicates, "failed": failed, "errors": errors}


def list_fetch_runs(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List news fetch audit runs."""
    with connect(db_path) as conn: return [dict(r) for r in conn.execute("SELECT * FROM news_fetch_runs ORDER BY id DESC").fetchall()]


def news_dashboard_summary(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Return compact dashboard counts."""
    today = date.today().isoformat()
    with connect(db_path) as conn:
        scalar = lambda sql, params=(): int(conn.execute(sql, params).fetchone()[0])
        run = conn.execute("SELECT finished_at FROM news_fetch_runs ORDER BY id DESC LIMIT 1").fetchone()
        return {"today": scalar("SELECT COUNT(*) FROM news_articles WHERE substr(COALESCE(published_at,retrieved_at),1,10)=?", (today,)), "unread": scalar("SELECT COUNT(*) FROM news_articles WHERE is_read=0"), "holdings": scalar("SELECT COUNT(DISTINCT x.article_id) FROM news_article_stocks x JOIN stocks s ON s.id=x.stock_id WHERE s.is_holding=1"), "watch": scalar("SELECT COUNT(DISTINCT x.article_id) FROM news_article_stocks x JOIN stocks s ON s.id=x.stock_id WHERE s.is_holding=0"), "important": scalar("SELECT COUNT(*) FROM news_articles WHERE importance='高'"), "favorites": scalar("SELECT COUNT(*) FROM news_articles WHERE is_favorite=1"), "last_fetch": run["finished_at"] if run else None}


def export_csv(kind: str, db_path: Path | str = DB_PATH) -> bytes:
    """Export articles, sources, or keywords with UTF-8 BOM."""
    output = io.StringIO(newline="")
    if kind == "articles": columns, rows = ARTICLE_COLUMNS, [{**r, "source": r.get("source_name", "")} for r in list_articles(db_path)]
    elif kind == "sources": columns, rows = SOURCE_COLUMNS, list_sources(db_path)
    elif kind == "keywords": columns, rows = KEYWORD_COLUMNS, list_keywords(db_path)
    else: raise ValueError("CSV種別が不正です。")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def parse_csv(uploaded_file: Any, kind: str) -> tuple[pd.DataFrame, list[str]]:
    """Parse a BOM-compatible news CSV for preview."""
    columns = {"articles": ARTICLE_COLUMNS, "sources": SOURCE_COLUMNS, "keywords": KEYWORD_COLUMNS}.get(kind)
    if not columns: return pd.DataFrame(), ["CSV種別が不正です。"]
    try:
        frame = pd.DataFrame(csv.DictReader(io.StringIO(uploaded_file.getvalue().decode("utf-8-sig"))))
        missing = [c for c in columns if c not in frame.columns]
        return (pd.DataFrame(), [f"CSV列が不足しています: {', '.join(missing)}"]) if missing else (frame[columns], [])
    except Exception as exc:
        logger.exception("ニュースCSV読み込み失敗 kind=%s", kind)
        return pd.DataFrame(), [f"CSVを読み込めませんでした: {exc}"]


def import_csv(frame: pd.DataFrame, kind: str, update_existing: bool, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Import valid rows independently, reporting line-level errors."""
    result: dict[str, Any] = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    for index, row in frame.iterrows():
        try:
            values = {key: ("" if pd.isna(value) else value) for key, value in row.to_dict().items()}
            if kind == "articles":
                source = next((s for s in list_sources(db_path) if s["name"] == values["source"]), None)
                item = CsvNewsProvider(values).fetch()[0]
                status, _ = save_article(item, int(source["id"]) if source else None, values, db_path)
                result["inserted" if status == "inserted" else "skipped"] += 1
            elif kind == "sources":
                existing = next((s for s in list_sources(db_path) if s["name"] == str(values["name"]).strip()), None)
                payload = {**values, "is_enabled": str(values["is_enabled"]).lower() not in {"0", "false", "off"}}
                if existing and update_existing: update_source(int(existing["id"]), payload, db_path); result["updated"] += 1
                elif existing: result["skipped"] += 1
                else: add_source(payload, db_path); result["inserted"] += 1
            elif kind == "keywords":
                stock = get_stock(str(values["ticker"]).strip(), db_path)
                if not stock: raise ValueError("登録銘柄に存在しないtickerです。")
                keyword = str(values["keyword"]).strip()
                existing = next((item for item in list_keywords(db_path) if int(item["stock_id"]) == int(stock["id"]) and item["keyword"] == keyword), None)
                if existing and update_existing:
                    with connect(db_path) as conn:
                        conn.execute("UPDATE stock_news_keywords SET is_enabled=?,updated_at=? WHERE id=?", (int(str(values["is_enabled"]).lower() not in {"0", "false", "off"}), _now(), existing["id"]))
                    result["updated"] += 1
                elif existing:
                    result["skipped"] += 1
                else:
                    add_keyword(int(stock["id"]), keyword, str(values["is_enabled"]).lower() not in {"0", "false", "off"}, db_path)
                    result["inserted"] += 1
            else: raise ValueError("CSV種別が不正です。")
        except Exception as exc:
            result["failed"] += 1; result["errors"].append(f"{int(index)+2}行目: {exc}")
            logger.exception("ニュースCSV行エラー kind=%s line=%s", kind, int(index)+2)
    return result


def make_news_prompt(article: dict[str, Any], db_path: Path | str = DB_PATH) -> str:
    """Build a copyable ChatGPT prompt without calling an AI API."""
    tags = ", ".join(get_article_tags(int(article["id"]), db_path)) or "なし"
    return f"""以下の日本株関連ニュースを整理してください。売買を断定せず、事実、推測、リスクを分けてください。

タイトル：{article.get('title') or 'データなし'}
公開日時：{article.get('published_at') or 'データなし'}
ソース：{article.get('source_name') or 'データなし'}
URL：{article.get('url') or 'データなし'}
著者：{article.get('author') or 'データなし'}
RSS要約：{article.get('summary') or 'データなし'}
関連銘柄候補：{article.get('stock_labels') or 'なし'}
重要度：{article.get('importance') or '通常'}
カテゴリ：{article.get('category') or 'その他'}
タグ：{tags}
メモ：{article.get('memo') or 'なし'}

1. 確認できる事実
2. 関連銘柄へ影響しうる要因
3. 短期・中期で確認すべき点
4. 推測に留まる点
5. 主なリスク
6. 追加で確認すべき一次情報
"""


def _match_article(conn: Any, article_id: int, text: str) -> None:
    normalized = text.casefold()
    keywords = conn.execute("SELECT * FROM stock_news_keywords WHERE is_enabled=1").fetchall()
    custom: dict[int, list[str]] = {}
    for row in keywords: custom.setdefault(int(row["stock_id"]), []).append(row["keyword"])
    for stock in conn.execute("SELECT id,ticker,company_name FROM stocks").fetchall():
        ticker = str(stock["ticker"]); terms = [ticker, ticker.removesuffix(".T"), str(stock["company_name"]), *custom.get(int(stock["id"]), [])]
        matched = [term for term in terms if len(term) >= 2 and term.casefold() in normalized]
        if matched:
            now = _now(); conn.execute("INSERT OR IGNORE INTO news_article_stocks(article_id,stock_id,match_reason,confirmed,created_at,updated_at) VALUES(?,?,?,0,?,?)", (article_id, stock["id"], ", ".join(matched), now, now))
