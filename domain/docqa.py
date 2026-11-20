"""Document Q&A: extract pages → BM25 → model answer with quote → verify or abstain."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from domain.verify import QUOTE_THRESHOLD, best_page_for_quote, quote_in_text


@dataclass
class Page:
    number: int  # 1-based
    text: str


@dataclass
class DocAnswer:
    found: bool
    answer: str | None
    quote: str | None
    page: int | None
    match_score: float | None
    retrieval_score: float | None
    extracted_text: str


def extract_pages(path: Path) -> list[Page]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import fitz

        doc = fitz.open(path)
        pages = [Page(i + 1, (doc.load_page(i).get_text("text") or "").strip()) for i in range(doc.page_count)]
        doc.close()
        return pages
    if suffix == ".docx":
        import docx

        paras = [p.text.strip() for p in docx.Document(str(path)).paragraphs if p.text.strip()]
        # Approximate pages by grouping paragraphs
        if not paras:
            return []
        chunk: list[str] = []
        pages: list[Page] = []
        page_no = 1
        for p in paras:
            chunk.append(p)
            if sum(len(x) for x in chunk) > 1500:
                pages.append(Page(page_no, "\n".join(chunk)))
                chunk, page_no = [], page_no + 1
        if chunk:
            pages.append(Page(page_no, "\n".join(chunk)))
        return pages
    # Plain text / markdown
    text = path.read_text(encoding="utf-8", errors="replace")
    return [Page(1, text)] if text.strip() else []


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9']+", text.lower()) if t]


def retrieve(pages: list[Page], question: str, top_k: int = 4) -> list[tuple[Page, float]]:
    if not pages:
        return []
    corpus = [_tokenize(p.text) or ["_empty_"] for p in pages]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(question) or ["_empty_"])
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [(pages[i], float(score)) for i, score in ranked if pages[i].text.strip()]


NOT_IN_DOC = "I couldn't find that in the document."


def finalize_answer(
    *,
    proposed_answer: str | None,
    proposed_quote: str | None,
    proposed_page: int | None,
    pages: list[Page],
    retrieval_score: float | None,
) -> DocAnswer:
    """Verify the model's quote against the document; abstain if it doesn't match."""
    full = "\n\n".join(p.text for p in pages)
    extracted = full[:20000]
    if not proposed_quote:
        return DocAnswer(False, NOT_IN_DOC, None, None, None, retrieval_score, extracted)

    page_map = [(p.number, p.text) for p in pages]
    page, score = best_page_for_quote(proposed_quote, page_map)
    if page is None:
        ok, score = quote_in_text(proposed_quote, full)
        page = proposed_page if ok else None
    else:
        ok = score >= QUOTE_THRESHOLD

    if not ok:
        return DocAnswer(False, NOT_IN_DOC, None, None, score, retrieval_score, extracted)

    answer = (proposed_answer or proposed_quote).strip()
    return DocAnswer(True, answer, proposed_quote.strip(), page or proposed_page, score, retrieval_score, extracted)
