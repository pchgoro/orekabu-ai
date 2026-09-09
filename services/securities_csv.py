"""Provider dispatch boundary for securities portfolio CSV adapters."""

from __future__ import annotations

from typing import Any

from services.marketspeed_import import parse_marketspeed_csv

SUPPORTED_PROVIDERS = ("marketspeed",)


def parse_securities_csv(provider: str, content: bytes, *, filename: str = "") -> dict[str, Any]:
    """Dispatch only to an explicitly supported provider parser."""
    key = str(provider or "").strip().casefold()
    if key == "marketspeed":
        return parse_marketspeed_csv(content, filename=filename)
    raise ValueError(
        f"未対応の証券会社CSV形式です: {provider or '未指定'}。実CSV確認後に対応します。"
    )
