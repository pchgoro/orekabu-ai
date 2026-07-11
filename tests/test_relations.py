"""Tests for directed stock relations and CSV."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from services.database import get_stock, init_db
from services.relations import add_relation, delete_relation, export_relations_csv, import_relations_csv, list_relations, update_relation


def test_relation_crud_self_and_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    source, related = get_stock("5801.T", db), get_stock("6976.T", db)
    payload = {"source_stock_id":source["id"],"related_stock_id":related["id"],"relation_type":"同業","impact_level":"中","memo":""}
    relation_id = add_relation(payload, db)
    with pytest.raises(sqlite3.IntegrityError): add_relation(payload, db)
    with pytest.raises(ValueError): add_relation({**payload,"related_stock_id":source["id"]}, db)
    update_relation(relation_id, {**payload,"impact_level":"高"}, db)
    assert list_relations(db)[0]["impact_level"] == "高"
    delete_relation(relation_id, db)
    assert list_relations(db) == []
    with pytest.raises(ValueError): delete_relation(relation_id, db)


def test_relations_csv_continues_after_invalid_row(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    frame = pd.DataFrame([
        {"source_ticker":"5801.T","related_ticker":"6976.T","relation_type":"同業","impact_level":"中","memo":""},
        {"source_ticker":"5801.T","related_ticker":"9999.T","relation_type":"同業","impact_level":"中","memo":""},
    ])
    result = import_relations_csv(frame, True, db)
    assert (result["inserted"], result["failed"]) == (1, 1)
    assert export_relations_csv(list_relations(db)).startswith(b"\xef\xbb\xbf")
