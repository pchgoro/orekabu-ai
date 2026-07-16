"""Disclosure CRUD, security, CSV, links, dashboard, and prompt tests."""

from __future__ import annotations

import io
from pathlib import Path

from services.database import get_stock, init_db
from services.disclosures import (
    dashboard_summary,
    delete_disclosure,
    export_csv,
    import_csv,
    links_for_news,
    list_disclosures,
    list_news_links,
    make_prompt,
    parse_csv,
    save_disclosure,
    save_uploaded_pdf,
    set_news_link,
    set_tags,
    update_disclosure,
    validate_local_pdf,
    validate_web_url,
)
from services.news import save_article
from services.news_providers.base import NewsItem


def payload(**overrides):
    base = {
        "ticker": "5801.T", "disclosure_type": "決算短信", "title": "2027年3月期 決算短信",
        "disclosed_at": "2026-07-13T15:00", "source_name": "企業サイト",
        "source_url": "https://example.com/disclosure", "document_url": "https://example.com/a.pdf",
        "summary": "売上と利益を発表", "importance": "高", "memo": "一次資料を確認", "external_id": "TD-1",
    }
    return {**base, **overrides}


def test_disclosure_crud_duplicate_tags_and_dashboard(tmp_path: Path) -> None:
    db = tmp_path / "disclosure.db"; init_db(db)
    status, disclosure_id = save_disclosure(payload(), db_path=db)
    assert status == "inserted"
    assert save_disclosure(payload(), db_path=db)[0] == "duplicate"
    set_tags(disclosure_id, ["決算", "重要", "決算"], db)
    row = list_disclosures(db)[0]
    assert row["tags"] in {"決算,重要", "重要,決算"}
    update_disclosure(disclosure_id, {**row, "title": "更新済み決算短信", "is_read": True, "is_favorite": True}, db)
    updated = list_disclosures(db)[0]
    assert updated["title"] == "更新済み決算短信" and updated["is_read"] and updated["is_favorite"]
    summary = dashboard_summary(db)
    assert summary["high"] == 1 and summary["unread"] == 0
    delete_disclosure(disclosure_id, db)
    assert list_disclosures(db) == []


def test_url_and_pdf_security(tmp_path: Path) -> None:
    for value in ("file:///tmp/a.pdf", "javascript:alert(1)", "http://127.0.0.1/a", "http://localhost/a"):
        try: validate_web_url(value)
        except ValueError: pass
        else: raise AssertionError(value)
    allowed = tmp_path / "allowed"; allowed.mkdir()
    pdf = allowed / "safe.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
    assert validate_local_pdf(pdf, allowed) == str(pdf.resolve())
    outside = tmp_path / "outside.pdf"; outside.write_bytes(b"%PDF-1.4\n")
    try: validate_local_pdf(outside, allowed)
    except ValueError: pass
    else: raise AssertionError("path traversal accepted")
    fake_local = allowed / "fake.pdf"; fake_local.write_bytes(b"not a pdf")
    try: validate_local_pdf(fake_local, allowed)
    except ValueError: pass
    else: raise AssertionError("invalid local PDF signature accepted")
    assert Path(save_uploaded_pdf("report.pdf", b"%PDF-1.4\n", allowed)).is_file()
    for name, content in (("bad.exe", b"%PDF-1.4"), ("fake.pdf", b"MZ")):
        try: save_uploaded_pdf(name, content, allowed)
        except ValueError: pass
        else: raise AssertionError(name)


def test_csv_bom_partial_success_duplicate_and_formula_safety(tmp_path: Path) -> None:
    db = tmp_path / "csv.db"; init_db(db)
    save_disclosure(payload(title="=危険な式"), db_path=db)
    exported = export_csv(db)
    assert exported.startswith(b"\xef\xbb\xbf") and b"'=\xe5\x8d\xb1" in exported
    raw = ("ticker,disclosure_type,title,disclosed_at,source_name,source_url,document_url,summary,importance,tags,memo,external_id\n"
           "6976.T,配当修正,配当予想修正,2026-07-14T15:00,企業,,,,高,配当,確認,CSV-1\n"
           "9999.T,その他,不正銘柄,2026-07-14T15:00,企業,,,,通常,,,CSV-2\n").encode("utf-8-sig")
    frame, errors = parse_csv(io.BytesIO(raw)); assert not errors
    result = import_csv(frame, False, db)
    assert result["inserted"] == 1 and result["failed"] == 1 and "3行目" in result["errors"][0]
    assert import_csv(frame.iloc[:1], False, db)["skipped"] == 1


def test_news_link_candidates_manual_link_and_prompt(tmp_path: Path) -> None:
    db = tmp_path / "links.db"; init_db(db)
    _, article_id = save_article(NewsItem(title="2027年3月期 決算短信", url="https://example.com/news"), db_path=db)
    _, disclosure_id = save_disclosure(payload(source_url="https://example.com/news", external_id="LINK-1"), db_path=db)
    candidates = list_news_links(disclosure_id, db)
    assert candidates and not candidates[0]["confirmed"]
    set_news_link(disclosure_id, article_id, True, db)
    assert links_for_news(article_id, db)[0]["id"] == disclosure_id
    prompt = make_prompt(list_disclosures(db)[0], db)
    assert "開示された事実" in prompt and "関連ニュース" in prompt and "売買を断定" in prompt
    assert "None" not in prompt and "nan" not in prompt.lower()


def test_html_is_stored_as_plain_text_and_missing_values_are_safe(tmp_path: Path) -> None:
    db = tmp_path / "plain.db"; init_db(db)
    save_disclosure(payload(title="<b>重要</b>", summary="<script>alert(1)</script>本文", source_url="", document_url="", external_id=""), db_path=db)
    row = list_disclosures(db)[0]
    assert "<" not in row["title"] and "<script>" not in row["summary"]
    assert "None" not in make_prompt(row, db)
