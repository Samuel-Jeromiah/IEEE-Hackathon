"""StormLog API (FastAPI).

Start it through the launcher:
    uv run python -m serving.launch --stub              # example data, no models
    uv run python -m serving.launch --profile mac16     # model servers + API
or directly:
    STORMLOG_MODE=stub uv run uvicorn backend.main:create_app --factory --port 8000

Stub mode serves the examples in backend/stub_data.py for every endpoint, so the
frontend can be built without models. Real mode runs the workers for image, document,
audio, video, text and code, behind the guardrails in backend/guard/, builds storm sites
from uploads (backend/workers/site.py), and runs incident analysis as sandboxed code. The
town report's totals and FEMA threshold come from fixed rules in both modes.
Stub hooks: a document question containing "pizza" returns the not-found example, and a
prompt containing "keylogger" returns the declined example.
"""
from __future__ import annotations

import asyncio
import base64
import csv
import html
import io
import logging
import os
import re
import socket
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import jobs, manager, storm_report, storm_store, stub_data
from backend import schemas as S
from backend.config import load_models_config
from backend.guard import gate, safety
from backend.guard.policy import load_policy
from backend.router import route_kind
from backend.workers import analysis as analysis_worker
from backend.workers import guide as guide_worker
from backend.workers import site as site_worker

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
SAFE_NAME = re.compile(r"[\w-][\w.-]*")
log = logging.getLogger("stormlog")


def lan_ip() -> str:
    """Best-effort LAN address. A UDP connect sends no packets; it only selects a route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def qr_png_b64(text: str) -> str | None:
    try:
        import qrcode

        buf = io.BytesIO()
        qrcode.make(text).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def placeholder_png(label: str) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (320, 200), (200, 205, 210))
    ImageDraw.Draw(img).text((12, 90), label[:48], fill=(40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def sites_csv(sites: list[S.Site]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["site_id", "kind", "location", "damage_level", "pa_category", "damage", "hazards",
                "est_cost_usd", "status", "evidence_items"])
    for s in sites:
        damage = s.fields.get("damage")
        w.writerow([s.id, s.kind, s.location.text or "", s.level or "", s.category or "",
                    (damage.value if damage else "") or "", "; ".join(h.type for h in s.hazards),
                    "" if s.est_cost is None else f"{s.est_cost:.2f}", s.status, len(s.evidence)])
    return out.getvalue()


def create_app() -> FastAPI:
    mode = os.environ.get("STORMLOG_MODE", "stub")
    profile = os.environ.get("STORMLOG_PROFILE") or None
    port = int(os.environ.get("STORMLOG_PORT", "8000"))
    app = FastAPI(title="StormLog API", version="0.1.0")
    store = stub_data.StubStore() if mode == "stub" else storm_store.FileStore()

    if mode != "stub":
        @app.on_event("startup")
        async def warm_guides() -> None:
            asyncio.create_task(asyncio.to_thread(guide_worker.warm))

    # ------------------------------------------------------------------ service
    @app.get("/api/health", response_model=S.Health)
    async def health() -> S.Health:
        if mode == "stub":
            return stub_data.examples()["health_stub"]
        servers = load_models_config()["servers"]
        models: dict[str, str] = dict(manager.model_status())
        async with httpx.AsyncClient(timeout=2.0) as client:
            for name, srv in servers.items():
                try:
                    r = await client.get(f"http://{srv['host']}:{srv['port']}/health")
                    models[name] = "up" if r.status_code == 200 else "down"
                except httpx.HTTPError:
                    models[name] = "down"
        status = "ok" if models.get("vlm") == "up" else "degraded"
        return S.Health(status=status, mode="real", profile=profile, models=models)

    @app.get("/api/info", response_model=S.Info)
    async def info() -> S.Info:
        lan = f"http://{lan_ip()}:{port}"
        return S.Info(local_url=f"http://127.0.0.1:{port}", lan_url=lan, qr_png_b64=qr_png_b64(lan))

    # ------------------------------------------------------------------ general mode
    @app.post("/api/analyze", response_model=S.CaseFile)
    async def analyze(
        files: list[UploadFile] = File(default=[]),
        text: str | None = Form(default=None),
        prompt: str | None = Form(default=None),
        task_hint: str | None = Form(default=None),
        request_id: str | None = Form(default=None),
    ) -> S.CaseFile:
        if mode == "stub":
            first = files[0].filename if files else None
            kind = route_kind(filename=first, task_hint=task_hint, has_text=bool(text))
            if "keylogger" in f"{prompt or ''} {text or ''}".lower():
                return stub_data.casefile_declined(request_id or stub_data.new_id("req"))
            not_found = kind == "document" and "pizza" in (prompt or "").lower()
            result = stub_data.casefile(kind, request_id or stub_data.new_id("req"), not_found=not_found)
            if first:
                result.artifacts[0].filename = first
            return result

        payloads: list[tuple[str | None, bytes]] = []
        for f in files:
            payloads.append((f.filename, await f.read()))
        return await jobs.analyze(
            files=payloads, text=text, prompt=prompt, task_hint=task_hint, request_id=request_id,
        )

    @app.get("/api/events/{request_id}")
    async def events(request_id: str) -> StreamingResponse:
        if mode == "stub":
            steps = [
                S.ProgressEvent(type="progress", stage="normalize", pct=10, message="Reading your file"),
                S.ProgressEvent(type="progress", stage="extract", pct=45, message="Looking and listening"),
                S.ProgressEvent(type="progress", stage="answer", pct=75, message="Writing the answer"),
                # Deltas are raw text chunks that carry their own spacing, like model tokens.
                *[S.ProgressEvent(type="delta", delta=w if i == 0 else f" {w}")
                  for i, w in enumerate("This is a streamed stub answer.".split(" "))],
                S.ProgressEvent(type="done", pct=100, case_id=request_id),
            ]

            async def stub_gen():
                for ev in steps:
                    yield f"data: {ev.model_dump_json(exclude_none=True)}\n\n"
                    await asyncio.sleep(0.05)

            return StreamingResponse(stub_gen(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        async def real_gen():
            async for ev in jobs.HUB.subscribe(request_id):
                yield f"data: {ev.model_dump_json(exclude_none=True)}\n\n"

        return StreamingResponse(real_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------ storm mode
    def get_incident(incident_id: str) -> S.Incident:
        if incident_id not in store.incidents:
            raise HTTPException(404, f"no incident {incident_id}")
        return store.incidents[incident_id]

    def incident_sites(incident_id: str) -> list[S.Site]:
        return [s for s in store.sites.values() if s.incident_id == incident_id]

    @app.get("/api/incidents", response_model=list[S.Incident])
    async def list_incidents() -> list[S.Incident]:
        return list(store.incidents.values())

    @app.post("/api/incidents", response_model=S.Incident)
    async def create_incident(body: S.IncidentCreate) -> S.Incident:
        inc = S.Incident(**body.model_dump(), id=stub_data.new_id("inc"), created_at=stub_data.now())
        store.incidents[inc.id] = inc
        store.save()
        return inc

    @app.get("/api/incidents/{incident_id}", response_model=S.IncidentReport)
    async def incident_report(incident_id: str) -> S.IncidentReport:
        return storm_report.build_report(get_incident(incident_id), incident_sites(incident_id))

    @app.post("/api/incidents/{incident_id}/sites", response_model=S.Site)
    async def add_site(
        incident_id: str,
        photo: UploadFile | None = File(default=None),
        voice: UploadFile | None = File(default=None),
        video: UploadFile | None = File(default=None),
        location_text: str | None = Form(default=None),
        request_id: str | None = Form(default=None),
    ) -> S.Site:
        get_incident(incident_id)
        if mode == "stub":
            return store.add_site(incident_id, location_text)

        async def read(f: UploadFile | None) -> tuple[str | None, bytes] | None:
            data = await f.read() if f else b""
            return (f.filename, data) if data else None

        uploads = {"photo": await read(photo), "voice": await read(voice), "video": await read(video)}
        if not any(uploads.values()):
            raise HTTPException(400, "Add a photo, a voice note or a video.")
        rid = request_id or jobs.new_request_id()

        async def progress(stage: str, pct: float, message: str) -> None:
            await jobs.HUB.publish(rid, S.ProgressEvent(type="progress", stage=stage, pct=pct, message=message))

        try:
            site = await site_worker.build_site(
                incident_id=incident_id, site_id=stub_data.new_id("site"), location_text=location_text,
                profile=jobs._profile(), progress=progress, **uploads)
        except httpx.HTTPError as exc:
            await jobs.HUB.publish(rid, S.ProgressEvent(type="error", message="model not responding"))
            raise HTTPException(503, "The local model isn't responding. Try again in a moment.") from exc
        except Exception as exc:
            log.exception("site build failed")
            await jobs.HUB.publish(rid, S.ProgressEvent(type="error", message=str(exc)[:300]))
            raise HTTPException(422, "Couldn't read one of the files. Try a JPEG photo, "
                                     "a voice memo, or an MP4/MOV video.") from exc
        finally:
            asyncio.create_task(jobs.HUB.cleanup(rid))
        store.put_site(site)
        await jobs.HUB.publish(rid, S.ProgressEvent(type="done", pct=100, case_id=site.id))
        return site

    @app.patch("/api/sites/{site_id}", response_model=S.Site)
    async def patch_site(site_id: str, body: S.SitePatch) -> S.Site:
        site = store.sites.get(site_id)
        if not site:
            raise HTTPException(404, f"no site {site_id}")
        for key in ("kind", "level", "category", "est_cost", "status"):
            value = getattr(body, key)
            if value is not None:
                setattr(site, key, value)
        if body.location_text is not None:
            site.location = S.Location(text=body.location_text, source="typed")
        for name, value in (body.fields or {}).items():
            site.fields[name] = S.FieldValue(value=value, needs_review=False)  # a person entered it
        store.save()
        return site

    @app.get("/api/incidents/{incident_id}/export.csv")
    async def export_csv(incident_id: str) -> Response:
        get_incident(incident_id)
        return Response(sites_csv(incident_sites(incident_id)), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{incident_id}.csv"'})

    @app.get("/api/incidents/{incident_id}/report.html", response_class=HTMLResponse)
    async def report_html(incident_id: str) -> str:
        rep = storm_report.build_report(get_incident(incident_id), incident_sites(incident_id))
        rows = "".join(
            f"<tr><td>{html.escape(s.location.text or '')}</td><td>{s.kind}</td>"
            f"<td>{s.level or s.category or ''}</td><td>{len(s.hazards)}</td><td>{s.status}</td></tr>"
            for s in rep.sites
        )
        t = rep.threshold
        meter = (f"<p>Public damage ${t.public_damage_usd:,.2f} of the {html.escape(t.county)} County threshold "
                 f"${t.threshold_usd:,.2f} ({t.percent_of_threshold:g}%). {html.escape(t.source)}</p>"
                 if t else "<p>No county threshold: set the incident's county.</p>")
        return (f"<!doctype html><meta charset=utf-8><title>{html.escape(rep.incident.name)}</title>"
                f"<style>body{{font:16px system-ui;margin:24px}}td,th{{border:1px solid #999;padding:6px}}"
                f"table{{border-collapse:collapse}}</style><h1>{html.escape(rep.incident.name)}</h1>{meter}"
                f"<table><tr><th>Location</th><th>Kind</th><th>Level / category</th><th>Hazards</th>"
                f"<th>Status</th></tr>{rows}</table>")

    @app.post("/api/guide/ask", response_model=S.GuideAnswer)
    async def guide_ask(body: S.GuideQuestion) -> S.GuideAnswer:
        if mode == "stub":
            return stub_data.guide_answer(found="pizza" not in body.question.lower())
        try:
            return await guide_worker.ask(body.question)
        except httpx.HTTPError as exc:
            raise HTTPException(503, "The local model isn't responding. Try again in a moment.") from exc

    @app.post("/api/incidents/{incident_id}/analyze", response_model=S.AnalysisResult)
    async def analyze_incident(incident_id: str, body: S.AnalyzePrompt) -> S.AnalysisResult:
        inc = get_incident(incident_id)
        if mode == "stub":
            return stub_data.analysis(body.prompt)
        checked = gate.check_request(kind="code", prompt=body.prompt, text=None)
        if not checked.ok:
            raise HTTPException(400, checked.message)
        verdict = await safety.classify(checked.question, jobs._guard_url())
        if verdict.action != "allow":
            pol = load_policy()
            raise HTTPException(400, pol.messages.support if verdict.action == "support" else pol.messages.declined)
        report = storm_report.build_report(inc, incident_sites(incident_id))
        try:
            return await analysis_worker.run(checked.question, report,
                                             timeout_s=float(jobs._profile()["timeouts_s"].get("code", 60)))
        except httpx.HTTPError as exc:
            raise HTTPException(503, "The local model isn't responding. Try again in a moment.") from exc

    @app.get("/api/media/{incident_id}/{name}")
    async def media(incident_id: str, name: str) -> Response:
        if SAFE_NAME.fullmatch(incident_id) and SAFE_NAME.fullmatch(name):
            path = site_worker.MEDIA_DIR / incident_id / name
            if path.is_file():
                return Response(path.read_bytes(), media_type="image/jpeg")
        return Response(placeholder_png(f"stub media: {name}"), media_type="image/png")

    # ------------------------------------------------------------------ web app (mounted last)
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app
