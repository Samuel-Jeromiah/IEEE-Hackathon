"""M1 unit tests: routing, quote verification, document finalize — no models required."""
from pathlib import Path

from backend.router import route_kind
from domain import docqa
from domain.verify import quote_in_text


def test_route_by_extension_and_hint():
    assert route_kind(filename="dog.jpg", task_hint=None, has_text=False) == "image"
    assert route_kind(filename="note.m4a", task_hint=None, has_text=False) == "audio"
    assert route_kind(filename="lease.pdf", task_hint=None, has_text=False) == "document"
    assert route_kind(filename=None, task_hint="code", has_text=False) == "code"
    # Document tile + photo → OCR / document path
    assert route_kind(filename="page.jpg", task_hint="document", has_text=False) == "document"


def test_route_by_magic_bytes():
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    pdf = b"%PDF-1.4" + b"\x00" * 20
    assert route_kind(filename="x.bin", task_hint=None, has_text=False, data=jpeg) == "image"
    assert route_kind(filename="x.bin", task_hint=None, has_text=False, data=pdf) == "document"


def test_quote_verification_threshold():
    source = "Rent is due on the first day of each month."
    ok, score = quote_in_text("Rent is due on the first day of each month.", source)
    assert ok and score >= 90
    ok2, _ = quote_in_text("Tenants may keep a dragon in the basement.", source)
    assert not ok2


def test_docqa_finalize_abstains_without_verified_quote(tmp_path: Path):
    pages = [docqa.Page(1, "The deposit is refundable within 30 days.")]
    bad = docqa.finalize_answer(
        proposed_answer="Pizza is free",
        proposed_quote="Pizza is free on Fridays",
        proposed_page=1,
        pages=pages,
        retrieval_score=1.0,
    )
    assert bad.found is False
    assert bad.answer == docqa.NOT_IN_DOC

    good = docqa.finalize_answer(
        proposed_answer="Within 30 days.",
        proposed_quote="The deposit is refundable within 30 days.",
        proposed_page=1,
        pages=pages,
        retrieval_score=5.0,
    )
    assert good.found is True
    assert good.page == 1
    assert good.match_score is not None and good.match_score >= 90


def test_extract_txt_pages(tmp_path: Path):
    p = tmp_path / "note.txt"
    p.write_text("Hello from page one.", encoding="utf-8")
    pages = docqa.extract_pages(p)
    assert len(pages) == 1 and "Hello" in pages[0].text
