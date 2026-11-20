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


def locate_quote(quote: str | None, segments: list[dict]) -> tuple[float | None, float | None, float]:
    """Find where a quote was said: the best window of 1-3 consecutive transcript segments.

    Returns (t_start, t_end, score 0-100). Case is ignored, and ties go to the narrowest window.
    A window shorter than the quote is scored with a full ratio, so a short segment can't match
    a long quote just by being inside it.
    """
    q = " ".join((quote or "").split()).lower()
    best: tuple[float | None, float | None, float] = (None, None, 0.0)
    best_key = (0.0, -9)
    if not q:
        return best
    for i in range(len(segments)):
        for j in range(i, min(i + 3, len(segments))):
            text = " ".join(" ".join(s.get("text", "") for s in segments[i:j + 1]).split()).lower()
            if not text:
                continue
            score = float(fuzz.partial_ratio(q, text) if len(text) >= len(q) else fuzz.ratio(q, text))
            key = (round(score, 1), i - j)
            if key > best_key:
                best_key = key
                best = (float(segments[i]["t_start"]), float(segments[j]["t_end"]), score)
    return best


def best_page_for_quote(quote: str, pages: list[tuple[int, str]]) -> tuple[int | None, float]:
    """Among (page_number, text) pages, return the best matching page and score."""
    best_page: int | None = None
    best = 0.0
    for page, text in pages:
        _, score = quote_in_text(quote, text)
        if score > best:
            best, best_page = score, page
    return best_page, best
