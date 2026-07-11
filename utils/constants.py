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
SAMPLE_STOCKS = [
    {"ticker": "5801.T", "company_name": "古河電気工業", "category": "監視銘柄"},
    {"ticker": "6976.T", "company_name": "太陽誘電", "category": "監視銘柄"},
    {"ticker": "4062.T", "company_name": "イビデン", "category": "監視銘柄"},
]

DEFAULT_SETTINGS = {
    "ranking_limit": 10,
    "stock_cache_minutes": 15,
    "buy_watch_near_percent": 3.0,
    "earnings_dashboard_limit": 5,
    "earnings_near_days": 7,
    "related_earnings_limit": 5,
    "past_earnings_days": 30,
    "show_unconfirmed_earnings": True,
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
