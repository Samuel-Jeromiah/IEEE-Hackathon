"""Video worker: sample frames (PyAV) + Whisper/CLAP on audio + one VLM call citing times."""
from __future__ import annotations

import asyncio
import base64
import io
import time
from dataclasses import dataclass
from pathlib import Path

import av
from PIL import Image, ImageOps

from backend import manager
from backend import schemas as S
from backend.clients import llm
from backend.guard.prompts import with_rule, wrap_untrusted
from backend.normalize import NormalizedFile

VIDEO_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "answer": {"type": "string"},
        "frame_captions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "caption": {"type": "string"},
                },
            },
        },
    },
    "required": ["description", "answer"],
}


@dataclass
class ExtractedFrame:
    idx: int
    t: float
    path: Path
    thumb_b64: str


def _fmt_ts(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def _stream_rotation(stream) -> int:
    """Return clockwise rotation degrees from container metadata, if present."""
    try:
        # Common on phone videos
        for key in ("rotate",):
            if key in (stream.metadata or {}):
                return int(float(stream.metadata[key])) % 360
        # displaymatrix side data (degrees are often negative of clockwise)
        for sd in getattr(stream, "side_data", None) or []:
            if getattr(sd, "type", None) and "DISPLAYMATRIX" in str(sd.type).upper():
                # PyAV may expose rotation via to_json; fall through
                pass
    except Exception:
        return 0
    return 0


def _resize(im: Image.Image, max_px: int) -> Image.Image:
    w, h = im.size
    scale = max_px / max(w, h) if max(w, h) > max_px else 1.0
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im


def _thumb_b64(im: Image.Image, thumb_px: int = 160) -> str:
    t = _resize(im.copy(), thumb_px)
    buf = io.BytesIO()
    t.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def extract_frames(
    path: Path,
    dest_dir: Path,
    *,
    max_frames: int,
    frame_px: int,
    max_s: float,
) -> tuple[list[ExtractedFrame], float]:
    """Sample up to max_frames evenly across the (possibly truncated) clip.

    Returns (frames, duration_used_seconds).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    frames: list[ExtractedFrame] = []
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            return [], 0.0
        rotation = _stream_rotation(stream)
        duration = 0.0
        if container.duration is not None:
            duration = float(container.duration) / av.time_base
        elif stream.duration is not None and stream.time_base is not None:
            duration = float(stream.duration * stream.time_base)
        if duration <= 0:
            # Fall back: decode until we have something and estimate
            duration = float(max_s)

        use_dur = min(duration, float(max_s))
        n = max(1, int(max_frames))
        if use_dur < 0.5:
            times = [0.0]
        else:
            # Evenly spaced across the clip (include start; stay shy of the end)
            times = [use_dur * i / max(n - 1, 1) for i in range(n)] if n > 1 else [0.0]
            times = [min(t, max(0.0, use_dur - 0.05)) for t in times]

        for idx, t in enumerate(times):
            # Seek near the target (keyframe seek, then decode forward)
            target_pts = int(t / stream.time_base) if stream.time_base else 0
            try:
                container.seek(target_pts, stream=stream, any_frame=False, backward=True)
            except av.AVError:
                try:
                    container.seek(int(t * av.time_base))
                except av.AVError:
                    continue
            got = None
            for packet in container.demux(stream):
                for frame in packet.decode():
                    ft = float(frame.time or 0.0)
                    if ft + 0.15 < t and idx < len(times) - 1:
                        continue
                    got = frame
                    break
                if got is not None:
                    break
            if got is None:
                continue
            arr = got.to_ndarray(format="rgb24")
            im = Image.fromarray(arr)
            if rotation:
                # Pillow rotate is counter-clockwise; metadata rotate is often clockwise
                im = im.rotate(-rotation, expand=True)
            im = ImageOps.exif_transpose(im)
            im = _resize(im, frame_px)
            out = dest_dir / f"frame_{idx:02d}.jpg"
            im.save(out, format="JPEG", quality=88)
            frames.append(ExtractedFrame(
                idx=idx,
                t=float(got.time or t),
                path=out,
                thumb_b64=_thumb_b64(im),
            ))
    return frames, use_dur if frames else 0.0


async def run(
    media: NormalizedFile,
    prompt: str | None,
    *,
    model_name: str,
    timeout_s: float,
    max_frames: int = 12,
    frame_px: int = 512,
    max_s: float = 90.0,
    on_delta=None,
) -> S.ArtifactResult:
    t0 = time.perf_counter()
    aid = f"a_{media.path.stem}"
    question = (prompt or "What happens in this clip? Note important moments with times.").strip()
    work = media.work_dir or media.path.parent
    frame_dir = work / "frames"

    try:
        extracted, used_s = await asyncio.to_thread(
            extract_frames, media.path, frame_dir,
            max_frames=max_frames, frame_px=frame_px, max_s=max_s,
        )
        # Audio in parallel with (already done) frames — Whisper/CLAP on the same file
        segments, sounds = await asyncio.gather(
            asyncio.to_thread(manager.transcribe, media.path),
            asyncio.to_thread(manager.classify_sounds, media.path),
        )

        transcript = [
            S.TranscriptSegment(t_start=s["t_start"], t_end=s["t_end"], text=s["text"])
            for s in segments if s["text"] and s["t_start"] <= used_s + 1.0
        ]
        sound_events = [
            S.SoundEvent(t_start=e["t_start"], t_end=e["t_end"], label=e["label"], score=e["score"])
            for e in sounds if e["t_start"] <= used_s + 1.0
        ]

        if not extracted and not transcript and not sound_events:
            return S.ArtifactResult(
                artifact_id=aid, kind="video", filename=media.original_name,
                converted_from=media.converted_from,
                answer="Can't tell — no frames or audio could be read from this video.",
                status="failed", model=model_name,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error="no_frames_or_audio",
            )

        frame_list = "\n".join(
            f"Frame {f.idx} at {_fmt_ts(f.t)}" for f in extracted
        ) or "(no frames)"
        transcript_block = "\n".join(
            f"[{_fmt_ts(s.t_start)}-{_fmt_ts(s.t_end)}] {s.text}" for s in transcript
        ) or "(no speech detected)"
        transcript_wrapped, rule = wrap_untrusted(transcript_block, "transcript")
        sounds_block = "\n".join(
            f"[{_fmt_ts(s.t_start)}-{_fmt_ts(s.t_end)}] {s.label} ({s.score:.2f})" for s in sound_events
        ) or "(no strong sound labels)"

        content: list[dict] = []
        for f in extracted:
            content.append({
                "type": "image_url",
                "image_url": {"url": llm.image_data_url(f.path)},
            })
        content.append({
            "type": "text",
            "text": (
                f"Question: {question}\n\n"
                f"Frames (in order):\n{frame_list}\n\n"
                f"Transcript:\n{transcript_wrapped}\n\n"
                f"Sounds:\n{sounds_block}\n\n"
                "Describe what happens. Answer the question. Cite times that match the frames "
                "(e.g. 0:04). Only use times that appear above. Return JSON with description, "
                "answer, and optional frame_captions [{idx, caption}]."
            ),
        })

        messages = [
            {
                "role": "system",
                "content": with_rule(
                    "You analyze short video clips from sampled frames plus transcript and sounds. "
                    "Report only what the frames/audio support. If you can't tell, say so. "
                    "Cite real frame times. Return JSON.", rule,
                ),
            },
            {"role": "user", "content": content},
        ]

        data = await llm.chat_json(
            "vlm", messages, VIDEO_SCHEMA, temperature=0.0, max_tokens=900, timeout_s=timeout_s,
        )
        description = str(data.get("description") or "").strip()
        answer = str(data.get("answer") or description).strip() or "Can't tell from this clip."
        captions = {
            int(c.get("idx")): str(c.get("caption") or "").strip()
            for c in (data.get("frame_captions") or [])
            if isinstance(c, dict) and c.get("idx") is not None
        }

        schema_frames = [
            S.Frame(
                idx=f.idx,
                t=round(f.t, 2),
                caption=captions.get(f.idx) or None,
                thumb_b64=f.thumb_b64,
            )
            for f in extracted
        ]
        if on_delta and answer:
            on_delta(answer)

        return S.ArtifactResult(
            artifact_id=aid, kind="video", filename=media.original_name,
            converted_from=media.converted_from,
            description=description or None,
            answer=answer,
            transcript=transcript,
            sounds=sound_events,
            frames=schema_frames,
            model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            status="ok",
        )
    except Exception as exc:  # noqa: BLE001
        return S.ArtifactResult(
            artifact_id=aid, kind="video", filename=media.original_name,
            converted_from=media.converted_from, answer=None, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="failed",
            error=str(exc)[:500],
        )
