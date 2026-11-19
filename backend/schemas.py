"""API data shapes: contract v1.

This file is the executable source of truth for contracts/schema.md. Change it only
when both Claude Code sessions agree (see CLAUDE.md), then regenerate the examples:
    uv run python -m scripts.export_examples
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "degraded", "failed"]
ArtifactKind = Literal["image", "audio", "document", "video", "code", "text"]


# --------------------------------------------------------------------------- general mode
class TranscriptSegment(BaseModel):
    t_start: float
    t_end: float
    text: str


class SoundEvent(BaseModel):
    t_start: float
    t_end: float
    label: str
    score: float = Field(ge=0, le=1)


class Frame(BaseModel):
    idx: int
    t: float
    caption: str | None = None
    thumb_b64: str | None = None  # small JPEG (~160 px), base64


class DocQA(BaseModel):
    found: bool
    answer: str | None = None
    quote: str | None = None  # verbatim text from the document, verified
    page: int | None = None
    match_score: float | None = None  # rapidfuzz partial ratio, 0-100
    retrieval_score: float | None = None


class CodeResult(BaseModel):
    source: str
    stdout: str = ""
    stderr: str = ""
    tests_passed: bool
    attempts: int = 1


class ArtifactResult(BaseModel):
    """The result for one uploaded file (or the typed text)."""

    artifact_id: str
    kind: ArtifactKind
    filename: str | None = None
    converted_from: str | None = None  # e.g. "heic", "mov"
    answer: str | None = None
    description: str | None = None
    extracted_text: str | None = None
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    sounds: list[SoundEvent] = Field(default_factory=list)
    frames: list[Frame] = Field(default_factory=list)
    doc_qa: DocQA | None = None
    code: CodeResult | None = None
    model: str | None = None
    latency_ms: int | None = None
    status: Status = "ok"
    error: str | None = None


class CaseFile(BaseModel):
    """Response of POST /api/analyze."""

    request_id: str
    mode: Literal["general"] = "general"
    status: Status = "ok"
    answer: str | None = None
    artifacts: list[ArtifactResult] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    degraded: list[str] = Field(default_factory=list)
    models: dict[str, str] = Field(default_factory=dict)


class ProgressEvent(BaseModel):
    """One server-sent event on GET /api/events/{request_id}."""

    type: Literal["progress", "delta", "done", "error"]
    stage: str | None = None
    pct: float | None = None
    message: str | None = None
    delta: str | None = None  # streamed answer text
    case_id: str | None = None  # set on "done"


# --------------------------------------------------------------------------- storm mode
DamageLevel = Literal["affected", "minor", "major", "destroyed", "needs_inspection"]
PACategory = Literal["A", "B", "C", "D", "E", "F", "G"]  # FEMA Public Assistance categories of work
SiteKind = Literal["home", "public"]
SiteStatus = Literal["draft", "needs_review", "approved"]
HazardType = Literal[
    "alarm_sounding",
    "downed_lines",
    "gas_smell",
    "fire",
    "trapped_person",
    "flooding",
    "road_impassable",
    "medical_need",
    "other",
]
EvidenceKind = Literal["photo", "voice", "video_frame", "video_audio", "document"]
LocationSource = Literal["photo_gps", "voice_note", "typed", "photo_text", "unknown"]


class Locator(BaseModel):
    t_start: float | None = None
    t_end: float | None = None
    frame_idx: int | None = None
    t: float | None = None
    page: int | None = None


class Evidence(BaseModel):
    id: str
    artifact_id: str
    kind: EvidenceKind
    quote: str | None = None
    locator: Locator | None = None
    verified: bool
    match_score: float | None = None
    media_url: str | None = None  # photo or frame thumbnail served by the API


class FieldValue(BaseModel):
    value: str | float | int | bool | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    needs_review: bool = False  # true when no verified evidence supports the value


class Location(BaseModel):
    text: str | None = None
    lat: float | None = None
    lon: float | None = None
    source: LocationSource = "unknown"


class Observation(BaseModel):
    name: str  # e.g. water_line, roof, structure, downed_lines
    value: str | float | bool | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class Hazard(BaseModel):
    type: HazardType
    message: str
    severity: Literal["life_safety", "warning"] = "life_safety"
    evidence_ids: list[str] = Field(default_factory=list)


class Site(BaseModel):
    id: str
    incident_id: str
    created_at: str
    location: Location = Field(default_factory=Location)
    kind: SiteKind = "home"
    level: DamageLevel | None = None  # homes: set by rules in domain/storm/levels.py
    level_reason: str | None = None  # which rule fired, citing the FEMA guide page
    category: PACategory | None = None  # public infrastructure
    observations: list[Observation] = Field(default_factory=list)
    hazards: list[Hazard] = Field(default_factory=list)
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    est_cost: float | None = None  # entered by a person, never estimated by a model
    status: SiteStatus = "draft"


class SitePatch(BaseModel):
    kind: SiteKind | None = None
    level: DamageLevel | None = None
    category: PACategory | None = None
    est_cost: float | None = None
    status: SiteStatus | None = None
    location_text: str | None = None
    fields: dict[str, str | float | int | bool | None] | None = None


class IncidentCreate(BaseModel):
    name: str
    town: str | None = None
    county: str | None = None
    started: str | None = None  # ISO date


class Incident(IncidentCreate):
    id: str
    created_at: str


class Threshold(BaseModel):
    county: str
    population: int
    per_capita_usd: float
    fiscal_year: str
    threshold_usd: float
    public_damage_usd: float
    percent_of_threshold: float
    source: str


class IncidentReport(BaseModel):
    incident: Incident
    sites: list[Site]
    totals_by_level: dict[str, int]
    totals_by_category_usd: dict[str, float]
    hazards_open: int
    threshold: Threshold | None = None


class GuideQuestion(BaseModel):
    question: str


class GuideAnswer(BaseModel):
    found: bool
    answer: str | None = None
    quote: str | None = None
    document: str | None = None
    page: int | None = None
    match_score: float | None = None


class AnalyzePrompt(BaseModel):
    prompt: str


class AnalysisResult(BaseModel):
    prompt: str
    code: CodeResult


# --------------------------------------------------------------------------- service
class Health(BaseModel):
    status: Literal["ok", "degraded", "stub"]
    mode: Literal["stub", "real"]
    profile: str | None = None
    models: dict[str, Literal["up", "down", "not_loaded"]] = Field(default_factory=dict)
    offline: bool = True


class Info(BaseModel):
    local_url: str
    lan_url: str
    qr_png_b64: str | None = None
