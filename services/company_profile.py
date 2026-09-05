"""Aggregate one company's stock, earnings, news, disclosures, and relations."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from services.database import _now, connect, get_stock
from services.disclosures import list_disclosures
from services.edinet import list_documents
from services.earnings import get_stock_earnings, japan_today, next_earnings_by_stock
from services.earnings_candidates import list_candidates
from services.investment_playbooks import (
    evaluate_playbook,
    format_playbook_for_prompt,
    get_playbook,
)
from services.categories import (
    get_trade_notes,
    list_stock_categories,
)
from services.stock_scores import calculate_ore_score, list_score_history
from services.strategy_rules import (
    calculate_rule_lines,
    get_stock_rule,
    list_stock_tags,
    resolve_strategy_rule,
)
from services.relations import impact_candidates, list_relations
from services.stock_data import build_analysis_rows
from utils.constants import DB_PATH
from utils.formatters import fmt_price, fmt_signed_price
from utils.validators import normalize_ticker

CHECKLIST_FIELDS = (
    "earnings_checked",
    "disclosure_checked",
    "news_checked",
    "edinet_checked",
    "ai_analyzed",
)


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


def get_company_intelligence(
    stock_id: int, db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Return themes, investment story, and checklist state for one stock."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM company_intelligence WHERE stock_id=?",
            (int(stock_id),),
        ).fetchone()
    if row:
        return dict(row)
    return {
        "stock_id": int(stock_id),
        "themes": "",
        "investment_story": "",
        **{field: 0 for field in CHECKLIST_FIELDS},
        "created_at": "",
        "updated_at": "",
    }


def save_company_intelligence(
    stock_id: int,
    themes: str,
    investment_story: str,
    checklist: dict[str, Any],
    db_path: Path | str = DB_PATH,
) -> None:
    """Upsert user-authored company intelligence without touching stock data."""
    normalized_themes = _normalize_themes(themes)
    story = str(investment_story or "").strip()[:10000]
    flags = [int(bool(checklist.get(field))) for field in CHECKLIST_FIELDS]
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)).fetchone():
            raise ValueError("対象銘柄が見つかりません。")
        conn.execute(
            """INSERT INTO company_intelligence
            (stock_id,themes,investment_story,earnings_checked,disclosure_checked,
             news_checked,edinet_checked,ai_analyzed,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(stock_id) DO UPDATE SET
                themes=excluded.themes,
                investment_story=excluded.investment_story,
                earnings_checked=excluded.earnings_checked,
                disclosure_checked=excluded.disclosure_checked,
                news_checked=excluded.news_checked,
                edinet_checked=excluded.edinet_checked,
                ai_analyzed=excluded.ai_analyzed,
                updated_at=excluded.updated_at""",
            (int(stock_id), normalized_themes, story, *flags, now, now),
        )


def add_company_note(
    stock_id: int,
    note: str,
    occurred_at: str | None = None,
    db_path: Path | str = DB_PATH,
) -> int:
    """Add a dated user note that can appear in the company timeline."""
    value = str(note or "").strip()
    if not value:
        raise ValueError("メモを入力してください。")
    now = _now()
    event_time = str(occurred_at or now).strip() or now
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)).fetchone():
            raise ValueError("対象銘柄が見つかりません。")
        cursor = conn.execute(
            """INSERT INTO company_notes
            (stock_id,note,occurred_at,created_at,updated_at)
            VALUES(?,?,?,?,?)""",
            (int(stock_id), value[:4000], event_time, now, now),
        )
        return int(cursor.lastrowid)


def delete_company_note(note_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete one user-created company note."""
    with connect(db_path) as conn:
        if not conn.execute("DELETE FROM company_notes WHERE id=?", (int(note_id),)).rowcount:
            raise ValueError("対象メモが見つかりません。")


def list_company_notes(
    stock_id: int, db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """List company notes newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM company_notes WHERE stock_id=?
            ORDER BY occurred_at DESC,id DESC""",
            (int(stock_id),),
        ).fetchall()
    return [dict(row) for row in rows]


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
    edinet_documents = [
        row for row in list_documents(1000, db_path)
        if int(row["stock_id"]) == stock_id
    ]
    relations = _stock_relations(stock_id, db_path)
    intelligence = get_company_intelligence(stock_id, db_path)
    playbook = get_playbook(stock_id, db_path)
    playbook_evaluation = evaluate_playbook(
        playbook, price.get("current_price")
    )
    strategy_tags = list_stock_tags(stock_id, db_path)
    strategy_resolution = resolve_strategy_rule(stock_id, db_path)
    strategy_lines = calculate_rule_lines(
        strategy_resolution.get("rule"),
        stock.get("average_price"),
        price.get("current_price"),
        near_percent=float(settings.get("strategy_rule_near_percent", 3.0)),
    )
    individual_strategy_rule = get_stock_rule(stock_id, db_path)
    categories = list_stock_categories(stock_id, db_path)
    trade_notes = get_trade_notes(stock_id, db_path)
    ore_score = calculate_ore_score({**stock, **price}, db_path)
    score_history = list_score_history(stock_id, db_path=db_path)
    notes = list_company_notes(stock_id, db_path)
    timeline = build_timeline(news, disclosures, earnings, edinet_documents, notes)
    profile = {
        "stock": stock, "price": price, "next_earnings": next_earnings,
        "earnings_candidates": candidates, "related_earnings": related_earnings,
        "earnings_history": _earnings_history(earnings), "news": news,
        "disclosures": disclosures, "edinet_documents": edinet_documents,
        "relations": relations, "intelligence": intelligence, "notes": notes,
        "investment_playbook": playbook,
        "playbook_evaluation": playbook_evaluation,
        "strategy_tags": strategy_tags,
        "strategy_rule_resolution": strategy_resolution,
        "strategy_lines": strategy_lines,
        "individual_strategy_rule": individual_strategy_rule,
        "categories": categories,
        "trade_notes": trade_notes,
        "ore_score": ore_score,
        "score_history": score_history,
        "timeline": timeline,
        "news_summary": _news_summary(news), "disclosure_summary": _disclosure_summary(disclosures),
    }
    profile["prompt"] = make_company_prompt(profile)
    return profile


def build_timeline(
    news: list[dict[str, Any]], disclosures: list[dict[str, Any]],
    earnings: list[dict[str, Any]],
    edinet_documents: list[dict[str, Any]] | None = None,
    notes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge company events and user notes newest first."""
    items: list[dict[str, Any]] = []
    items.extend({"event_type": "ニュース", "occurred_at": row.get("published_at") or row.get("retrieved_at"), "title": row.get("title") or "タイトルなし", "importance": row.get("importance") or "通常"} for row in news)
    items.extend({"event_type": "適時開示", "occurred_at": row.get("disclosed_at"), "title": row.get("title") or "タイトルなし", "importance": row.get("importance") or "通常"} for row in disclosures)
    items.extend({"event_type": "決算", "occurred_at": row.get("earnings_date"), "title": f"{row.get('fiscal_year') or ''}年 {row.get('fiscal_quarter') or '未設定'}", "importance": row.get("date_status") or "未確認"} for row in earnings)
    items.extend({
        "event_type": "EDINET",
        "occurred_at": row.get("submitted_at"),
        "title": row.get("description") or row.get("document_type") or "書類名なし",
        "importance": row.get("document_type") or "書類",
    } for row in (edinet_documents or []))
    items.extend({
        "event_type": "メモ",
        "occurred_at": row.get("occurred_at"),
        "title": row.get("note") or "内容なし",
        "importance": "ユーザーメモ",
        "note_id": row.get("id"),
    } for row in (notes or []))
    return sorted(items, key=lambda row: str(row.get("occurred_at") or ""), reverse=True)


def make_company_prompt(profile: dict[str, Any]) -> str:
    """Generate a copy-only company intelligence prompt without calling an AI API."""
    stock, price = profile["stock"], profile["price"]
    news = "\n".join(f"- {row.get('published_at') or '日時不明'} {row.get('title') or 'タイトルなし'}" for row in profile["news"][:5]) or "なし"
    disclosures = "\n".join(f"- {row.get('disclosed_at') or '日時不明'} {row.get('disclosure_type') or 'その他'} {row.get('title') or 'タイトルなし'}" for row in profile["disclosures"][:5]) or "なし"
    edinet = "\n".join(f"- {row.get('submitted_at') or '日時不明'} {row.get('document_type') or '書類種別不明'} {row.get('description') or ''}" for row in profile["edinet_documents"][:5]) or "なし"
    next_event = profile.get("next_earnings") or {}
    relations = "\n".join(f"- {row['direction_label']} {row['related_ticker']} {row['related_company_name']}（{row['relation_type']}）" for row in profile["relations"]) or "なし"
    intelligence = profile.get("intelligence") or {}
    playbook_text = format_playbook_for_prompt(
        profile.get("investment_playbook")
    )
    strategy_tags = "、".join(
        str(row.get("name")) for row in profile.get("strategy_tags", [])
    ) or "未設定"
    categories = "、".join(
        str(row.get("name")) for row in profile.get("categories", [])
    ) or "未設定"
    trade_notes = profile.get("trade_notes") or {}
    ore_score = profile.get("ore_score") or {}
    strategy_resolution = profile.get("strategy_rule_resolution") or {}
    strategy_lines = profile.get("strategy_lines") or {}
    checklist = " / ".join(
        f"{label}: {'済' if intelligence.get(field) else '未'}"
        for field, label in (
            ("earnings_checked", "決算"),
            ("disclosure_checked", "適時開示"),
            ("news_checked", "ニュース"),
            ("edinet_checked", "EDINET"),
            ("ai_analyzed", "AI分析"),
        )
    )
    notes = "\n".join(f"- {row.get('occurred_at') or '日時不明'} {row.get('note') or ''}" for row in profile.get("notes", [])[:5]) or "なし"
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
テーマ：{intelligence.get('themes') or '未登録'}
投資ストーリー：{intelligence.get('investment_story') or '未登録'}
確認チェックリスト：{checklist}

投資ルール：
{playbook_text}

戦略タグ：{strategy_tags}
カテゴリ：{categories}
保有理由：{trade_notes.get('holding_reason') or '未設定'}
売却条件：{trade_notes.get('sell_conditions') or '未設定'}
自由メモ：{trade_notes.get('memo') or '未設定'}
オレ株スコア：{ore_score.get('score', '未設定')}点
スコア内訳：{' / '.join(f"{part.get('points', 0):+d} {part.get('reason', '')}" for part in ore_score.get('breakdown', [])) or '未設定'}
適用中の戦略ルール：{strategy_resolution.get('source_label') or '未設定'}
戦略ルール損切価格：{fmt_price(strategy_lines.get('stop_loss_price'))}
戦略ルール利確価格：{fmt_price(strategy_lines.get('take_profit_price'))}
戦略ルール買い増し価格：{fmt_price(strategy_lines.get('add_position_price'))}
戦略ルール状態：{'競合' if strategy_resolution.get('conflict') else strategy_lines.get('status_label') or '未設定'}

最新ニュース：
{news}

最新適時開示：
{disclosures}

最新EDINET書類：
{edinet}

関連銘柄：
{relations}

時系列メモ：
{notes}

1. 企業の現状
2. 株価と注目スコアの確認点
3. 次回決算までの確認事項
4. ニュースと適時開示から確認できる事実
5. 関連銘柄から確認できること
6. 強材料と弱材料
7. 不足情報
8. 投資ストーリーを支持する事実と反証する事実
9. 主なリスク

上記ルールを前提として、現在のニュース・決算・適時開示を整理してください。
売買推奨は禁止し、設定したルールに対する事実関係だけを整理してください。
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


def _normalize_themes(value: str) -> str:
    """Store manually entered themes as a compact comma-separated list."""
    parts = re.split(r"[,、\n]+", str(value or ""))
    unique: list[str] = []
    for part in parts:
        theme = part.strip()[:100]
        if theme and theme not in unique:
            unique.append(theme)
    return ", ".join(unique[:30])
