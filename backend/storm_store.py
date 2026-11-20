"""Incidents and sites for real mode, saved to data/storm/store.json after every change."""
from __future__ import annotations

import json
from pathlib import Path

from backend import schemas as S
from backend import stub_data

ROOT = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT / "data" / "storm" / "store.json"


class FileStore:
    """Same shape as stub_data.StubStore, but starts empty (plus the demo incident) and persists."""

    def __init__(self, path: Path = STORE_PATH) -> None:
        self.path = path
        self.incidents: dict[str, S.Incident] = {}
        self.sites: dict[str, S.Site] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.incidents = {i["id"]: S.Incident(**i) for i in data.get("incidents", [])}
            self.sites = {s["id"]: S.Site(**s) for s in data.get("sites", [])}
        if not self.incidents:
            inc = stub_data.demo_incident()
            self.incidents[inc.id] = inc
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "incidents": [i.model_dump() for i in self.incidents.values()],
            "sites": [s.model_dump() for s in self.sites.values()],
        }, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def put_site(self, site: S.Site) -> S.Site:
        self.sites[site.id] = site
        self.save()
        return site
