"""Read serving/models.yaml and the record of downloaded models (models/resolved.json)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "serving" / "models.yaml"
MODELS_DIR = ROOT / "models"


def load_models_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def selected_profile_name(explicit: str | None = None) -> str | None:
    """The profile given on the command line, else the one setup recorded in models/profile.txt."""
    if explicit:
        return explicit
    recorded = MODELS_DIR / "profile.txt"
    return recorded.read_text(encoding="utf-8").strip() if recorded.exists() else None


def resolved_models() -> dict:
    path = MODELS_DIR / "resolved.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def repo_path(rel_path: str) -> Path:
    """Turn a repo-relative path from resolved.json into an absolute path."""
    return ROOT / rel_path
