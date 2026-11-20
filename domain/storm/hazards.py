"""Life-safety hazards from three sources: words in the transcript, sound labels, and the photo."""
from __future__ import annotations

import re
from dataclasses import dataclass

from domain.storm.tones import TONE_MIN

PHRASES: dict[str, re.Pattern] = {
    "alarm_sounding": re.compile(
        r"\b((smoke|fire|co|carbon monoxide) )?(alarms?|detectors?) (is |are |was |were |keeps? |kept )?"
        r"(still )?(going off|beeping|chirping|sounding|ringing)\b", re.I),
    "downed_lines": re.compile(
        r"\b(power |electric(al)? )?(wires?|lines?) (are |is |were |was )?(down|on the ground|sparking)\b|"
        r"\bdowned (power )?lines?\b|\blive wires?\b", re.I),
    "gas_smell": re.compile(r"\bsmell(s|ing)? (of |like )?(natural )?gas\b|\bgas leak\b|\bsmells like gas\b", re.I),
    "fire": re.compile(r"\b(on fire|house fire|flames?|is burning|see smoke|smoke coming)\b", re.I),
    "trapped_person": re.compile(
        r"\btrapped\b|\bcan'?t get out\b|\bstuck (inside|in the)\b|\bsomeone('s| is)? (still )?inside\b", re.I),
    "medical_need": re.compile(
        r"\b(injur(ed|y|ies)|hurt|bleeding|unconscious|not breathing|needs? (a )?(doctor|ambulance|oxygen))\b", re.I),
    "flooding": re.compile(r"\bwater('s| is)? (still )?rising\b|\brushing water\b|\bswept away\b", re.I),
    "road_impassable": re.compile(
        r"\broad('s| is)? (closed|blocked|washed out|impassable|gone)\b|\bwashed out\b|\bcan'?t get through\b", re.I),
}

_NEGATION = re.compile(r"\b(no|not|never|without|don'?t|doesn'?t|didn'?t|isn'?t|aren'?t|wasn'?t)\b", re.I)

SEVERITY = {
    "alarm_sounding": "life_safety", "downed_lines": "life_safety", "gas_smell": "life_safety",
    "fire": "life_safety", "trapped_person": "life_safety", "medical_need": "life_safety",
    "flooding": "warning", "road_impassable": "warning",
}

MESSAGES = {
    "alarm_sounding": "An alarm may be sounding{at}. Check whether anyone is inside. If it could be a "
                      "smoke or CO alarm, get everyone out and call 911.",
    "downed_lines": "Downed power lines reported{at}. Assume they are live, stay at least 30 feet away, "
                    "and call 911 and the power company.",
    "gas_smell": "Gas smell reported{at}. Leave the area, don't use switches, lighters or phones near it, "
                 "and call 911 or the gas company from a safe distance.",
    "fire": "Fire or smoke reported{at}. Get everyone out and call 911.",
    "trapped_person": "Someone may be trapped{at}. Call 911 now with the exact address.",
    "medical_need": "Someone may need medical help{at}. Call 911.",
    "flooding": "Rising or rushing water{at}. Don't walk or drive through moving water.",
    "road_impassable": "Road reported impassable{at}. Mark it closed and tell the road crew.",
}

# CLAP label -> (hazard, minimum score). Alarms use a lower bar, since a missed alarm costs more,
# but also need the 3 kHz beep from tones.py, since CLAP alone hears some voices as alarms.
SOUND_HAZARDS = {"smoke_alarm": ("alarm_sounding", 0.25), "co_alarm": ("alarm_sounding", 0.25),
                 "rushing_water": ("flooding", 0.4)}
NEEDS_TONE = {"smoke_alarm", "co_alarm"}


@dataclass
class HazardHit:
    type: str
    source: str  # transcript | sound | photo
    t_start: float | None = None
    t_end: float | None = None
    quote: str | None = None


def _fmt(t: float | None) -> str:
    if t is None:
        return ""
    return f" at {int(t // 60)}:{int(t % 60):02d}"


def message(hit: HazardHit) -> str:
    return MESSAGES[hit.type].format(at=_fmt(hit.t_start))


def from_transcript(segments: list[dict]) -> list[HazardHit]:
    hits: list[HazardHit] = []
    for seg in segments:
        text = seg.get("text") or ""
        for kind, pattern in PHRASES.items():
            m = pattern.search(text)
            if not m or _NEGATION.search(text[max(0, m.start() - 24):m.start()]):
                continue
            hits.append(HazardHit(kind, "transcript", seg.get("t_start"), seg.get("t_end"), text.strip()))
    return hits


def from_sounds(events: list[dict]) -> list[HazardHit]:
    hits = []
    for ev in events:
        label = ev.get("label", "")
        rule = SOUND_HAZARDS.get(label)
        if not rule or float(ev.get("score", 0)) < rule[1]:
            continue
        quote = f"Sounds like {label.replace('_', ' ')} (confidence {round(100 * float(ev['score']))}%)"
        if label in NEEDS_TONE:
            if float(ev.get("tone", 0)) < TONE_MIN:
                continue
            quote += ", with a 3 kHz alarm beep"
        hits.append(HazardHit(rule[0], "sound", ev.get("t_start"), ev.get("t_end"), quote))
    return hits


def from_photo(obs: dict) -> list[HazardHit]:
    hits = []
    if obs.get("downed_lines") is True:
        hits.append(HazardHit("downed_lines", "photo"))
    if obs.get("road_passable") == "no":
        hits.append(HazardHit("road_impassable", "photo"))
    return hits
