"""Explainable, user-defined daily investment score and category trade rules."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from services.categories import list_stock_categories
from services.database import _now, connect
from services.earnings import next_earnings_by_stock
from utils.constants import DB_PATH


def get_trade_rule(category_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return one optional category-level investment rule."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM trade_rules WHERE category_id=?", (int(category_id),)).fetchone()
    return dict(row) if row else None


def save_trade_rule(category_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Save a category rule without altering holdings or stock-level rules."""
    values = (
        str(payload.get("buy_conditions") or "").strip()[:3000],
        str(payload.get("add_position_conditions") or "").strip()[:3000],
        _percent(payload.get("take_profit_percent"), "利確ライン"),
        _percent(payload.get("stop_loss_percent"), "損切りライン"),
        _percent(payload.get("max_holding_ratio_percent"), "最大保有比率"),
        str(payload.get("memo") or "").strip()[:3000],
    )
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM categories WHERE id=?", (int(category_id),)).fetchone():
            raise ValueError("カテゴリが見つかりません。")
        conn.execute(
            """INSERT INTO trade_rules(category_id,buy_conditions,add_position_conditions,take_profit_percent,stop_loss_percent,max_holding_ratio_percent,memo,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(category_id) DO UPDATE SET
                buy_conditions=excluded.buy_conditions,add_position_conditions=excluded.add_position_conditions,
                take_profit_percent=excluded.take_profit_percent,stop_loss_percent=excluded.stop_loss_percent,
                max_holding_ratio_percent=excluded.max_holding_ratio_percent,memo=excluded.memo,
                updated_at=excluded.updated_at""",
            (int(category_id), *values, now, now),
        )


def calculate_ore_score(row: dict[str, Any], db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Calculate a 0-100 explanation-first score; never return a trade instruction."""
    stock_id = int(row.get("id") or 0)
    categories = list_stock_categories(stock_id, db_path) if stock_id else []
    category_names = {str(item.get("name") or "") for item in categories}
    parts: list[dict[str, Any]] = [{"points": 50, "reason": "基本点"}]
    if "AI" in category_names:
        parts.append({"points": 15, "reason": "AIテーマ"})
    if "国策" in category_names:
        parts.append({"points": 10, "reason": "国策テーマ"})
    days = _days_to_earnings(stock_id, db_path)
    if days == 0:
        parts.append({"points": 10, "reason": "本日決算"})
    elif days is not None and 0 < days <= 3:
        parts.append({"points": 8, "reason": "決算3日以内"})
    news_high, disclosures_high = _important_counts(stock_id, db_path)
    if news_high:
        parts.append({"points": 8, "reason": "重要ニュース"})
    if disclosures_high:
        parts.append({"points": 6, "reason": "重要な適時開示"})
    if _number(row.get("volume_ratio")) is not None and float(row["volume_ratio"]) >= 1.5:
        parts.append({"points": 5, "reason": "出来高増加"})
    if _number(row.get("profit_loss")) is not None and float(row["profit_loss"]) < 0:
        parts.append({"points": -8, "reason": "含み損"})
    rule_state = _category_rule_state(row, categories, db_path)
    if rule_state["take_profit_reached"]:
        parts.append({"points": -5, "reason": "カテゴリ利確ライン到達"})
    if rule_state["stop_loss_reached"]:
        parts.append({"points": -20, "reason": "カテゴリ損切りライン到達"})
    score = max(0, min(100, sum(int(part["points"]) for part in parts)))

    trade_rules = []
    if stock_id:
        with connect(db_path) as conn:
            for cat in categories:
                tr = conn.execute("SELECT * FROM trade_rules WHERE category_id=?", (int(cat["id"]),)).fetchone()
                if tr:
                    trade_rules.append(dict(tr))

    improvements = []
    if not categories:
        improvements.append("カテゴリ（テーマ・投資分類）を設定すると、オレ株スコアの評価精度が向上します。")
    elif not rule_state["rule_configured"]:
        improvements.append("設定したカテゴリに対応する投資ルールを「テーマ管理」で設定してください。")

    if rule_state["stop_loss_reached"]:
        improvements.append("カテゴリ投資ルールの損切りラインに到達しています。ルールに則った売却を検討してください。")
    if rule_state["take_profit_reached"]:
        improvements.append("カテゴリ投資ルールの利確ラインに到達しています。利益確定を検討してください。")
    if _number(row.get("profit_loss")) is not None and float(row["profit_loss"]) < 0:
        improvements.append("含み損が発生しています。保有理由や業績トレンドを再確認してください。")
    if days is not None and days <= 3:
        improvements.append("決算発表が間近（3日以内）です。発表後の株価急変に備えて、指値や損切りラインを再確認してください。")

    prev_score = None
    if stock_id:
        history = list_score_history(stock_id, limit=1, db_path=db_path)
        if history:
            prev_score = history[0]["score"]

    return {
        "score": score,
        "prev_score": prev_score,
        "breakdown": parts,
        "categories": categories,
        "trade_rules": trade_rules,
        "improvements": improvements,
        "days_to_earnings": days,
        "important_news_count": news_high,
        "important_disclosure_count": disclosures_high,
        **rule_state,
        "classification": _classification(score, rule_state),
    }



def enrich_rows_with_ore_scores(rows: list[dict[str, Any]], db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Attach transient score data so display paths do not persist history implicitly."""
    return [{**row, "ore_score": calculate_ore_score(row, db_path)} for row in rows]


def record_scores(rows: list[dict[str, Any]], db_path: Path | str = DB_PATH) -> int:
    """Persist the latest score and one score-history snapshot per explicit run."""
    snapshots = [
        (int(row.get("id") or 0), row.get("ore_score") or calculate_ore_score(row, db_path))
        for row in rows
        if int(row.get("id") or 0)
    ]
    now = _now()
    count = 0
    with connect(db_path) as conn:
        for stock_id, score_data in snapshots:
            breakdown = json.dumps(score_data["breakdown"], ensure_ascii=False)
            conn.execute(
                """INSERT INTO stock_scores(stock_id,score,breakdown_json,calculated_at,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(stock_id) DO UPDATE SET
                    score=excluded.score,breakdown_json=excluded.breakdown_json,
                    calculated_at=excluded.calculated_at,updated_at=excluded.updated_at""",
                (stock_id, int(score_data["score"]), breakdown, now, now),
            )
            conn.execute(
                """INSERT INTO score_history(stock_id,score,breakdown_json,recorded_at)
                VALUES(?,?,?,?) ON CONFLICT(stock_id,recorded_at) DO UPDATE SET
                    score=excluded.score,breakdown_json=excluded.breakdown_json""",
                (stock_id, int(score_data["score"]), breakdown, now),
            )
            count += 1
    return count


def list_score_history(stock_id: int, limit: int = 30, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return persisted score snapshots newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM score_history WHERE stock_id=? ORDER BY recorded_at DESC,id DESC LIMIT ?",
            (int(stock_id), max(1, min(int(limit), 365))),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["breakdown"] = json.loads(item.pop("breakdown_json") or "[]")
        except json.JSONDecodeError:
            item["breakdown"] = []
        result.append(item)
    return result


def score_rankings(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Classify existing score rows into ranked, explainable review queues."""
    ranked = sorted(rows, key=lambda item: int((item.get("ore_score") or {}).get("score") or 0), reverse=True)
    
    sudden_changes = []
    for r in rows:
        ore_score = r.get("ore_score") or {}
        score = ore_score.get("score")
        prev = ore_score.get("prev_score")
        if score is not None and prev is not None:
            diff = score - prev
            if abs(diff) >= 10:
                sudden_changes.append({**r, "score_diff": diff})
    sudden_changes.sort(key=lambda item: abs(item["score_diff"]), reverse=True)

    return {
        "overall": ranked,
        "buy_candidates": [r for r in ranked if r["ore_score"]["classification"] == "買い候補"],
        "attention": [r for r in ranked if r["ore_score"]["classification"] in {"注意銘柄", "売却候補"}],
        "sell_candidates": [r for r in ranked if r["ore_score"]["classification"] == "売却候補"],
        "earnings": [r for r in ranked if (r["ore_score"].get("days_to_earnings") is not None and r["ore_score"]["days_to_earnings"] <= 3)],
        "news": [r for r in ranked if r["ore_score"].get("important_news_count")],
        "sudden_changes": sudden_changes,
    }



def _days_to_earnings(stock_id: int, db_path: Path | str) -> int | None:
    event = next_earnings_by_stock(db_path).get(stock_id)
    value = event.get("days_until") if event else None
    return int(value) if isinstance(value, int) and value >= 0 else None


def _important_counts(stock_id: int, db_path: Path | str) -> tuple[int, int]:
    with connect(db_path) as conn:
        news = conn.execute(
            """SELECT COUNT(*) FROM news_article_stocks nas JOIN news_articles na ON na.id=nas.article_id
            WHERE nas.stock_id=? AND nas.confirmed=1 AND na.importance='高'""", (stock_id,)
        ).fetchone()[0]
        disclosures = conn.execute(
            "SELECT COUNT(*) FROM disclosures WHERE stock_id=? AND importance='高'", (stock_id,)
        ).fetchone()[0]
    return int(news), int(disclosures)


def _category_rule_state(row: dict[str, Any], categories: list[dict[str, Any]], db_path: Path | str) -> dict[str, bool]:
    current = _number(row.get("current_price"))
    average = _number(row.get("average_price"))
    if current is None or average is None or average <= 0:
        return {"take_profit_reached": False, "stop_loss_reached": False, "rule_configured": False}
    rules = []
    with connect(db_path) as conn:
        for category in categories:
            item = conn.execute("SELECT * FROM trade_rules WHERE category_id=?", (int(category["id"]),)).fetchone()
            if item:
                rules.append(dict(item))
    take = any(_number(rule.get("take_profit_percent")) is not None and current >= average * (1 + float(rule["take_profit_percent"]) / 100) for rule in rules)
    stop = any(_number(rule.get("stop_loss_percent")) is not None and current <= average * (1 - float(rule["stop_loss_percent"]) / 100) for rule in rules)
    return {"take_profit_reached": take, "stop_loss_reached": stop, "rule_configured": bool(rules)}


def _classification(score: int, state: dict[str, bool]) -> str:
    if state["stop_loss_reached"]:
        return "売却候補"
    if state["take_profit_reached"] or score < 45:
        return "注意銘柄"
    if score >= 65:
        return "買い候補"
    return "通常"


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _percent(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    parsed = _number(value)
    if parsed is None or parsed < 0 or parsed > 100:
        raise ValueError(f"{label}は0から100の範囲で入力してください。")
    return parsed or None
