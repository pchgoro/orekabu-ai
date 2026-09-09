import pytest

from services.database import connect, get_stock, init_db
from services.earnings_ir_sources import list_ir_sources, save_ir_source
from services.trusted_sources import (
    build_trusted_source_review_rows,
    build_trusted_source_rows,
    list_trusted_source_approvals,
    normalize_trusted_source_approval,
    set_trusted_source_approval,
)


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
    for value in ("false", "0", "yes", object()):
        with pytest.raises(ValueError):
            normalize_trusted_source_approval({"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": value, "approved_by": "tester"})


def test_trusted_source_review_exposes_explicit_reversible_action() -> None:
    rows = build_trusted_source_review_rows(
        [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir"}],
        [{"stock_id": 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": True}],
    )
    assert rows[0]["review_action"] == "revoke"
    assert rows[0]["review_action_label"] == "承認を解除"
    assert rows[0]["human_confirmation_required"] is True


def test_trusted_source_approval_is_append_only_idempotent_and_reversible(tmp_path) -> None:
    db = tmp_path / "trusted.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    save_ir_source({"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir"}, db)
    before_sources = list_ir_sources(db)

    approved = set_trusted_source_approval(
        {"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir/?utm_source=test", "approved": True, "approved_by": "tester"},
        db_path=db,
    )
    repeated = set_trusted_source_approval(
        {"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": True, "approved_by": "other"},
        db_path=db,
    )
    revoked = set_trusted_source_approval(
        {"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": False, "approved_by": "tester"},
        db_path=db,
    )
    reapproved = set_trusted_source_approval(
        {"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir", "approved": True, "approved_by": "tester"},
        db_path=db,
    )

    assert approved["changed"] is True and repeated["changed"] is False
    assert revoked["changed"] is True and reapproved["changed"] is True
    assert len(list_trusted_source_approvals(db)) == 1
    assert list_trusted_source_approvals(db)[0]["approved"] == 1
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trusted_source_approval_events").fetchone()[0] == 3
    rows = build_trusted_source_review_rows(list_ir_sources(db), list_trusted_source_approvals(db))
    assert rows[0]["trusted"] is True and rows[0]["review_action"] == "revoke"
    assert build_trusted_source_rows(
        [{"stock_id": stock["id"], "source_type": "official_ir_news", "source_url": "https://example.com/other"}],
        list_trusted_source_approvals(db),
    )[0]["trusted"] is False
    assert build_trusted_source_rows(
        [{"stock_id": stock["id"] + 1, "source_type": "official_ir_news", "source_url": "https://example.com/ir"}],
        list_trusted_source_approvals(db),
    )[0]["trusted"] is False
    assert build_trusted_source_rows(
        [{"stock_id": stock["id"], "source_type": "official_ir_calendar", "source_url": "https://example.com/ir"}],
        list_trusted_source_approvals(db),
    )[0]["trusted"] is False
    assert list_ir_sources(db) == before_sources


def test_trusted_source_migration_is_non_destructive(tmp_path) -> None:
    db = tmp_path / "migration.db"
    init_db(db)
    stock_before = get_stock("5801.T", db)
    save_ir_source({"stock_id": stock_before["id"], "source_type": "official_ir_news", "source_url": "https://example.com/ir"}, db)
    sources_before = list_ir_sources(db)
    init_db(db)
    assert get_stock("5801.T", db) == stock_before
    assert list_ir_sources(db) == sources_before
