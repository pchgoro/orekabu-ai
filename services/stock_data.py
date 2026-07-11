"""Stock price retrieval and analysis row assembly."""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import pandas as pd
import streamlit as st
import yfinance as yf

from services.indicators import add_indicators
from services.scoring import calculate_attention_score
from utils.formatters import fmt_number, fmt_percent, fmt_price, fmt_signed_percent, fmt_signed_price

logger = logging.getLogger(__name__)


@st.cache_data(show_spinner=False)
def fetch_stock_history(ticker: str, period: str = "1y", interval: str = "1d", cache_bucket: int = 0) -> pd.DataFrame:
    """Fetch stock history with a caller-controlled cache bucket."""
    del cache_bucket
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            logger.warning("株価データが空です ticker=%s", ticker)
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            logger.error("株価データの列が不足しています ticker=%s missing=%s", ticker, missing)
            return pd.DataFrame()
        return df[required].dropna(how="all")
    except Exception:
        logger.exception("yfinance取得失敗 ticker=%s", ticker)
        return pd.DataFrame()


def cache_bucket(cache_minutes: int) -> int:
    """Return a time bucket used to invalidate Streamlit cache."""
    seconds = max(60, int(cache_minutes) * 60)
    return int(time.time() // seconds)


def period_to_yfinance(label: str) -> str:
    """Convert Japanese period labels to yfinance periods."""
    return {"1か月": "1mo", "3か月": "3mo", "6か月": "6mo", "1年": "1y"}.get(label, "1y")


def build_analysis_rows(stocks: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch prices and build display-ready analysis rows for multiple stocks."""
    rows: list[dict[str, Any]] = []
    bucket = cache_bucket(settings.get("stock_cache_minutes", 15))
    for stock in stocks:
        ticker = stock["ticker"]
        try:
            raw = fetch_stock_history(ticker, "1y", "1d", bucket)
            if raw.empty:
                rows.append({**stock, "data_status": "データなし", "score": 0, "judge": "データなし", "score_reasons": ["株価データを取得できませんでした"]})
                continue
            df = add_indicators(raw)
            latest = df.iloc[-1].to_dict()
            previous = df.iloc[-2].to_dict() if len(df) >= 2 else None
            scoring = calculate_attention_score(latest, previous, settings)
            close = latest.get("Close")
            prev_close = raw["Close"].iloc[-2] if len(raw) >= 2 else None
            change = close - prev_close if close is not None and prev_close is not None else None
            change_pct = (close / prev_close - 1) * 100 if close is not None and prev_close not in (None, 0) else None
            shares = int(stock.get("shares") or 0)
            average_price = float(stock.get("average_price") or 0)
            market_value = close * shares if close is not None else None
            profit = (close - average_price) * shares if close is not None and shares and average_price else None
            profit_pct = (close / average_price - 1) * 100 if close is not None and average_price else None
            rows.append(
                {
                    **stock,
                    **latest,
                    "current_price": close,
                    "previous_close": prev_close,
                    "change": change,
                    "change_pct": change_pct,
                    "market_value": market_value,
                    "profit": profit,
                    "profit_pct": profit_pct,
                    "score": scoring["score"],
                    "judge": scoring["judge"],
                    "score_reasons": scoring["reasons"],
                    "data_status": "OK",
                }
            )
        except Exception:
            logger.exception("銘柄分析行の生成に失敗 ticker=%s", ticker)
            rows.append({**stock, "data_status": "エラー", "score": 0, "judge": "エラー", "score_reasons": ["分析中にエラーが発生しました"]})
    return rows


def make_prompt(row: dict[str, Any]) -> str:
    """Generate a copyable prompt for manual ChatGPT analysis."""
    reasons = "\n".join(f"・{reason}" for reason in row.get("score_reasons", []))
    formatted = {
        "current_price": fmt_price(row.get("current_price")),
        "change": fmt_signed_price(row.get("change")),
        "average_price": fmt_price(row.get("average_price")),
        "profit": fmt_signed_price(row.get("profit")),
        "profit_pct": fmt_signed_percent(row.get("profit_pct")),
        "RSI14": fmt_number(row.get("RSI14")),
        "MA5": fmt_price(row.get("MA5")),
        "MA25": fmt_price(row.get("MA25")),
        "MA75": fmt_price(row.get("MA75")),
        "DEV_MA25": fmt_percent(row.get("DEV_MA25")),
        "DEV_MA75": fmt_percent(row.get("DEV_MA75")),
        "MACD": fmt_number(row.get("MACD")),
        "MACD_SIGNAL": fmt_number(row.get("MACD_SIGNAL")),
        "VOLUME_RATIO": fmt_number(row.get("VOLUME_RATIO")),
        "DROP_FROM_HIGH_60": fmt_percent(row.get("DROP_FROM_HIGH_60")),
        "buy_watch_price": fmt_price(row.get("buy_watch_price")),
    }
    fields = [
        ("銘柄コード", row.get("ticker")),
        ("会社名", row.get("company_name")),
        ("現在値", formatted["current_price"]),
        ("前日比", formatted["change"]),
        ("平均取得単価", formatted["average_price"]),
        ("保有株数", row.get("shares")),
        ("評価損益", formatted["profit"]),
        ("評価損益率", formatted["profit_pct"]),
        ("RSI", formatted["RSI14"]),
        ("5日移動平均", formatted["MA5"]),
        ("25日移動平均", formatted["MA25"]),
        ("75日移動平均", formatted["MA75"]),
        ("25日線乖離率", formatted["DEV_MA25"]),
        ("75日線乖離率", formatted["DEV_MA75"]),
        ("MACD", formatted["MACD"]),
        ("MACDシグナル", formatted["MACD_SIGNAL"]),
        ("出来高倍率", formatted["VOLUME_RATIO"]),
        ("直近高値からの下落率", formatted["DROP_FROM_HIGH_60"]),
        ("注目スコア", row.get("score")),
        ("スコア理由", reasons),
        ("買い検討価格", formatted["buy_watch_price"]),
        ("メモ", row.get("memo")),
        ("次回決算日", row.get("next_earnings_date_display")),
        ("決算までの日数", row.get("earnings_days_label")),
        ("決算対象四半期", row.get("earnings_quarter")),
        ("決算日ステータス", row.get("earnings_date_status")),
        ("発表予定時間", row.get("earnings_announcement_time")),
        ("関連銘柄の直近決算", row.get("related_earnings")),
        ("決算前に確認したいメモ", row.get("earnings_memo")),
    ]
    body = "\n".join(f"{label}：\n{_prompt_value(value)}" for label, value in fields)
    return f"""以下の日本株について、短期・中期の投資判断材料を整理してください。

{body}

以下の項目に分けて分析してください。

1. 現在のチャート状況
2. 強材料
3. 弱材料
4. 注目すべき価格帯
5. 買い増しを考える場合の確認事項
6. 保有継続を考える場合の確認事項
7. 売却を考える場合の確認事項
8. 今後確認すべきニュースや決算項目
9. 次回決算までに確認するべき項目
10. 決算で注目すべき売上、利益、会社予想、進捗率
11. 関連企業の決算から確認できること
12. 決算前後のリスク

売買を断定せず、
事実、推測、リスクを分けて説明してください。"""


def _prompt_value(value: Any) -> str:
    """Return a prompt-safe string without raw None/NaN/inf."""
    if value in (None, ""):
        return "データなし"
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "データなし"
    except TypeError:
        return "データなし"
    return str(value)
