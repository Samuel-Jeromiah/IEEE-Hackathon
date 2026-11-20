"""Guide Q&A over the local FEMA/MEMA corpus: BM25 across every page, then quote verification.

No model calls here; backend/workers/guide.py asks the model and passes its quote back in.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from domain.docqa import extract_pages
from domain.verify import QUOTE_THRESHOLD, quote_in_text

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

# The two FEMA PDFs are saved by hand (fema.gov blocks scripts), so they aren't in manifest.json.
DEFAULT_TITLES = {
    "fema_pda_guide_2025-07.pdf": "FEMA Preliminary Damage Assessment Guide (July 2025)",
    "fema_pda_pocket_guide_2025-07.pdf": "FEMA Preliminary Damage Assessment Pocket Guide (July 2025)",
}


@dataclass(frozen=True)
class GuidePage:
    file: str
    title: str
    page: int
    text: str


@dataclass
class Verified:
    page: GuidePage
    score: float


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _titles(corpus: Path) -> dict[str, str]:
    titles = dict(DEFAULT_TITLES)
    manifest = corpus / "manifest.json"
    if manifest.exists():
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            titles[row["file"]] = row.get("title") or row["file"]
    return titles


@lru_cache(maxsize=2)
def load_corpus(corpus: Path = CORPUS_DIR) -> tuple[list[GuidePage], BM25Okapi | None]:
    titles = _titles(corpus)
    pages: list[GuidePage] = []
    for pdf in sorted(corpus.glob("*.pdf")):
        for p in extract_pages(pdf):
            if len(p.text) > 40:
                pages.append(GuidePage(pdf.name, titles.get(pdf.name, pdf.stem), p.number, p.text))
    if not pages:
        return [], None
    return pages, BM25Okapi([_tokens(p.text) or ["_"] for p in pages])


def retrieve(question: str, k: int = 4, corpus: Path = CORPUS_DIR) -> list[tuple[GuidePage, float]]:
    pages, bm25 = load_corpus(corpus)
    if not bm25:
        return []
    scores = bm25.get_scores(_tokens(question) or ["_"])
    ranked = sorted(range(len(pages)), key=lambda i: scores[i], reverse=True)[:k]
    return [(pages[i], float(scores[i])) for i in ranked if scores[i] > 0]


def verify_quote(quote: str | None, hits: list[GuidePage], corpus: Path = CORPUS_DIR) -> Verified | None:
    """Find the page the quote really comes from: retrieved pages first, then the whole corpus."""
    if not quote or len(quote.split()) < 3:
        return None
    for pool in (hits, load_corpus(corpus)[0]):
        best: Verified | None = None
        for page in pool:
            ok, score = quote_in_text(quote, page.text)
            if ok and (best is None or score > best.score):
                best = Verified(page, score)
        if best and best.score >= QUOTE_THRESHOLD:
            return best
    return None
