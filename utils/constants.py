"""Application-wide constants for オレ株AI."""

from __future__ import annotations

from pathlib import Path

APP_NAME = "オレ株AI"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "orekabu.db"
LOG_PATH = LOG_DIR / "app.log"

CATEGORIES = ["保有株", "監視銘柄", "関連銘柄", "その他"]
EARNINGS_QUARTERS = ["Q1", "Q2", "Q3", "通期", "未設定"]
EARNINGS_DATE_STATUSES = ["確定", "予定", "未確認"]
RELATION_TYPES = ["同業", "顧客", "仕入先", "競合", "親会社", "子会社", "テーマ関連", "海外関連", "指数関連", "その他"]
IMPACT_LEVELS = ["高", "中", "低"]
EARNINGS_COMPARISON_STATUSES = ["new", "same", "date_changed", "time_changed", "quarter_changed", "conflict", "past_date", "invalid", "unknown"]
EARNINGS_REVIEW_STATUSES = ["pending", "approved", "rejected", "held"]
EARNINGS_CONFIDENCE_LEVELS = ["high", "medium", "low", "unknown"]
NEWS_SOURCE_TYPES = ["RSS", "Atom", "手動", "CSV"]
NEWS_IMPORTANCE_LEVELS = ["高", "通常", "低"]
NEWS_CATEGORIES = ["決算", "業績", "適時開示", "製品・サービス", "業界", "市況", "その他"]
DISCLOSURE_TYPES = ["決算短信", "業績予想修正", "配当修正", "自己株式", "資本政策", "M&A", "提携", "人事", "株主総会", "その他"]
DISCLOSURE_IMPORTANCE_LEVELS = ["高", "通常", "低"]
DISCLOSURE_MAX_FILE_SIZE = 10 * 1024 * 1024
SAMPLE_STOCKS = [
    {"ticker": "5801.T", "company_name": "古河電気工業", "category": "監視銘柄"},
    {"ticker": "6976.T", "company_name": "太陽誘電", "category": "監視銘柄"},
    {"ticker": "4062.T", "company_name": "イビデン", "category": "監視銘柄"},
]

DEFAULT_SETTINGS = {
    "dashboard_display_mode": "標準",
    "news_display_mode": "カード",
    "mobile_priority_display": False,
    "briefing_limit": 10,
    "daily_tasks_limit": 10,
    "hide_zero_sections": True,
    "ranking_limit": 10,
    "stock_cache_minutes": 15,
    "buy_watch_near_percent": 3.0,
    "earnings_dashboard_limit": 5,
    "earnings_near_days": 7,
    "related_earnings_limit": 5,
    "past_earnings_days": 30,
    "show_unconfirmed_earnings": True,
    "earnings_auto_fetch": {
        "enabled": True,
        "provider": "yfinance",
        "max_tickers_per_run": 20,
        "request_interval_seconds": 1.0,
        "cache_hours": 6,
        "candidate_retention_days": 90,
        "show_past_candidates": True,
        "save_same_candidates": False,
        "date_change_min_days": 1,
        "include_confirmed_events": True,
    },
    "score": {
        "base_score": 50,
        "rsi_30_or_less": 20,
        "rsi_30_40": 15,
        "rsi_40_50": 5,
        "rsi_70_or_more": -10,
        "ma25_deviation_near": 15,
        "ma75_deviation_near": 10,
        "volume_ratio_15": 15,
        "volume_ratio_20_extra": 5,
        "drop_10_20": 10,
        "drop_20_or_more": 5,
        "ma5_above_ma25": 10,
        "golden_cross_extra": 10,
        "price_below_ma25_ma75": -10,
        "price_above_ma25_ma75": 5,
        "rsi_low": 30,
        "rsi_mid_low": 40,
        "rsi_mid": 50,
        "rsi_high": 70,
        "ma_deviation_threshold": 3.0,
        "volume_ratio_threshold": 1.5,
        "volume_ratio_extra_threshold": 2.0,
        "drop_threshold_low": 10.0,
        "drop_threshold_high": 20.0,
    },
}
