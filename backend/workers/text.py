"""Plain-text worker: short Q&A via the VLM server (no file)."""
from __future__ import annotations

import time

from backend import schemas as S
from backend.clients import llm
from backend.guard.prompts import with_rule, wrap_untrusted


async def run(
    text: str | None,
    prompt: str | None,
    *,
    model_name: str,
    timeout_s: float,
    on_delta=None,
) -> S.ArtifactResult:
    t0 = time.perf_counter()
    system = "You are a concise offline assistant. If you lack evidence, say you can't tell."
    if text and text.strip() and prompt and prompt.strip():
        pasted, rule = wrap_untrusted(text.strip(), "pasted text")
        system, user = with_rule(system, rule), f"{prompt.strip()}\n\n{pasted}"
    else:
        user = (prompt or text or "").strip() or "Hello"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        answer = await llm.chat_stream(
            "vlm", messages, temperature=0.2, max_tokens=600, timeout_s=timeout_s, on_delta=on_delta,
        )
        answer = answer.strip() or "Can't tell."
        return S.ArtifactResult(
            artifact_id="a_text", kind="text", answer=answer, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="ok",
        )
    except Exception as exc:  # noqa: BLE001
        return S.ArtifactResult(
            artifact_id="a_text", kind="text", answer=None, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="failed",
            error=str(exc)[:500],
        )
