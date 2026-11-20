"""Job runner: progress events (buffered for late SSE subscribers), timeouts, JSONL log."""
from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend import manager, normalize, router
from backend import schemas as S
from backend.config import load_models_config, selected_profile_name
from backend.guard import gate, outputs, safety
from backend.guard.policy import load_policy
from backend.workers import audio as audio_worker
from backend.workers import code as code_worker
from backend.workers import document as document_worker
from backend.workers import image as image_worker
from backend.workers import text as text_worker
from backend.workers import video as video_worker

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "logs" / "jobs.jsonl"


@dataclass
class EventHub:
    """Buffers SSE events per request_id so clients that connect first still see them all."""

    _buffers: dict[str, list[S.ProgressEvent]] = field(default_factory=lambda: defaultdict(list))
    _waiters: dict[str, list[asyncio.Queue]] = field(default_factory=lambda: defaultdict(list))
    _done: set[str] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def publish(self, request_id: str, event: S.ProgressEvent) -> None:
        async with self._lock:
            self._buffers[request_id].append(event)
            if event.type in {"done", "error"}:
                self._done.add(request_id)
            waiters = list(self._waiters.get(request_id, []))
        for q in waiters:
            await q.put(event)

    async def subscribe(self, request_id: str) -> AsyncIterator[S.ProgressEvent]:
        q: asyncio.Queue[S.ProgressEvent] = asyncio.Queue()
        async with self._lock:
            history = list(self._buffers.get(request_id, []))
            finished = request_id in self._done
            self._waiters[request_id].append(q)
        for ev in history:
            yield ev
        if finished:
            return
        try:
            while True:
                ev = await q.get()
                yield ev
                if ev.type in {"done", "error"}:
                    break
        finally:
            async with self._lock:
                lst = self._waiters.get(request_id, [])
                if q in lst:
                    lst.remove(q)

    async def cleanup(self, request_id: str, delay_s: float = 120.0) -> None:
        await asyncio.sleep(delay_s)
        async with self._lock:
            self._buffers.pop(request_id, None)
            self._waiters.pop(request_id, None)
            self._done.discard(request_id)


HUB = EventHub()


def _log_job(row: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:10]}"


def _profile() -> dict:
    cfg = load_models_config()
    name = selected_profile_name() or "mac16"
    return cfg["profiles"][name]


def _guard_url() -> str | None:
    srv = load_models_config().get("servers", {}).get("guard")
    return f"http://{srv['host']}:{srv['port']}/v1" if srv else None


async def _policy_case(rid: str, t0: float, action: S.PolicyAction, reason: str | None,
                       message: str) -> S.CaseFile:
    """A request the guardrails stopped before any model ran."""
    case = S.CaseFile(
        request_id=rid, status="ok", answer=message,
        policy=S.PolicyNote(action=action, reason=reason, message=message),
        timings_ms={"total": int((time.perf_counter() - t0) * 1000)},
    )
    await HUB.publish(rid, S.ProgressEvent(type="done", pct=100, case_id=rid))
    _log_job({"ts": datetime.now(UTC).isoformat(), "request_id": rid, "kinds": [],
              "status": "ok", "policy": action, "reason": reason})
    return case


def _prepare_media(
    filename: str | None,
    data: bytes,
    kind: str,
    dest: Path,
    limits: dict,
) -> normalize.NormalizedFile:
    raw = normalize.write_upload(data, filename, dest)
    ext = Path(filename or raw.name).suffix.lower()
    if kind == "image" or (kind == "document" and ext in router.IMAGE_EXT):
        max_px = limits["ocr_max_px"] if kind == "document" else limits["image_max_px"]
        nf = normalize.normalize_image(raw, dest, max_px, original_name=filename)
        nf.kind = kind
        return nf
    if kind == "audio":
        return normalize.copy_as(
            raw, dest, "audio", original_name=filename,
            converted_from=ext.lstrip(".") or None,
        )
    return normalize.copy_as(raw, dest, kind, original_name=filename)


async def analyze(
    *,
    files: list[tuple[str | None, bytes]],
    text: str | None,
    prompt: str | None,
    task_hint: str | None,
    request_id: str | None,
) -> S.CaseFile:
    rid = request_id or new_request_id()
    profile = _profile()
    limits = profile["limits"]
    timeouts = profile["timeouts_s"]
    vlm_name = profile["vlm"]
    t0 = time.perf_counter()
    degraded: list[str] = []
    work = normalize.make_work_dir()
    loop = asyncio.get_running_loop()

    async def progress(stage: str, pct: float, message: str) -> None:
        await HUB.publish(rid, S.ProgressEvent(type="progress", stage=stage, pct=pct, message=message))

    def on_delta_async(chunk: str) -> None:
        loop.create_task(HUB.publish(rid, S.ProgressEvent(type="delta", delta=chunk)))

    try:
        first_name, first_data = files[0] if files else (None, None)
        gate_kind = router.route_kind(filename=first_name, task_hint=task_hint,
                                      has_text=bool(text), data=first_data)
        checked = gate.check_request(kind=gate_kind, prompt=prompt, text=text,
                                     file_sizes=[len(d) for _, d in files])
        if not checked.ok:
            return await _policy_case(rid, t0, "declined", checked.reason, checked.message or "")
        prompt, text = checked.question, checked.text
        verdict = await safety.classify(prompt or text, _guard_url())
        if verdict.action != "allow":
            pol = load_policy()
            msg = pol.messages.support if verdict.action == "support" else pol.messages.declined
            return await _policy_case(rid, t0, "declined", verdict.reason, msg)

        await progress("normalize", 8, "Reading your file")
        media_list: list[normalize.NormalizedFile] = []
        kinds: list[str] = []

        if not files:
            kind = router.route_kind(filename=None, task_hint=task_hint, has_text=bool(text))
            if kind == "code":
                kinds.append("code")
                media_list.append(normalize.NormalizedFile(
                    path=work / "code.txt", kind="code", work_dir=work,
                    extra={"text": text or "", "prompt": prompt or ""},
                ))
                (work / "code.txt").write_text(prompt or text or "", encoding="utf-8")
            elif kind == "document" and text:
                kinds.append("document")
                media_list.append(normalize.text_file(text, work / "0"))
            else:
                kinds.append("text")
                media_list.append(normalize.NormalizedFile(
                    path=work / "empty.txt", kind="text", work_dir=work,
                    extra={"text": text or "", "prompt": prompt or ""},
                ))
                (work / "empty.txt").write_text(text or "", encoding="utf-8")

        for i, (filename, data) in enumerate(files):
            kind = router.route_kind(
                filename=filename, task_hint=task_hint, has_text=bool(text), data=data,
            )
            if kind == "code":
                # File + code hint: still M2 for execution; answer as text for now
                kind = "text"
            media_list.append(_prepare_media(filename, data, kind, work / str(i), limits))
            kinds.append(kind)

        await progress("extract", 35, "Looking and listening")
        artifacts: list[S.ArtifactResult] = []

        async def run_one(media: normalize.NormalizedFile, kind: str) -> S.ArtifactResult:
            timeout = float(timeouts.get(kind, 60))
            deltas: list[str] = []

            def collect(chunk: str) -> None:
                deltas.append(chunk)
                on_delta_async(chunk)

            async def call() -> S.ArtifactResult:
                if kind == "image":
                    return await image_worker.run(
                        media, prompt, model_name=vlm_name, timeout_s=timeout, on_delta=collect,
                    )
                if kind == "document":
                    return await document_worker.run(
                        media, prompt, model_name=vlm_name, timeout_s=timeout, on_delta=collect,
                    )
                if kind == "audio":
                    return await audio_worker.run(
                        media, prompt,
                        model_name=f"{profile['asr']}+{profile['sound']}+{vlm_name}",
                        timeout_s=timeout, on_delta=collect,
                    )
                if kind == "text":
                    return await text_worker.run(
                        media.extra.get("text") or text,
                        prompt or media.extra.get("prompt"),
                        model_name=vlm_name, timeout_s=timeout, on_delta=collect,
                    )
                if kind == "video":
                    return await video_worker.run(
                        media, prompt,
                        model_name=f"{vlm_name}+{profile['asr']}+{profile['sound']}",
                        timeout_s=timeout,
                        max_frames=int(limits.get("video_max_frames", 12)),
                        frame_px=int(limits.get("frame_px", 512)),
                        max_s=float(limits.get("video_max_s", 90)),
                        on_delta=collect,
                    )
                if kind == "code":
                    return await code_worker.run(
                        prompt or media.extra.get("prompt") or media.extra.get("text") or "",
                        model_name=profile["coder"], timeout_s=timeout, on_delta=collect,
                    )
                return await text_worker.run(
                    text, prompt, model_name=vlm_name, timeout_s=timeout, on_delta=collect,
                )

            try:
                return await asyncio.wait_for(call(), timeout=timeout + 5)
            except TimeoutError:
                degraded.append(f"{kind}_timeout")
                partial = "".join(deltas).strip()
                return S.ArtifactResult(
                    artifact_id=f"a_{kind}",
                    kind=kind,  # type: ignore[arg-type]
                    filename=media.original_name,
                    answer=partial or "Timed out; partial result.",
                    status="degraded",
                    model=vlm_name,
                    latency_ms=int(timeout * 1000),
                    error="timeout",
                )

        notes: list[S.PolicyNote] = []
        for media, kind in zip(media_list, kinds, strict=True):
            await progress("answer", 70, "Writing the answer")
            art = await run_one(media, kind)
            if kind != "code" and art.status != "failed":
                art.answer, note = outputs.finalize(kind, art.answer, prompt)
                notes.append(note)
            artifacts.append(art)

        answer = next((a.answer for a in artifacts if a.answer), None)
        policy = next((n for n in notes if n.action != "answered"), S.PolicyNote())
        if any(n.action == "answered" for n in notes):
            policy = S.PolicyNote()
        status: S.Status = "ok"
        if any(a.status == "failed" for a in artifacts) and not answer:
            status = "failed"
        elif degraded or any(a.status == "degraded" for a in artifacts):
            status = "degraded"

        total_ms = int((time.perf_counter() - t0) * 1000)
        ms = manager.model_status()
        case = S.CaseFile(
            request_id=rid,
            status=status,
            policy=policy,
            answer=answer,
            artifacts=artifacts,
            timings_ms={"total": total_ms},
            degraded=degraded,
            models={
                "vlm": vlm_name,
                "coder": profile["coder"],
                "asr": ms.get("asr", "not_loaded"),
                "sound": ms.get("sound", "not_loaded"),
            },
        )
        await HUB.publish(rid, S.ProgressEvent(type="done", pct=100, case_id=rid))
        _log_job({
            "ts": datetime.now(UTC).isoformat(),
            "request_id": rid,
            "kinds": kinds,
            "status": status,
            "policy": policy.action,
            "latency_ms": total_ms,
            "degraded": degraded,
        })
        return case
    except Exception as exc:  # noqa: BLE001
        await HUB.publish(rid, S.ProgressEvent(type="error", message=str(exc)[:300]))
        raise
    finally:
        asyncio.create_task(HUB.cleanup(rid))
        shutil.rmtree(work, ignore_errors=True)
