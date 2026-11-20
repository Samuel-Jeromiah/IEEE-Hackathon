"""Guide worker: retrieve FEMA/MEMA pages → model answers with a verbatim quote → verify or abstain."""
from __future__ import annotations

import asyncio

from backend import schemas as S
from backend.clients import llm
from backend.guard import gate, safety
from backend.guard.policy import load_policy
from backend.guard.prompts import with_rule, wrap_untrusted
from domain.storm import guide

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "quote": {"type": "string"},
    },
    "required": ["found", "answer", "quote"],
}

SYSTEM = (
    "You answer questions for small-town emergency managers using only the guide excerpts. "
    "If the excerpts answer the question, set found=true, give a short plain answer (one to three "
    "sentences), and copy one supporting sentence word for word into quote. If they don't, set "
    "found=false and leave answer and quote empty. Return JSON."
)


async def ask(question: str, *, timeout_s: float = 60.0) -> S.GuideAnswer:
    pol = load_policy()
    not_found = pol.abstain("guide")
    checked = gate.check_request(kind="text", prompt=question, text=None)
    if not checked.ok or not checked.question:
        return S.GuideAnswer(found=False, answer=checked.message or not_found)
    q = checked.question
    if safety.check_patterns(q).action != "allow":
        return S.GuideAnswer(found=False, answer=pol.messages.declined)

    hits = await asyncio.to_thread(guide.retrieve, q, 4)
    if not hits:
        return S.GuideAnswer(found=False, answer=not_found)
    context = "\n\n".join(
        f"[{i + 1}] {p.title}, page {p.page}\n{p.text[:3500]}" for i, (p, _) in enumerate(hits)
    )
    excerpts, rule = wrap_untrusted(context, "guides")
    messages = [
        {"role": "system", "content": with_rule(SYSTEM, rule)},
        {"role": "user", "content": f"Question: {q}\n\nExcerpts:\n{excerpts}"},
    ]
    data = await llm.chat_json("vlm", messages, SCHEMA, temperature=0.0,
                               max_tokens=pol.max_tokens("document"), timeout_s=timeout_s)
    if not data.get("found"):
        return S.GuideAnswer(found=False, answer=not_found)
    quote = str(data.get("quote") or "").strip()
    verified = await asyncio.to_thread(guide.verify_quote, quote, [p for p, _ in hits])
    if not verified:
        return S.GuideAnswer(found=False, answer=not_found)
    answer = str(data.get("answer") or "").strip() or quote
    return S.GuideAnswer(found=True, answer=answer, quote=quote, document=verified.page.title,
                         page=verified.page.page, match_score=round(verified.score, 1))


def warm() -> None:
    """Parse the PDFs once at startup so the first question is fast."""
    guide.load_corpus()
