"""Aggregate one company's stock, earnings, news, disclosures, and relations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from services.database import _now, connect, get_stock
from services.disclosures import list_disclosures
from services.earnings import get_stock_earnings, japan_today, next_earnings_by_stock
from services.earnings_candidates import list_candidates
from services.relations import impact_candidates, list_relations
from services.stock_data import build_analysis_rows
from utils.constants import DB_PATH
from utils.formatters import fmt_price, fmt_signed_price
from utils.validators import normalize_ticker


def search_companies(query: str = "", db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Search registered stocks by ticker, company name, or alias."""
    term = str(query or "").strip().casefold()
    with connect(db_path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM stocks ORDER BY ticker").fetchall()]
    if not term:
        return rows
    return [
        row for row in rows
        if any(term in str(row.get(field) or "").casefold() for field in ("ticker", "company_name", "company_alias"))
    ]


def update_company_metadata(
    stock_id: int, company_alias: str, market: str, industry: str,
    db_path: Path | str = DB_PATH,
) -> None:
    """Update optional profile metadata without changing portfolio fields."""
    values = [str(value or "").strip()[:100] for value in (company_alias, market, industry)]
    with connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE stocks SET company_alias=?,market=?,industry=?,updated_at=? WHERE id=?",
            (*values, _now(), int(stock_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError("対象銘柄が見つかりません。")


def build_company_profile(
    ticker: str, settings: dict[str, Any], db_path: Path | str = DB_PATH,
    *, include_price: bool = True,
) -> dict[str, Any]:
    """Build the sole cross-domain view model consumed by the company page."""
    stock = get_stock(normalize_ticker(ticker), db_path)
    if stock is None:
        raise ValueError("登録済みの銘柄が見つかりません。")
    stock_id = int(stock["id"])
    price = _price_summary(stock, settings, include_price)
    earnings = get_stock_earnings(stock_id, db_path)
    next_earnings = next_earnings_by_stock(db_path).get(stock_id)
    candidates = [row for row in list_candidates(db_path) if int(row["stock_id"]) == stock_id]
    related_earnings = [row for row in impact_candidates(db_path) if int(row["source_stock_id"]) == stock_id]
    news = _stock_news(stock_id, db_path)
    disclosures = [row for row in list_disclosures(db_path) if int(row["stock_id"]) == stock_id]
    relations = _stock_relations(stock_id, db_path)
    timeline = build_timeline(news, disclosures, earnings)
    profile = {
        "stock": stock, "price": price, "next_earnings": next_earnings,
        "earnings_candidates": candidates, "related_earnings": related_earnings,
        "earnings_history": _earnings_history(earnings), "news": news,
        "disclosures": disclosures, "relations": relations, "timeline": timeline,
        "news_summary": _news_summary(news), "disclosure_summary": _disclosure_summary(disclosures),
    }
    profile["prompt"] = make_company_prompt(profile)
    return profile


def build_timeline(
    news: list[dict[str, Any]], disclosures: list[dict[str, Any]],
    earnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge supported company events newest first with missing dates last."""
    items: list[dict[str, Any]] = []
    items.extend({"event_type": "ニュース", "occurred_at": row.get("published_at") or row.get("retrieved_at"), "title": row.get("title") or "タイトルなし", "importance": row.get("importance") or "通常"} for row in news)
    items.extend({"event_type": "適時開示", "occurred_at": row.get("disclosed_at"), "title": row.get("title") or "タイトルなし", "importance": row.get("importance") or "通常"} for row in disclosures)
    items.extend({"event_type": "決算", "occurred_at": row.get("earnings_date"), "title": f"{row.get('fiscal_year') or ''}年 {row.get('fiscal_quarter') or '未設定'}", "importance": row.get("date_status") or "未確認"} for row in earnings)
    return sorted(items, key=lambda row: str(row.get("occurred_at") or ""), reverse=True)


def make_company_prompt(profile: dict[str, Any]) -> str:
    """Generate a copy-only company intelligence prompt without calling an AI API."""
    stock, price = profile["stock"], profile["price"]
    news = "\n".join(f"- {row.get('published_at') or '日時不明'} {row.get('title') or 'タイトルなし'}" for row in profile["news"][:5]) or "なし"
    disclosures = "\n".join(f"- {row.get('disclosed_at') or '日時不明'} {row.get('disclosure_type') or 'その他'} {row.get('title') or 'タイトルなし'}" for row in profile["disclosures"][:5]) or "なし"
    next_event = profile.get("next_earnings") or {}
    relations = "\n".join(f"- {row['direction_label']} {row['related_ticker']} {row['related_company_name']}（{row['relation_type']}）" for row in profile["relations"]) or "なし"
    return f"""以下の日本株について企業カルテの情報を整理してください。AIは売買を断定せず、事実、推測、リスクを分けてください。

銘柄：{stock.get('ticker') or 'データなし'}
会社名：{stock.get('company_name') or 'データなし'}
略称：{stock.get('company_alias') or '未登録'}
市場：{stock.get('market') or '未登録'}
業種：{stock.get('industry') or '未登録'}
保有区分：{'保有株' if stock.get('is_holding') else stock.get('category') or '監視銘柄'}
現在値：{fmt_price(price.get('current_price'))}
前日比：{fmt_signed_price(price.get('change'))}
買い検討価格：{fmt_price(stock.get('buy_watch_price'))}
注目スコア：{price.get('score') if price.get('score') is not None else 'データなし'}
次回決算：{next_event.get('earnings_date') or '未登録'} {next_event.get('fiscal_quarter') or ''}
保有メモ：{stock.get('memo') or 'なし'}

最新ニュース：
{news}

最新適時開示：
{disclosures}

関連銘柄：
{relations}

1. 企業の現状
2. 株価と注目スコアの確認点
3. 次回決算までの確認事項
4. ニュースと適時開示から確認できる事実
5. 関連銘柄から確認できること
6. 強材料と弱材料
7. 不足情報
8. 主なリスク
"""


def _price_summary(stock: dict[str, Any], settings: dict[str, Any], include_price: bool) -> dict[str, Any]:
    if not include_price:
        return {**stock, "data_status": "未取得", "current_price": None, "change": None, "score": None, "price_updated_at": None}
    row = build_analysis_rows([stock], settings)[0]
    return {**row, "price_updated_at": datetime.now().isoformat(timespec="minutes") if row.get("data_status") == "OK" else None}


def _stock_news(stock_id: int, db_path: Path | str) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute("""SELECT a.*,COALESCE(s.name,'手動') source_name FROM news_articles a
            LEFT JOIN news_sources s ON s.id=a.source_id
            JOIN news_article_stocks x ON x.article_id=a.id
            WHERE x.stock_id=? AND x.confirmed=1
            ORDER BY COALESCE(a.published_at,a.retrieved_at) DESC,a.id DESC""", (stock_id,)).fetchall()
    return [dict(row) for row in rows]


def _stock_relations(stock_id: int, db_path: Path | str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in list_relations(db_path):
        if int(row["source_stock_id"]) == stock_id:
            result.append({**row, "direction_label": "この企業 ← 関連銘柄", "related_ticker": row["related_ticker"], "related_company_name": row["related_company_name"]})
        elif int(row["related_stock_id"]) == stock_id:
            result.append({**row, "direction_label": "この企業 → 影響を受ける銘柄", "related_ticker": row["source_ticker"], "related_company_name": row["source_company_name"]})
    return result


def _earnings_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = japan_today().isoformat()
    return sorted([row for row in rows if row.get("earnings_date") and str(row["earnings_date"]) < today], key=lambda row: str(row["earnings_date"]), reverse=True)


def _news_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {"unread": sum(not row.get("is_read") for row in rows), "important": sum(row.get("importance") == "高" for row in rows), "favorites": sum(bool(row.get("is_favorite")) for row in rows)}


def _disclosure_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {"unread": sum(not row.get("is_read") for row in rows), "important": sum(row.get("importance") == "高" for row in rows)}
