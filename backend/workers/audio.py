"""Audio worker: Whisper (16 kHz) + CLAP (48 kHz) + answer citing timestamps."""
from __future__ import annotations

import asyncio
import time

from backend import manager
from backend import schemas as S
from backend.clients import llm
from backend.guard.prompts import with_rule, wrap_untrusted
from backend.normalize import NormalizedFile

AUDIO_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "t_start": {"type": "number"},
                    "t_end": {"type": "number"},
                    "quote": {"type": "string"},
                },
            },
        },
    },
    "required": ["answer"],
}


def _fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


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
    question = (prompt or "What was said, and what sounds do you hear?").strip()

    try:
        # Run Whisper + CLAP off the event loop (CPU-heavy).
        segments, sounds = await asyncio.gather(
            asyncio.to_thread(manager.transcribe, media.path),
            asyncio.to_thread(manager.classify_sounds, media.path),
        )
        transcript = [
            S.TranscriptSegment(t_start=s["t_start"], t_end=s["t_end"], text=s["text"])
            for s in segments if s["text"]
        ]
        sound_events = [
            S.SoundEvent(t_start=e["t_start"], t_end=e["t_end"], label=e["label"], score=e["score"])
            for e in sounds
        ]

        transcript_block = "\n".join(
            f"[{_fmt_ts(s.t_start)}-{_fmt_ts(s.t_end)}] {s.text}" for s in transcript
        ) or "(no speech detected)"
        sounds_block = "\n".join(
            f"[{_fmt_ts(s.t_start)}-{_fmt_ts(s.t_end)}] {s.label} ({s.score:.2f})" for s in sound_events
        ) or "(no strong sound labels)"
        transcript_wrapped, rule = wrap_untrusted(transcript_block, "transcript")

        messages = [
            {
                "role": "system",
                "content": with_rule(
                    "Answer using the transcript and sound labels. Cite times like 0:04-0:08. "
                    "If the transcript does not support the answer, say you can't tell. Return JSON.", rule,
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\nTranscript:\n{transcript_wrapped}\n\nSounds:\n{sounds_block}"
                ),
            },
        ]
        data = await llm.chat_json(
            "vlm", messages, AUDIO_SCHEMA, temperature=0.0, max_tokens=500, timeout_s=timeout_s,
        )
        answer = str(data.get("answer") or "").strip()
        if not answer:
            answer = "Can't tell from the audio."
        if on_delta:
            on_delta(answer)

        return S.ArtifactResult(
            artifact_id=aid, kind="audio", filename=media.original_name,
            converted_from=media.converted_from, answer=answer,
            transcript=transcript, sounds=sound_events,
            model=model_name, latency_ms=int((time.perf_counter() - t0) * 1000), status="ok",
        )
    except Exception as exc:  # noqa: BLE001
        return S.ArtifactResult(
            artifact_id=aid, kind="audio", filename=media.original_name,
            converted_from=media.converted_from, answer=None, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="failed",
            error=str(exc)[:500],
        )
