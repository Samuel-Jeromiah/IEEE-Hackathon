"""Evidence checks: a quote must appear in the source (rapidfuzz), or we abstain."""
from __future__ import annotations

from rapidfuzz import fuzz

# Contract: found==true only when match_score >= 90
QUOTE_THRESHOLD = 90.0


def quote_in_text(quote: str | None, source: str | None) -> tuple[bool, float]:
    """Return (verified, partial_ratio 0-100). Empty quote never verifies."""
    if not quote or not source:
        return False, 0.0
    q = " ".join(quote.split())
    s = " ".join(source.split())
    if not q or not s:
        return False, 0.0
    score = float(fuzz.partial_ratio(q, s))
    return score >= QUOTE_THRESHOLD, score


def best_page_for_quote(quote: str, pages: list[tuple[int, str]]) -> tuple[int | None, float]:
    """Among (page_number, text) pages, return the best matching page and score."""
    best_page: int | None = None
    best = 0.0
    for page, text in pages:
        _, score = quote_in_text(quote, text)
        if score > best:
            best, best_page = score, page
    return best_page, best
