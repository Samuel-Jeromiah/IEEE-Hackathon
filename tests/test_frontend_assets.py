"""The web app works offline: every referenced asset is served, and nothing points off the laptop."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
# SVG namespace URIs are identifiers, never fetched.
ALLOWED_URL_PREFIXES = ("http://www.w3.org/",)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("STORMLOG_MODE", "stub")
    from backend.main import create_app

    return TestClient(create_app())


def code_files():
    return [p for p in FRONTEND.rglob("*") if p.suffix in {".html", ".css", ".js"}]


def rel(path: Path) -> str:
    return path.resolve().relative_to(FRONTEND.resolve()).as_posix()


def referenced_assets() -> set[str]:
    refs: set[str] = set()
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    refs |= set(re.findall(r'(?:src|href)="([^"#:]+)"', html))
    for js in FRONTEND.rglob("*.js"):
        for spec in re.findall(r'from\s+"(\.{1,2}/[^"]+)"', js.read_text(encoding="utf-8")):
            refs.add(rel(js.parent / spec))
    for css in FRONTEND.rglob("*.css"):
        for spec in re.findall(r'url\("(\.\./[^"]+|[\w./-]+\.(?:woff2|svg|png))"\)', css.read_text(encoding="utf-8")):
            refs.add(rel(css.parent / spec))
    return refs


def test_no_external_urls_in_frontend_code():
    offenders = []
    for path in code_files():
        for url in re.findall(r"https?://[^\s\"'<>)]+", path.read_text(encoding="utf-8")):
            if not url.startswith(ALLOWED_URL_PREFIXES):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {url}")
    assert not offenders, "frontend must work offline; remove external URLs:\n" + "\n".join(offenders)


def test_every_referenced_asset_is_served(client):
    assert client.get("/").status_code == 200
    refs = referenced_assets()
    assert {"css/app.css", "js/app.js", "js/views/town.js", "fonts/atkinson-hyperlegible-latin-400-normal.woff2"} <= refs
    for ref in sorted(refs):
        assert (FRONTEND / ref).is_file(), f"missing: {ref}"
        resp = client.get(f"/{ref}")
        assert resp.status_code == 200, ref
        if ref.endswith(".js"):
            assert "javascript" in resp.headers["content-type"], f"{ref} served as {resp.headers['content-type']}"


def test_bundled_fonts_are_licensed():
    fonts = sorted(p.name for p in (FRONTEND / "fonts").glob("*.woff2"))
    assert fonts, "no bundled fonts"
    notes = (FRONTEND / "fonts" / "LICENSES.md").read_text(encoding="utf-8")
    for family in ("atkinson-hyperlegible", "barlow-condensed", "jetbrains-mono"):
        assert any(f.startswith(family) for f in fonts), family
        assert (FRONTEND / "fonts" / f"LICENSE-{family}.txt").is_file(), family
    assert "SIL Open Font License" in notes
