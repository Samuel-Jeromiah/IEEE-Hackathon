"""Example responses for stub mode (no models) and for contracts/examples/.

The storm examples use a fictional town. Anything that would come from FEMA or MEMA
documents is marked as a placeholder, so stub output can't be mistaken for real guidance.
"""
from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime

from backend import schemas as S

DEMO_INCIDENT_ID = "inc_demo"
PLACEHOLDER = "[stub placeholder: real text comes from the guide]"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- general mode
def casefile(kind: str, request_id: str = "req_example", not_found: bool = False) -> S.CaseFile:
    models = {"vlm": "stub", "asr": "stub", "sound": "stub", "coder": "stub"}
    if kind == "image":
        art = S.ArtifactResult(
            artifact_id="a1", kind="image", filename="beach.jpg",
            description="A golden retriever lying on wet sand at the edge of the water, with a red ball "
            "beside it. The sky is overcast and there are low waves behind the dog.",
            answer="The dog is a golden retriever, and the ball next to it is red.",
            extracted_text="", model="stub", latency_ms=12,
        )
    elif kind == "audio":
        art = S.ArtifactResult(
            artifact_id="a1", kind="audio", filename="voice-note.m4a", converted_from="m4a",
            transcript=[
                S.TranscriptSegment(t_start=0.0, t_end=4.1, text="Hi, it's Dana. The road by the old mill is flooded."),
                S.TranscriptSegment(t_start=4.1, t_end=7.8, text="I can hear a siren coming from the north side."),
            ],
            sounds=[
                S.SoundEvent(t_start=0.0, t_end=5.0, label="rain", score=0.71),
                S.SoundEvent(t_start=5.0, t_end=10.0, label="siren", score=0.64),
            ],
            answer="She says the road by the old mill is flooded (0:00-0:04). A siren is audible from 0:05.",
            model="stub", latency_ms=15,
        )
    elif kind == "document" and not_found:
        art = S.ArtifactResult(
            artifact_id="a1", kind="document", filename="lease.pdf",
            answer="I couldn't find that in the document.",
            doc_qa=S.DocQA(found=False, answer=None, quote=None, page=None, match_score=None, retrieval_score=2.1),
            model="stub", latency_ms=9,
        )
    elif kind == "document":
        art = S.ArtifactResult(
            artifact_id="a1", kind="document", filename="lease.pdf",
            answer="Rent is due on the first day of each month (page 2).",
            doc_qa=S.DocQA(
                found=True, answer="On the first day of each month.",
                quote="Rent is due on the first day of each month.", page=2,
                match_score=100.0, retrieval_score=11.4,
            ),
            model="stub", latency_ms=11,
        )
    elif kind == "video":
        art = S.ArtifactResult(
            artifact_id="a1", kind="video", filename="street.mov", converted_from="mov",
            description="Water covers a residential street. At 0:04 a pickup truck drives slowly through it; "
            "by 0:10 the water reaches the truck's wheel rims.",
            frames=[
                S.Frame(idx=0, t=0.0, caption="Flooded street, parked cars on the left."),
                S.Frame(idx=1, t=4.0, caption="A pickup truck enters the water."),
                S.Frame(idx=2, t=8.0, caption="The truck is halfway down the street."),
                S.Frame(idx=3, t=10.0, caption="Water up to the wheel rims."),
            ],
            transcript=[S.TranscriptSegment(t_start=1.2, t_end=3.0, text="Look how high it is.")],
            sounds=[S.SoundEvent(t_start=0.0, t_end=5.0, label="engine idling", score=0.58)],
            answer="Yes. A pickup truck drives through the flooded street starting at 0:04 (frame 2).",
            model="stub", latency_ms=20,
        )
    elif kind == "code":
        art = S.ArtifactResult(
            artifact_id="a1", kind="code",
            answer="The script totals the damage by category and compares it to the threshold. Tests passed.",
            code=S.CodeResult(
                source=(
                    "import pandas as pd\n\n"
                    "df = pd.read_csv('input.csv')\n"
                    "totals = df.groupby('category')['est_cost'].sum()\n"
                    "print(totals.to_string())\n\n"
                    "assert totals.sum() == df['est_cost'].sum()\n"
                    "assert (totals >= 0).all()\n"
                    "assert set(totals.index) <= set('ABCDEFG')\n"
                ),
                stdout="category\nA    12000.0\nC    48000.0\n",
                stderr="", tests_passed=True, attempts=1,
            ),
            model="stub", latency_ms=14,
        )
    else:  # plain text question
        art = S.ArtifactResult(artifact_id="a1", kind="text", answer="This is a stub answer.", model="stub")
    policy = S.PolicyNote()
    if kind == "document" and not_found:
        policy = S.PolicyNote(action="abstained", reason="not_in_document", message=art.answer)
    return S.CaseFile(request_id=request_id, policy=policy, answer=art.answer, artifacts=[art],
                      timings_ms={"total": art.latency_ms or 0}, models=models)


def casefile_declined(request_id: str = "req_example") -> S.CaseFile:
    """A harmful request stopped by the guardrails before any model ran."""
    from backend.guard.policy import load_policy

    msg = load_policy().messages.declined
    return S.CaseFile(request_id=request_id, answer=msg,
                      policy=S.PolicyNote(action="declined", reason="harmful_request", message=msg),
                      timings_ms={"total": 1})


# --------------------------------------------------------------------------- storm mode
def demo_incident() -> S.Incident:
    return S.Incident(id=DEMO_INCIDENT_ID, name="November windstorm (demo)", town="Pine Harbor (fictional)",
                      county="Knox", started="2026-11-17", created_at="2026-11-18T14:00:00+00:00")


def site_flooded_home(incident_id: str = DEMO_INCIDENT_ID, site_id: str = "site_1") -> S.Site:
    return S.Site(
        id=site_id, incident_id=incident_id, created_at="2026-11-18T14:05:00+00:00",
        location=S.Location(text="14 Water Street", source="voice_note"),
        kind="home", level="major",
        level_reason="Stub: water in first-floor living space. Real rule text comes from domain/storm/levels.py.",
        observations=[
            S.Observation(name="water_line", value="first_floor_living", evidence_ids=["e1", "e2"]),
            S.Observation(name="roof", value="none", evidence_ids=["e1"]),
            S.Observation(name="structure", value="minor", evidence_ids=["e1"]),
        ],
        fields={
            "location": S.FieldValue(value="14 Water Street", evidence_ids=["e2"]),
            "damage": S.FieldValue(value="Flooding in the living room; water above the outlets.",
                                   evidence_ids=["e1", "e2"]),
            "access": S.FieldValue(value=None, needs_review=True),
        },
        evidence=[
            S.Evidence(id="e1", artifact_id="a_photo_1", kind="photo", verified=True,
                       media_url=f"/api/media/{incident_id}/site_1_photo.jpg"),
            S.Evidence(id="e2", artifact_id="a_voice_1", kind="voice",
                       quote="the water came up past the outlets in the living room",
                       locator=S.Locator(t_start=4.2, t_end=8.9), verified=True, match_score=97.0),
        ],
        status="needs_review",
    )


def site_basement_alarm(incident_id: str = DEMO_INCIDENT_ID, site_id: str = "site_2") -> S.Site:
    return S.Site(
        id=site_id, incident_id=incident_id, created_at="2026-11-18T14:20:00+00:00",
        location=S.Location(text="7 Ledge Road", source="typed"),
        kind="home", level="needs_inspection",
        level_reason="Basement water depth can't be seen in the video, so an inspector must check.",
        observations=[S.Observation(name="water_line", value="basement", evidence_ids=["e4"])],
        hazards=[
            S.Hazard(type="alarm_sounding", severity="life_safety", evidence_ids=["e3"],
                     message="An alarm is sounding in this video at 0:07. Check whether anyone is inside. "
                             "If a CO or smoke alarm may be going off, get everyone out and call 911."),
        ],
        fields={"damage": S.FieldValue(value="Standing water in the basement.", evidence_ids=["e4"])},
        evidence=[
            S.Evidence(id="e3", artifact_id="a_video_2", kind="video_audio",
                       quote="alarm beeping (three-beep pattern)", locator=S.Locator(t_start=7.0, t_end=9.5),
                       verified=True, match_score=None),
            S.Evidence(id="e4", artifact_id="a_video_2", kind="video_frame",
                       locator=S.Locator(frame_idx=3, t=6.0), verified=True,
                       media_url=f"/api/media/{incident_id}/site_2_frame_3.jpg"),
        ],
        status="draft",
    )


def site_culvert(incident_id: str = DEMO_INCIDENT_ID, site_id: str = "site_3") -> S.Site:
    return S.Site(
        id=site_id, incident_id=incident_id, created_at="2026-11-18T14:40:00+00:00",
        location=S.Location(text="Mill Road culvert", source="voice_note"),
        kind="public", category="C",
        observations=[S.Observation(name="washout", value=True, evidence_ids=["e5", "e6"]),
                      S.Observation(name="road_passable", value=False, evidence_ids=["e6"])],
        hazards=[S.Hazard(type="road_impassable", severity="warning", evidence_ids=["e6"],
                          message="Road reported closed at the Mill Road culvert.")],
        fields={
            "location": S.FieldValue(value="Mill Road culvert", evidence_ids=["e6"]),
            "damage": S.FieldValue(value="Culvert washed out; road closed.", evidence_ids=["e5", "e6"]),
        },
        evidence=[
            S.Evidence(id="e5", artifact_id="a_photo_3", kind="photo", verified=True,
                       media_url=f"/api/media/{incident_id}/site_3_photo.jpg"),
            S.Evidence(id="e6", artifact_id="a_voice_3", kind="voice",
                       quote="the culvert on Mill Road is washed out, road's closed",
                       locator=S.Locator(t_start=0.8, t_end=3.9), verified=True, match_score=100.0),
        ],
        est_cost=48000.0, status="approved",
    )


def demo_sites(incident_id: str = DEMO_INCIDENT_ID) -> list[S.Site]:
    return [site_flooded_home(incident_id), site_basement_alarm(incident_id), site_culvert(incident_id)]


def report(incident: S.Incident, sites: list[S.Site]) -> S.IncidentReport:
    by_level: dict[str, int] = {}
    by_cat: dict[str, float] = {}
    for s in sites:
        if s.kind == "home" and s.level:
            by_level[s.level] = by_level.get(s.level, 0) + 1
        if s.kind == "public" and s.category:
            by_cat[s.category] = by_cat.get(s.category, 0.0) + (s.est_cost or 0.0)
    public = sum(by_cat.values())
    population, per_capita = 40607, 5.03  # stub figures; real ones live in domain/storm/thresholds.yaml
    threshold_usd = round(population * per_capita, 2)
    return S.IncidentReport(
        incident=incident, sites=sites, totals_by_level=by_level, totals_by_category_usd=by_cat,
        hazards_open=sum(1 for s in sites for h in s.hazards if s.status != "approved"),
        threshold=S.Threshold(
            county=incident.county or "Knox", population=population, per_capita_usd=per_capita,
            fiscal_year="FY2027", threshold_usd=threshold_usd, public_damage_usd=public,
            percent_of_threshold=round(100 * public / threshold_usd, 1),
            source="Stub figures. Real values: domain/storm/thresholds.yaml (verify on fema.gov).",
        ),
    )


def guide_answer(found: bool) -> S.GuideAnswer:
    if not found:
        return S.GuideAnswer(found=False, answer="That isn't covered in the guides I have.")
    return S.GuideAnswer(found=True, answer=f"Stub answer. {PLACEHOLDER}", quote=PLACEHOLDER,
                         document="fema_pda_guide_2025-07.pdf", page=1, match_score=100.0)


def analysis(prompt: str) -> S.AnalysisResult:
    return S.AnalysisResult(prompt=prompt, code=casefile("code").artifacts[0].code)


class StubStore:
    """In-memory incidents and sites for stub mode, preloaded with the demo incident."""

    def __init__(self) -> None:
        inc = demo_incident()
        self.incidents: dict[str, S.Incident] = {inc.id: inc}
        self.sites: dict[str, S.Site] = {s.id: s for s in demo_sites(inc.id)}

    def add_site(self, incident_id: str, location_text: str | None) -> S.Site:
        site = copy.deepcopy(site_flooded_home(incident_id, new_id("site")))
        site.created_at, site.status = now(), "draft"
        if location_text:
            site.location = S.Location(text=location_text, source="typed")
        self.sites[site.id] = site
        return site


def examples() -> dict[str, object]:
    """Everything written to contracts/examples/ by scripts/export_examples.py."""
    inc = demo_incident()
    return {
        "casefile_image": casefile("image"),
        "casefile_audio": casefile("audio"),
        "casefile_document_found": casefile("document"),
        "casefile_document_not_found": casefile("document", not_found=True),        "casefile_video": casefile("video"),
        "casefile_code": casefile("code"),
        "casefile_declined": casefile_declined(),
        "incident": inc,
        "site_flooded_home": site_flooded_home(),
        "site_basement_alarm": site_basement_alarm(),
        "site_culvert": site_culvert(),
        "incident_report": report(inc, demo_sites()),
        "guide_answer_found": guide_answer(True),
        "guide_answer_not_found": guide_answer(False),
        "analysis_result": analysis("Total the damage by category and compare it to the county threshold."),
        "health_stub": S.Health(status="stub", mode="stub", profile=None,
                                models={"vlm": "not_loaded", "coder": "not_loaded",
                                        "asr": "not_loaded", "sound": "not_loaded"}),
    }
