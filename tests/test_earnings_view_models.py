"""Tests for earnings display models."""

from __future__ import annotations

from datetime import date

from services.earnings_view_models import format_earnings_date, format_weekday, prepare_earnings_rows


def test_display_labels_and_missing_values() -> None:
    row = prepare_earnings_rows([{"earnings_date":None,"announcement_time":None,"memo":None}], date(2026, 7, 11))[0]
    assert row["earnings_date_display"] == "日付未確認"
    assert row["weekday"] == "データなし"
    assert row["announcement_time_display"] == "未定"
    displayed = [row["earnings_date_display"], row["weekday"], row["announcement_time_display"], row["memo_display"]]
    assert "None" not in " ".join(displayed)


def test_weekday_display() -> None:
    assert format_earnings_date("2026-07-11") == "2026-07-11"
    assert format_weekday("2026-07-11") == "土曜日"


def test_earnings_dataframe_never_exposes_none_or_nan() -> None:
    from components.tables import earnings_dataframe

    frame = earnings_dataframe(prepare_earnings_rows([{"earnings_date":None,"announcement_time":None,"memo":None,"date_status":"未確認"}]))
    text = frame.to_string()
    assert "None" not in text and "NaN" not in text
    assert "日付未確認" in text


def test_candidate_dataframe_never_exposes_none_or_nan() -> None:
    from components.earnings_auto_fetch import _candidate_frame

    text = _candidate_frame([{"ticker":"5801.T","company_name":"古河電気工業","candidate_date":None,"existing_date":None,"comparison_status":"unknown","confidence":"unknown","review_status":"pending"}]).to_string()
    assert "None" not in text and "NaN" not in text
    assert "日付なし" in text and "不明" in text
