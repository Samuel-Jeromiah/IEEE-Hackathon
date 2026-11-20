"""Guide retrieval and quote verification on a tiny fake corpus. No models, no real PDFs."""
from __future__ import annotations

import fitz

from domain.storm import guide


def _pdf(path, pages):
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text, fontsize=10)
    doc.save(path)
    doc.close()


def test_retrieve_and_verify(tmp_path):
    _pdf(tmp_path / "fema_pda_guide_2025-07.pdf", [
        "Introduction to preliminary damage assessments for state and local partners.",
        "Major: Structural damage that requires extensive repairs to the home.",
    ])
    _pdf(tmp_path / "other.pdf", ["Debris removal is Category A of Public Assistance work."])
    guide.load_corpus.cache_clear()

    hits = guide.retrieve("What is major structural damage?", 2, corpus=tmp_path)
    top = hits[0][0]
    assert top.page == 2 and top.title.startswith("FEMA Preliminary Damage Assessment Guide")

    v = guide.verify_quote("Structural damage that requires extensive repairs", [top], corpus=tmp_path)
    assert v and v.page.page == 2 and v.score >= 90
    # a quote from another page still verifies against the whole corpus, with the right page
    v = guide.verify_quote("Debris removal is Category A", [top], corpus=tmp_path)
    assert v and v.page.file == "other.pdf"
    assert guide.verify_quote("FEMA pays for pizza at every shelter", [top], corpus=tmp_path) is None
    assert guide.verify_quote("Major", [top], corpus=tmp_path) is None  # too short to count
    guide.load_corpus.cache_clear()
