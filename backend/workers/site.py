"""StormLog site builder: volunteer's photo + voice note + video → one evidence-linked site.

Models only observe (what's in the photo, what was said). Fixed rules in domain/storm/
set the FEMA level, PA category and hazards. Every field points at its evidence, or is
marked "needs review".
"""
from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend import manager, normalize
from backend import schemas as S
from backend.clients import llm
from backend.guard.prompts import with_rule, wrap_untrusted
from backend.workers import video as video_worker
from domain.storm import hazards as hz
from domain.storm import levels as lv
from domain.verify import QUOTE_THRESHOLD, locate_quote

ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT / "data" / "media"

PHOTO_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["home", "public", "other"]},
        "home_type": {"type": "string", "enum": list(lv.HOME_TYPE)},
        "water_line": {"type": "string", "enum": list(lv.WATER_LINE)},
        "roof": {"type": "string", "enum": list(lv.ROOF)},
        "structure": {"type": "string", "enum": list(lv.STRUCTURE)},
        "public_element": {"type": "string", "enum": list(lv.PUBLIC_ELEMENT)},
        "downed_lines": {"type": "boolean"},
        "road_passable": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "visible_text": {"type": "string"},
        "description": {"type": "string"},
        "best_frame": {"type": "integer"},
    },
    "required": ["kind", "home_type", "water_line", "roof", "structure", "public_element",
                 "downed_lines", "road_passable", "visible_text", "description"],
}

PHOTO_SYSTEM = (
    "You help storm-damage volunteers. Report only what is visible; use \"unknown\" when you can't see it. "
    "kind: home for a house or apartment, public for roads, bridges, culverts, public buildings, utilities "
    "or parks, other otherwise. home_type: manufactured for mobile or manufactured homes. "
    "water_line: none if no flooding; crawlspace_or_basement if water is only under the home, in a basement "
    "or around it; below_outlets if water is inside living space but lower than wall outlets (about 30 cm); "
    "at_or_above_outlets if it reaches outlets or higher; at_or_above_ceiling if it reaches the ceiling; "
    "unknown if you can't see the inside water level. roof: none, cosmetic (shingles, gutters), structural "
    "(holes, broken rafters, tree through it) or collapsed. structure: intact, cosmetic (siding, paint), "
    "structural (walls or foundation damaged), collapsed, or only_foundation. public_element: what public "
    "thing is damaged, or none. visible_text: house numbers, street signs or other readable text. "
    "description: one or two plain sentences. Return JSON."
)

_FIELD = {"type": "object", "properties": {"value": {"type": "string"}, "quote": {"type": "string"}},
          "required": ["value", "quote"]}
VOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "location": _FIELD, "damage": _FIELD, "people": _FIELD, "access": _FIELD,
        "water_line": {"type": "object", "properties": {
            "value": {"type": "string", "enum": list(lv.WATER_LINE)}, "quote": {"type": "string"}},
            "required": ["value", "quote"]},
    },
    "required": ["location", "damage", "people", "access", "water_line"],
}
VOICE_SYSTEM = (
    "A volunteer recorded a voice note about storm damage. From the transcript, fill each field with a "
    "short plain phrase (not just yes or no) and the exact words from the transcript that support it "
    "(quote), copied word for word. location: the address or landmark. damage: what is damaged. people: "
    "who is affected or displaced. access: whether the road or house can be reached, e.g. \"road washed "
    "out\". water_line: how high the water got inside: crawlspace_or_basement, below_outlets, "
    "at_or_above_outlets (water reached, passed or covered the wall outlets), at_or_above_ceiling, none, "
    "or unknown. If something isn't mentioned, use an empty value and quote (unknown for water_line). "
    "Return JSON."
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

_SEVERITY = {
    "water_line": list(lv.WATER_LINE[:-1]),
    "roof": list(lv.ROOF[:-1]),
    "structure": list(lv.STRUCTURE[:-1]),
}


@dataclass
class Heard:
    """A transcript (voice note or video audio) plus what the model read out of it."""
    kind: str  # voice | video_audio
    artifact_id: str
    segments: list[dict]
    sounds: list[dict]
    fields: dict = field(default_factory=dict)


@dataclass
class Seen:
    """Observations from the photo or video frames."""
    kind: str  # photo | video_frame
    artifact_id: str
    obs: dict
    media_url: str | None = None
    frame_idx: int | None = None
    t: float | None = None
    lat: float | None = None
    lon: float | None = None


# --------------------------------------------------------------------------- model calls
async def observe_images(paths: list[Path], timeout_s: float) -> dict:
    content: list[dict] = [{"type": "image_url", "image_url": {"url": llm.image_data_url(p)}} for p in paths]
    note = (f"These are {len(paths)} frames from one video, in order (0 to {len(paths) - 1}). "
            "Set best_frame to the frame that shows the damage best." if len(paths) > 1
            else "Describe the damage in this photo.")
    content.append({"type": "text", "text": note})
    messages = [{"role": "system", "content": PHOTO_SYSTEM}, {"role": "user", "content": content}]
    return await llm.chat_json("vlm", messages, PHOTO_SCHEMA, temperature=0.0, max_tokens=500,
                               timeout_s=timeout_s)


async def read_transcript(segments: list[dict], timeout_s: float) -> dict:
    text = "\n".join(s["text"] for s in segments if s.get("text"))
    if not text.strip():
        return {}
    wrapped, rule = wrap_untrusted(text, "transcript")
    messages = [{"role": "system", "content": with_rule(VOICE_SYSTEM, rule)},
                {"role": "user", "content": f"Transcript:\n{wrapped}"}]
    return await llm.chat_json("vlm", messages, VOICE_SCHEMA, temperature=0.0, max_tokens=500,
                               timeout_s=timeout_s)


async def listen(path: Path) -> tuple[list[dict], list[dict]]:
    return await asyncio.gather(asyncio.to_thread(manager.transcribe, path),
                                asyncio.to_thread(manager.classify_sounds, path))


# --------------------------------------------------------------------------- assembly (no models)
class _Evidence:
    def __init__(self) -> None:
        self.items: list[S.Evidence] = []

    def add(self, **kw) -> str:
        item = S.Evidence(id=f"e{len(self.items) + 1}", **kw)
        for old in self.items:
            if old.model_dump(exclude={"id"}) == item.model_dump(exclude={"id"}):
                return old.id
        self.items.append(item)
        return item.id


def _verify(quote: str, segments: list[dict]) -> list[tuple[str, float | None, float | None, float]]:
    """Each sentence of the quote with where it was said, or [] if any sentence wasn't said."""
    found = []
    for part in (p.strip() for p in _SENTENCE.split(quote)):
        if not part:
            continue
        t0, t1, score = locate_quote(part, segments)
        if score < QUOTE_THRESHOLD:
            return []
        found.append((part, t0, t1, score))
    return found


def _said(text: str | None) -> str:
    """The model's text, or "" when it only says that nothing is there."""
    text = (text or "").strip()
    return "" if text.lower().strip(".") in {"", "unknown", "none", "n/a", "no text", "not visible"} else text


def _worst(field_name: str, values: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Most severe known value across sources, with the evidence ids that support it."""
    order = _SEVERITY[field_name]
    known = [(v, eid) for v, eid in values if v in order]
    if not known:
        return "unknown", []
    top = max(known, key=lambda x: order.index(x[0]))[0]
    return top, list(dict.fromkeys(eid for v, eid in known if v == top))


def assemble(*, site_id: str, incident_id: str, created_at: str, typed_location: str | None,
             seen: list[Seen], heard: list[Heard]) -> S.Site:
    ev = _Evidence()
    seen_ids: list[tuple[Seen, str]] = []
    for s in seen:
        locator = S.Locator(frame_idx=s.frame_idx, t=s.t) if s.kind == "video_frame" else None
        seen_ids.append((s, ev.add(artifact_id=s.artifact_id, kind=s.kind, verified=True,
                                   media_url=s.media_url, locator=locator)))

    # Voice/video fields: keep a quote only if it really is in the transcript.
    quoted: dict[str, list[tuple[str, str]]] = {}
    unverified: dict[str, str] = {}
    for h in heard:
        for name, item in (h.fields or {}).items():
            value, quote = str(item.get("value") or "").strip(), str(item.get("quote") or "").strip()
            if name == "water_line" and quote:
                value = lv.water_line_from_text(quote) or value
            if not value or value == "unknown":
                continue
            parts = _verify(quote, h.segments) if quote else []
            if not parts:
                unverified.setdefault(name, value)
                continue
            for part, t0, t1, score in parts:
                eid = ev.add(artifact_id=h.artifact_id, kind=h.kind, quote=part, verified=True,
                             locator=S.Locator(t_start=t0, t_end=t1), match_score=round(score, 1))
                quoted.setdefault(name, []).append((value, eid))
        # The water line also comes straight from what was said, in case the model missed it.
        cited = {(e.artifact_id, e.locator.t_start) for e in ev.items if e.locator
                 for _, eid in quoted.get("water_line", []) if eid == e.id}
        for seg in h.segments:
            value = lv.water_line_from_text(seg.get("text", ""), quote=False)
            if value and (h.artifact_id, seg.get("t_start")) not in cited:
                eid = ev.add(artifact_id=h.artifact_id, kind=h.kind, quote=seg["text"].strip(), verified=True,
                             locator=S.Locator(t_start=seg.get("t_start"), t_end=seg.get("t_end")),
                             match_score=100.0)
                quoted.setdefault("water_line", []).append((value, eid))

    # Observations, fused across photo, frames and what was said.
    obs_values: dict[str, list[tuple[str, str]]] = {k: [] for k in _SEVERITY}
    for s, eid in seen_ids:
        for k in _SEVERITY:
            obs_values[k].append((s.obs.get(k, "unknown"), eid))
    obs_values["water_line"] += quoted.get("water_line", [])
    fused = {k: _worst(k, v) for k, v in obs_values.items()}
    home_type = next((s.obs.get("home_type") for s, _ in seen_ids
                      if s.obs.get("home_type") not in (None, "unknown")), "unknown")
    kind_votes = [s.obs.get("kind") for s, _ in seen_ids]
    site_kind = "public" if "public" in kind_votes and "home" not in kind_votes else "home"

    # Public sites only list damage; "roof: none" says nothing about a culvert.
    skip = {"unknown", "none", "intact"} if site_kind == "public" else {"unknown"}
    observations = [S.Observation(name=k, value=v, evidence_ids=ids) for k, (v, ids) in fused.items()
                    if v not in skip]
    if home_type != "unknown" and site_kind == "home":
        observations.append(S.Observation(name="home_type", value=home_type,
                                          evidence_ids=[e for s, e in seen_ids if s.obs.get("home_type") == home_type]))
    for s, eid in seen_ids:
        if s.obs.get("road_passable") in ("yes", "no") and not any(o.name == "road_passable" for o in observations):
            observations.append(S.Observation(name="road_passable", value=s.obs["road_passable"] == "yes",
                                              evidence_ids=[eid]))

    # Level or category by rule.
    level = category = None
    if site_kind == "home":
        result = lv.assign_level({k: v for k, (v, _) in fused.items()} | {"home_type": home_type})
        level, level_reason = result.level, result.reason
    else:
        element = next((s.obs.get("public_element") for s, _ in seen_ids
                        if s.obs.get("public_element") not in (None, "none")), None)
        category, level_reason = lv.public_category(element)

    # Location: typed, then voice quote, then photo GPS, then text read from the photo.
    location = S.Location(source="unknown")
    loc_ids: list[str] = []
    if typed_location:
        location = S.Location(text=typed_location, source="typed")
    elif quoted.get("location"):
        location = S.Location(text=quoted["location"][0][0], source="voice_note")
        loc_ids = [quoted["location"][0][1]]
    else:
        gps = next(((s, e) for s, e in seen_ids if s.lat is not None and s.lon is not None), None)
        text = next(((_said(s.obs.get("visible_text")), e) for s, e in seen_ids
                     if _said(s.obs.get("visible_text"))), None)
        if gps:
            location = S.Location(lat=gps[0].lat, lon=gps[0].lon, source="photo_gps",
                                  text=f"{gps[0].lat:.5f}, {gps[0].lon:.5f}")
            loc_ids = [gps[1]]
        elif text:
            location = S.Location(text=text[0][:120], source="photo_text")
            loc_ids = [text[1]]
        elif unverified.get("location"):
            location = S.Location(text=unverified["location"], source="voice_note")

    def fv(name: str, fallback: str | None = None, fallback_ids: list[str] | None = None) -> S.FieldValue:
        if quoted.get(name):
            return S.FieldValue(value=quoted[name][0][0],
                                evidence_ids=list(dict.fromkeys(e for _, e in quoted[name])))
        if fallback:
            return S.FieldValue(value=fallback, evidence_ids=fallback_ids or [])
        return S.FieldValue(value=unverified.get(name), needs_review=True)

    photo_desc = next(((_said(s.obs.get("description")), e) for s, e in seen_ids
                       if _said(s.obs.get("description"))), (None, None))
    # Text the model read off a photo is a hint, not a checked fact.
    loc_review = location.text is None or location.source == "photo_text" or (
        location.source != "typed" and not loc_ids)
    fields = {
        "location": S.FieldValue(value=location.text, evidence_ids=loc_ids, needs_review=loc_review),
        "damage": fv("damage", photo_desc[0], [photo_desc[1]] if photo_desc[1] else None),
        "people": fv("people"),
        "access": fv("access"),
    }

    # Hazards from words, sounds and the photo.
    hits: list[tuple[hz.HazardHit, str | None]] = []
    for h in heard:
        for hit in hz.from_transcript(h.segments) + hz.from_sounds(h.sounds):
            eid = ev.add(artifact_id=h.artifact_id, kind=h.kind, quote=hit.quote, verified=True,
                         locator=S.Locator(t_start=hit.t_start, t_end=hit.t_end),
                         match_score=100.0 if hit.source == "transcript" else None)
            hits.append((hit, eid))
    for s, eid in seen_ids:
        hits += [(hit, eid) for hit in hz.from_photo(s.obs)]
    hazards: dict[str, S.Hazard] = {}
    for hit, eid in hits:
        if hit.type in hazards:
            hazards[hit.type].evidence_ids.append(eid)
            continue
        hazards[hit.type] = S.Hazard(type=hit.type, message=hz.message(hit),
                                     severity=hz.SEVERITY[hit.type], evidence_ids=[eid] if eid else [])

    needs_review = level == "needs_inspection" or any(f.needs_review for f in fields.values())
    return S.Site(
        id=site_id, incident_id=incident_id, created_at=created_at, location=location, kind=site_kind,
        level=level if site_kind == "home" else None, level_reason=level_reason, category=category,
        observations=observations, hazards=sorted(hazards.values(), key=lambda x: x.severity != "life_safety"),
        fields=fields, evidence=ev.items, status="needs_review" if needs_review else "draft",
    )


# --------------------------------------------------------------------------- pipeline
async def build_site(
    *, incident_id: str, site_id: str, photo: tuple[str | None, bytes] | None,
    voice: tuple[str | None, bytes] | None, video: tuple[str | None, bytes] | None,
    location_text: str | None, profile: dict, progress,
) -> S.Site:
    limits, timeouts = profile["limits"], profile["timeouts_s"]
    work = normalize.make_work_dir()
    media = MEDIA_DIR / incident_id
    media.mkdir(parents=True, exist_ok=True)
    seen: list[Seen] = []
    heard: list[Heard] = []
    try:
        voice_task = None
        if voice:
            raw = normalize.write_upload(voice[1], voice[0], work / "voice")
            voice_task = asyncio.create_task(listen(raw))

        if photo:
            await progress("photo", 20, "Looking at the photo")
            raw = normalize.write_upload(photo[1], photo[0], work / "photo")
            img = normalize.normalize_image(raw, work / "photo_n", limits["image_max_px"], original_name=photo[0])
            name = f"{site_id}_photo.jpg"
            shutil.copyfile(img.path, media / name)
            obs = await observe_images([img.path], float(timeouts.get("image", 30)))
            seen.append(Seen("photo", "a_photo", obs, f"/api/media/{incident_id}/{name}", lat=img.lat, lon=img.lon))

        if voice_task:
            await progress("voice", 45, "Listening to the voice note")
            segments, sounds = await voice_task
            fields = await read_transcript(segments, float(timeouts.get("audio", 60)))
            heard.append(Heard("voice", "a_voice", segments, sounds, fields))

        if video:
            await progress("video", 65, "Watching the video")
            raw = normalize.write_upload(video[1], video[0], work / "video")
            frames, _ = await asyncio.to_thread(
                video_worker.extract_frames, raw, work / "frames", max_frames=4,
                frame_px=int(limits.get("frame_px", 512)), max_s=float(limits.get("video_max_s", 90)))
            segments, sounds = await listen(raw)
            if frames:
                obs = await observe_images([f.path for f in frames], float(timeouts.get("video", 120)))
                best = frames[min(max(int(obs.get("best_frame") or 0), 0), len(frames) - 1)]
                name = f"{site_id}_frame_{best.idx}.jpg"
                shutil.copyfile(best.path, media / name)
                seen.append(Seen("video_frame", "a_video", obs, f"/api/media/{incident_id}/{name}",
                                 frame_idx=best.idx, t=round(best.t, 1)))
            fields = await read_transcript(segments, float(timeouts.get("audio", 60))) if not voice else {}
            heard.append(Heard("video_audio", "a_video", segments, sounds, fields))

        await progress("rules", 90, "Applying FEMA rules")
        return assemble(site_id=site_id, incident_id=incident_id,
                        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                        typed_location=(location_text or "").strip() or None, seen=seen, heard=heard)
    finally:
        shutil.rmtree(work, ignore_errors=True)
