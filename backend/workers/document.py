"""Document worker: BM25 retrieve → VLM/text answer with quote → verify or abstain."""
from __future__ import annotations

import time

from backend import schemas as S
from backend.clients import llm
from backend.guard.prompts import with_rule, wrap_untrusted
from backend.normalize import NormalizedFile
from backend.workers import image as image_worker
from domain import docqa

DOC_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "quote": {"type": "string"},
        "page": {"type": "integer"},
    },
    "required": ["found", "answer"],
}


async def run(
    media: NormalizedFile,
    prompt: str | None,
    *,
    model_name: str,
    timeout_s: float,
    on_delta=None,
) -> S.ArtifactResult:
    t0 = time.perf_counter()
    aid = f"a_{media.path.stem}"
    question = (prompt or "Summarize the key points.").strip()

    try:
        path = media.path
        # Photo sent via Document tool → OCR first
        if media.kind == "document" and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            text = await image_worker.ocr_text(path, timeout_s=min(timeout_s, 30))
            ocr_path = path.with_suffix(".ocr.txt")
            ocr_path.write_text(text, encoding="utf-8")
            path = ocr_path

        pages = docqa.extract_pages(path)
        if not pages:
            art = S.ArtifactResult(
                artifact_id=aid, kind="document", filename=media.original_name,
                answer=docqa.NOT_IN_DOC,
                doc_qa=S.DocQA(found=False, answer=None, quote=None, page=None,
                               match_score=None, retrieval_score=None),
                model=model_name, latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            if on_delta:
                on_delta(art.answer or "")
            return art

        hits = docqa.retrieve(pages, question, top_k=4)
        retrieval_score = hits[0][1] if hits else 0.0
        context = "\n\n".join(f"[page {p.number}]\n{p.text}" for p, _ in hits) if hits else pages[0].text
        excerpts, rule = wrap_untrusted(context[:12000], "document")

        messages = [
            {
                "role": "system",
                "content": with_rule(
                    "Answer only from the document excerpts. If the answer is not there, set found=false "
                    "and leave quote empty. When found=true, quote must be a verbatim span from the excerpts. "
                    "Return JSON.", rule,
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nExcerpts:\n{excerpts}",
            },
        ]
        data = await llm.chat_json(
            "vlm", messages, DOC_SCHEMA, temperature=0.0, max_tokens=500, timeout_s=timeout_s,
        )
        result = docqa.finalize_answer(
            proposed_answer=data.get("answer"),
            proposed_quote=data.get("quote") if data.get("found") else None,
            proposed_page=data.get("page"),
            pages=pages,
            retrieval_score=retrieval_score,
        )
        answer = result.answer or docqa.NOT_IN_DOC
        if on_delta:
            on_delta(answer)
        return S.ArtifactResult(
            artifact_id=aid, kind="document", filename=media.original_name,
            answer=answer, extracted_text=result.extracted_text[:8000],
            doc_qa=S.DocQA(
                found=result.found, answer=result.answer if result.found else None,
                quote=result.quote, page=result.page, match_score=result.match_score,
                retrieval_score=result.retrieval_score,
            ),
            model=model_name, latency_ms=int((time.perf_counter() - t0) * 1000), status="ok",
        )
    except Exception as exc:  # noqa: BLE001
        return S.ArtifactResult(
            artifact_id=aid, kind="document", filename=media.original_name,
            answer=None, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="failed",
            error=str(exc)[:500],
        )
