"""Display formatting must never leak or crash on missing numeric values."""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils.formatters import fmt_number, fmt_percent, fmt_price, fmt_signed_price


def test_missing_numeric_variants_render_as_data_unavailable() -> None:
    values = [None, float("nan"), float("inf"), np.float32("nan"), pd.NA, "invalid"]
    for value in values:
        assert fmt_price(value) == "データなし"
        assert fmt_signed_price(value) == "データなし"
        assert fmt_percent(value) == "データなし"
        assert fmt_number(value) == "データなし"


def test_numeric_strings_remain_supported() -> None:
    assert fmt_price("1234.5") == "1,234"
    assert fmt_percent("12.345") == "12.35%"
