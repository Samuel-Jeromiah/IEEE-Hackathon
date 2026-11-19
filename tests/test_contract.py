"""The contract: stub examples validate, example files are current, and config is consistent."""
import json
from pathlib import Path

from backend import schemas as S
from backend import stub_data
from backend.config import load_models_config

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "contracts" / "examples"

# Order matters: "incident_report" must match before "incident".
SCHEMA_FOR_PREFIX = [
    ("casefile_", S.CaseFile),
    ("incident_report", S.IncidentReport),
    ("incident", S.Incident),
    ("site_", S.Site),
    ("guide_answer_", S.GuideAnswer),
    ("analysis_result", S.AnalysisResult),
    ("health_", S.Health),
]


def schema_for(name: str):
    for prefix, model in SCHEMA_FOR_PREFIX:
        if name.startswith(prefix):
            return model
    raise KeyError(name)


def test_stub_examples_round_trip():
    for name, obj in stub_data.examples().items():
        model = schema_for(name)
        assert isinstance(obj, model), name
        assert model.model_validate_json(obj.model_dump_json()) == obj


def test_example_files_are_current():
    examples = stub_data.examples()
    files = sorted(EXAMPLES_DIR.glob("*.json"))
    assert {f.stem for f in files} == set(examples), "run: uv run python -m scripts.export_examples"
    for f in files:
        on_disk = json.loads(f.read_text(encoding="utf-8"))
        schema_for(f.stem).model_validate(on_disk)
        assert on_disk == json.loads(examples[f.stem].model_dump_json()), (
            f"{f.name} is stale; run: uv run python -m scripts.export_examples"
        )


def test_profiles_reference_defined_models():
    cfg = load_models_config()
    for name, profile in cfg["profiles"].items():
        for role in ("vlm", "coder", "asr", "sound"):
            assert profile[role] in cfg["models"], f"{name}.{role}"
        for key in profile.get("optional", []):
            assert key in cfg["models"], f"{name}.optional: {key}"
        assert {"ctx", "image_max_px", "video_max_frames", "frame_px"} <= set(profile["limits"])
        assert set(profile["timeouts_s"]) == {"image", "document", "audio", "video", "code"}


def test_site_evidence_ids_resolve():
    for site in stub_data.demo_sites():
        ids = {e.id for e in site.evidence}
        refs = [i for f in site.fields.values() for i in f.evidence_ids]
        refs += [i for o in site.observations for i in o.evidence_ids]
        refs += [i for h in site.hazards for i in h.evidence_ids]
        assert set(refs) <= ids, site.id


def test_fields_without_evidence_need_review():
    for site in stub_data.demo_sites():
        for name, field in site.fields.items():
            if not field.evidence_ids:
                assert field.needs_review, f"{site.id}.{name} has no evidence but isn't marked needs_review"
