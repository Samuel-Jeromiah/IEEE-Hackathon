"""Sanity: chat view ships offline and task_hint helpers stay reachable via the bundle."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("STORMLOG_MODE", "stub")
    from backend.main import create_app

    return TestClient(create_app())


def test_chat_assets_are_served(client):
    assert client.get("/").status_code == 200
    assert b'data-nav="/chat"' in client.get("/").content
    for path in ("js/views/chat.js", "js/app.js", "css/app.css"):
        r = client.get(f"/{path}")
        assert r.status_code == 200, path
    chat = client.get("/js/views/chat.js").text
    assert "inferTaskHint" in chat
    assert "export function chatView" in chat
    app_js = client.get("/js/app.js").text
    assert 'route("/chat"' in app_js
    assert "toolsRedirectView" in app_js


def test_chat_js_infer_logic_documented():
    """Keep the client-side routing rules discoverable (mirrored in chat.js)."""
    src = (ROOT / "frontend/js/views/chat.js").read_text(encoding="utf-8")
    assert "fileKind" in src and "inferTaskHint" in src
    assert "image/*" in src and "video/*" in src
