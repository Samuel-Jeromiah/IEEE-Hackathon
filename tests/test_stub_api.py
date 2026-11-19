"""Every endpoint in stub mode, through FastAPI's test client (no models, no network)."""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("STORMLOG_MODE", "stub")
    from backend.main import create_app

    return TestClient(create_app())


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "stub" and body["mode"] == "stub"


@pytest.mark.parametrize(
    "filename,kind",
    [("dog.jpg", "image"), ("IMG_0001.HEIC", "image"), ("note.m4a", "audio"),
     ("clip.mov", "video"), ("lease.pdf", "document")],
)
def test_analyze_picks_example_by_file_type(client, filename, kind):
    r = client.post("/api/analyze", files={"files": (filename, b"x", "application/octet-stream")},
                    data={"prompt": "What is this?", "request_id": "r1"})
    assert r.status_code == 200
    body = r.json()
    assert body["request_id"] == "r1"
    assert body["artifacts"][0]["kind"] == kind
    assert body["artifacts"][0]["filename"] == filename


def test_analyze_code_and_document_not_found(client):
    code = client.post("/api/analyze", data={"prompt": "Write a function", "task_hint": "code"}).json()
    assert code["artifacts"][0]["code"]["tests_passed"] is True
    doc = client.post("/api/analyze", data={"text": "Rent is due monthly.", "prompt": "Is pizza allowed?"}).json()
    assert doc["artifacts"][0]["doc_qa"]["found"] is False


def test_events_stream_ends_with_done(client):
    with client.stream("GET", "/api/events/r1") as r:
        body = "".join(r.iter_text())
    assert '"type":"progress"' in body and '"type":"delta"' in body and '"type":"done"' in body


def test_incident_flow(client):
    assert client.get("/api/incidents").json()[0]["id"] == "inc_demo"
    inc = client.post("/api/incidents", json={"name": "Test storm", "county": "Knox"}).json()
    site = client.post(f"/api/incidents/{inc['id']}/sites",
                       files={"photo": ("p.jpg", b"x", "image/jpeg")}, data={"location_text": "1 Main St"}).json()
    assert site["location"] == {"text": "1 Main St", "lat": None, "lon": None, "source": "typed"}
    patched = client.patch(f"/api/sites/{site['id']}", json={"status": "approved", "est_cost": 1200}).json()
    assert patched["status"] == "approved" and patched["est_cost"] == 1200
    assert len(client.get(f"/api/incidents/{inc['id']}").json()["sites"]) == 1
    csv_resp = client.get(f"/api/incidents/{inc['id']}/export.csv")
    assert csv_resp.headers["content-type"].startswith("text/csv") and "1 Main St" in csv_resp.text
    assert "Test storm" in client.get(f"/api/incidents/{inc['id']}/report.html").text


def test_demo_report_totals_and_threshold(client):
    rep = client.get("/api/incidents/inc_demo").json()
    assert rep["totals_by_category_usd"] == {"C": 48000.0}
    assert rep["totals_by_level"] == {"major": 1, "needs_inspection": 1}
    assert rep["threshold"]["threshold_usd"] > rep["threshold"]["public_damage_usd"] > 0


def test_guide_found_and_not_found(client):
    assert client.post("/api/guide/ask", json={"question": "What is major damage?"}).json()["found"] is True
    assert client.post("/api/guide/ask", json={"question": "Does FEMA pay for pizza?"}).json()["found"] is False


def test_analysis_and_media_and_info(client):
    res = client.post("/api/incidents/inc_demo/analyze", json={"prompt": "Total by category"}).json()
    assert res["code"]["tests_passed"] is True
    img = client.get("/api/media/inc_demo/site_1_photo.jpg")
    assert img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
    assert client.get("/api/info").json()["lan_url"].startswith("http://")


def test_unknown_ids_are_404(client):
    assert client.get("/api/incidents/nope").status_code == 404
    assert client.patch("/api/sites/nope", json={"status": "approved"}).status_code == 404


def test_launcher_stub_mode_serves_api_and_web_app():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "serving.launch", "--stub", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 40
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
                    assert b'"stub"' in r.read()
                break
            except OSError:
                if time.time() > deadline or proc.poll() is not None:
                    raise AssertionError("launcher did not come up in stub mode") from None
                time.sleep(0.3)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
            assert b"StormLog" in r.read()
    finally:
        proc.terminate()
        proc.wait(timeout=15)
