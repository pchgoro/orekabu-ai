import pytest

from services.trusted_sources import build_trusted_source_review_rows, build_trusted_source_rows, normalize_trusted_source_approval


def test_trusted_source_requires_explicit_matching_approval() -> None:
    sources = [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir/?utm_source=x"}]
    rows = build_trusted_source_rows(
        sources,
        [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir/", "approved": True}],
    )
    assert rows[0]["trusted"] is True
    assert rows[0]["trust_reason"] == "明示承認済み"
    assert rows[0]["normalized_source_url"] == "https://example.com/ir"


def test_trusted_source_never_infers_from_existing_source_fields() -> None:
    rows = build_trusted_source_rows([
        {"stock_id": 1, "source_type": "official_ir_calendar", "source_url": "https://example.com/ir", "enabled": 1}
    ])
    assert rows[0]["trusted"] is False
    assert rows[0]["trust_reason"] == "明示承認なし"


def test_trusted_source_approval_contract_is_reversible_and_explicit() -> None:
    approval = normalize_trusted_source_approval({
        "stock_id": "1", "source_type": "official_ir_news",
        "source_url": "https://example.com/ir/?utm_campaign=test", "approved": True,
        "approved_by": "human",
    })
    assert approval["approved"] is True
    revoked = normalize_trusted_source_approval({**approval, "approved": False})
    assert revoked["approved"] is False
    with pytest.raises(ValueError):
        normalize_trusted_source_approval({"stock_id": 1, "source_type": "official_ir_news", "approved": True})
    with pytest.raises(ValueError):
        normalize_trusted_source_approval({"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": True})


def test_trusted_source_review_exposes_explicit_reversible_action() -> None:
    rows = build_trusted_source_review_rows(
        [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir"}],
        [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": True}],
    )
    assert rows[0]["review_action"] == "revoke"
    assert rows[0]["review_action_label"] == "承認を解除"
    assert rows[0]["human_confirmation_required"] is True
