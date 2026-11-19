"""StormLog API (FastAPI).

Start it through the launcher:
    uv run python -m serving.launch --stub              # example data, no models
    uv run python -m serving.launch --profile mac16     # model servers + API
or directly:
    STORMLOG_MODE=stub uv run uvicorn backend.main:create_app --factory --port 8000

Stub mode serves the examples in backend/stub_data.py for every endpoint, so the
frontend can be built without models. Real mode reports real model health; the other
endpoints still return stub data until the workers replace them (docs/PLAN.md, M1-M3).
Stub hook: a document question containing "pizza" returns the not-found example.
"""
from __future__ import annotations

import asyncio
import base64
import csv
import html
import io
import os
import socket
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import schemas as S
from backend import stub_data
from backend.config import load_models_config

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
DOC_EXT = {".pdf", ".docx", ".txt", ".md"}


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


def guess_kind(filename: str | None, task_hint: str | None, has_text: bool) -> str:
    if task_hint == "code":
        return "code"
    ext = Path(filename or "").suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in DOC_EXT or has_text:
        return "document"
    return "text"


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
    store = stub_data.StubStore()

    # ------------------------------------------------------------------ service
    @app.get("/api/health", response_model=S.Health)
    async def health() -> S.Health:
        if mode == "stub":
            return stub_data.examples()["health_stub"]
        servers = load_models_config()["servers"]
        models: dict[str, str] = {"asr": "not_loaded", "sound": "not_loaded"}
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
        first = files[0].filename if files else None
        kind = guess_kind(first, task_hint, bool(text))
        not_found = kind == "document" and "pizza" in (prompt or "").lower()
        result = stub_data.casefile(kind, request_id or stub_data.new_id("req"), not_found=not_found)
        if first:
            result.artifacts[0].filename = first
        return result

    @app.get("/api/events/{request_id}")
    async def events(request_id: str) -> StreamingResponse:
        steps = [
            S.ProgressEvent(type="progress", stage="normalize", pct=10, message="Reading your file"),
            S.ProgressEvent(type="progress", stage="extract", pct=45, message="Looking and listening"),
            S.ProgressEvent(type="progress", stage="answer", pct=75, message="Writing the answer"),
            *[S.ProgressEvent(type="delta", delta=w) for w in "This is a streamed stub answer.".split(" ")],
            S.ProgressEvent(type="done", pct=100, case_id=request_id),
        ]

        async def gen():
            for ev in steps:
                yield f"data: {ev.model_dump_json(exclude_none=True)}\n\n"
                await asyncio.sleep(0.05)

        return StreamingResponse(gen(), media_type="text/event-stream",
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
        return inc

    @app.get("/api/incidents/{incident_id}", response_model=S.IncidentReport)
    async def incident_report(incident_id: str) -> S.IncidentReport:
        return stub_data.report(get_incident(incident_id), incident_sites(incident_id))

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
        return store.add_site(incident_id, location_text)

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
        return site

    @app.get("/api/incidents/{incident_id}/export.csv")
    async def export_csv(incident_id: str) -> Response:
        get_incident(incident_id)
        return Response(sites_csv(incident_sites(incident_id)), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{incident_id}.csv"'})

    @app.get("/api/incidents/{incident_id}/report.html", response_class=HTMLResponse)
    async def report_html(incident_id: str) -> str:
        rep = stub_data.report(get_incident(incident_id), incident_sites(incident_id))
        rows = "".join(
            f"<tr><td>{html.escape(s.location.text or '')}</td><td>{s.kind}</td>"
            f"<td>{s.level or s.category or ''}</td><td>{len(s.hazards)}</td><td>{s.status}</td></tr>"
            for s in rep.sites
        )
        return (f"<!doctype html><meta charset=utf-8><title>{html.escape(rep.incident.name)}</title>"
                f"<style>body{{font:16px system-ui;margin:24px}}td,th{{border:1px solid #999;padding:6px}}"
                f"table{{border-collapse:collapse}}</style><h1>{html.escape(rep.incident.name)}</h1>"
                f"<table><tr><th>Location</th><th>Kind</th><th>Level / category</th><th>Hazards</th>"
                f"<th>Status</th></tr>{rows}</table><p>Stub report.</p>")

    @app.post("/api/guide/ask", response_model=S.GuideAnswer)
    async def guide_ask(body: S.GuideQuestion) -> S.GuideAnswer:
        return stub_data.guide_answer(found="pizza" not in body.question.lower())

    @app.post("/api/incidents/{incident_id}/analyze", response_model=S.AnalysisResult)
    async def analyze_incident(incident_id: str, body: S.AnalyzePrompt) -> S.AnalysisResult:
        get_incident(incident_id)
        return stub_data.analysis(body.prompt)

    @app.get("/api/media/{incident_id}/{name}")
    async def media(incident_id: str, name: str) -> Response:
        return Response(placeholder_png(f"stub media: {name}"), media_type="image/png")

    # ------------------------------------------------------------------ web app (mounted last)
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app
