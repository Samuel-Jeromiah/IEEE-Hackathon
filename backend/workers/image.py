"""Image worker: describe what is visible; answer a question; say can't tell when unsure."""
from __future__ import annotations

import time
from pathlib import Path

from backend import schemas as S
from backend.clients import llm
from backend.normalize import NormalizedFile

IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "answer": {"type": "string"},
        "extracted_text": {"type": "string"},
        "cant_tell": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description", "answer"],
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
    question = (prompt or "Describe this image in detail.").strip()
    data_url = llm.image_data_url(media.path, media.mime or "image/jpeg")
    messages = [
        {
            "role": "system",
            "content": (
                "You describe photos for an offline assistant. Report only what you can see. "
                "If the user asks for something not visible, say you can't tell. "
                "Put any readable text in extracted_text. Return JSON."
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": question},
            ],
        },
    ]
    try:
        data = await llm.chat_json(
            "vlm", messages, IMAGE_SCHEMA, temperature=0.0, max_tokens=700, timeout_s=timeout_s,
        )
        description = str(data.get("description") or "").strip()
        answer = str(data.get("answer") or description).strip()
        extracted = str(data.get("extracted_text") or "")
        cant = data.get("cant_tell") or []
        if cant and "can't tell" not in answer.lower():
            answer = f"{answer} Can't tell: {', '.join(map(str, cant))}."
        if on_delta and answer:
            on_delta(answer)
        return S.ArtifactResult(
            artifact_id=aid, kind="image", filename=media.original_name,
            converted_from=media.converted_from, description=description, answer=answer,
            extracted_text=extracted, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="ok",
        )
    except Exception as exc:  # noqa: BLE001 — surface as degraded artifact
        return S.ArtifactResult(
            artifact_id=aid, kind="image", filename=media.original_name,
            converted_from=media.converted_from, answer=None, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="failed",
            error=str(exc)[:500],
        )


async def ocr_text(path: Path, *, timeout_s: float) -> str:
    """OCR a page image for the document path (task_hint=document + photo)."""
    data_url = llm.image_data_url(path)
    messages = [
        {"role": "system", "content": "Extract all readable text from the image. Return only the text."},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": "Transcribe every word you can read."},
        ]},
    ]
    return (await llm.chat("vlm", messages, temperature=0.0, max_tokens=1200, timeout_s=timeout_s)).strip()
