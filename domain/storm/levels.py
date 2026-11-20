"""FEMA degree of damage for homes and PA category for public sites, set by fixed rules.

The model only reports what it sees or hears (the observation values below). These rules,
not the model, turn observations into a level. Criteria and page numbers (PDF pages) come
from the FEMA Preliminary Damage Assessment Guide, July 2025.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

GUIDE = "FEMA PDA Guide (July 2025)"

WATER_LINE = ("none", "crawlspace_or_basement", "below_outlets", "at_or_above_outlets",
              "at_or_above_ceiling", "unknown")
ROOF = ("none", "cosmetic", "structural", "collapsed", "unknown")
STRUCTURE = ("intact", "cosmetic", "structural", "collapsed", "only_foundation", "unknown")
HOME_TYPE = ("conventional", "manufactured", "unknown")
PUBLIC_ELEMENT = ("none", "debris", "road", "bridge", "culvert", "water_control", "public_building",
                  "utility", "park")

_RANK = {"affected": 1, "minor": 2, "major": 3, "destroyed": 4}

# (observation, value) -> (level, rule text with page)
_CONVENTIONAL = {
    ("structure", "collapsed"): ("destroyed", "Collapse of the foundation, walls or roof (p. 50)"),
    ("structure", "only_foundation"): ("destroyed", "Only the foundation remains (p. 50)"),
    ("roof", "collapsed"): ("destroyed", "Collapse of the roof (p. 50)"),
    ("water_line", "at_or_above_ceiling"): (
        "destroyed", "Waterline at or above the ceiling of an above-ground essential living space (p. 50)"),
    ("water_line", "at_or_above_outlets"): (
        "major", "Waterline at or above the electrical outlets in an essential living space (p. 49)"),
    ("roof", "structural"): (
        "major", "Failure or partial failure of structural elements of the roof over living space (p. 49)"),
    ("structure", "structural"): (
        "major", "Structural damage, such as failure of the foundation or walls (p. 49)"),
    ("water_line", "below_outlets"): (
        "minor", "Waterline below the electrical outlets in the lowest floor with living space (p. 49)"),
    ("roof", "cosmetic"): (
        "minor", "Nonstructural damage to roof components such as shingles or flashing (p. 49)"),
    ("water_line", "crawlspace_or_basement"): (
        "affected", "Waterline in the crawl space or an unfinished basement (p. 48)"),
    ("structure", "cosmetic"): (
        "affected", "Cosmetic damage only, such as siding, paint or gutters (p. 46)"),
}

_MANUFACTURED = {
    ("structure", "collapsed"): ("destroyed", "Frame bent, twisted or otherwise compromised (p. 48)"),
    ("structure", "only_foundation"): ("destroyed", "Home is a total loss (p. 48)"),
    ("roof", "collapsed"): ("destroyed", "Most of the structural framing of the roof is compromised (p. 48)"),
    ("water_line", "at_or_above_ceiling"): ("destroyed", "Waterline at or above the ceiling (p. 48)"),
    ("water_line", "at_or_above_outlets"): ("major", "Water entered the living space (p. 48)"),
    ("water_line", "below_outlets"): ("major", "Water entered the living space (p. 48)"),
    ("roof", "structural"): ("major", "The roof is substantially damaged (p. 48)"),
    ("structure", "structural"): ("major", "Displaced from its foundation or structural damage (p. 48)"),
    ("water_line", "crawlspace_or_basement"): (
        "minor", "Waterline reached the floor system but not the living space (p. 47)"),
    ("roof", "cosmetic"): ("affected", "Cosmetic damage such as shingles or gutters (p. 47)"),
    ("structure", "cosmetic"): ("affected", "Cosmetic damage such as skirting or paint (p. 47)"),
}

_NO_DAMAGE = {("water_line", "none"), ("roof", "none"), ("structure", "intact")}

_CATEGORY = {
    "debris": ("A", "Debris removal"),
    "road": ("C", "Roads and bridges"),
    "bridge": ("C", "Roads and bridges"),
    "culvert": ("C", "Roads and bridges"),
    "water_control": ("D", "Water control facilities"),
    "public_building": ("E", "Public buildings and equipment"),
    "utility": ("F", "Public utilities"),
    "park": ("G", "Parks, recreational and other facilities"),
}


@dataclass
class LevelResult:
    level: str | None  # affected | minor | major | destroyed | needs_inspection | None (no damage seen)
    reason: str
    unknown: list[str]


def assign_level(observations: dict[str, str]) -> LevelResult:
    """Take the most severe level any known observation supports."""
    home_type = observations.get("home_type") or "unknown"
    table = _MANUFACTURED if home_type == "manufactured" else _CONVENTIONAL
    keys = ("water_line", "roof", "structure")
    unknown = [k for k in keys if (observations.get(k) or "unknown") == "unknown"]
    hits = [table[(k, observations[k])] for k in keys if (k, observations.get(k)) in table]

    if not hits:
        if unknown:
            seen = ", ".join(k.replace("_", " ") for k in unknown)
            return LevelResult("needs_inspection",
                               f"The evidence doesn't show the {seen}, so an inspector needs to check.", unknown)
        return LevelResult(None, "No damage is visible in the evidence.", unknown)

    level, rule = max(hits, key=lambda h: _RANK[h[0]])
    home = "manufactured home" if home_type == "manufactured" else "conventionally built home"
    reason = f"{rule}, {GUIDE}, {home}."
    if unknown and level != "destroyed":
        reason += f" Not in the evidence: {', '.join(k.replace('_', ' ') for k in unknown)}."
    return LevelResult(level, reason, unknown)


_NOT = re.compile(r"(\bnot|n't|\bnever|\balmost|\bnearly|\bjust short of)\b[^.]{0,16}$", re.I)
_TARGET = r"(the\s+)?(electrical\s+|power\s+|wall\s+)?(outlets?|sockets?)\b"
_REACHED = r"\b(to|up to|reach(ed|ing)?|at|above|over|past|covered|covering|hit)\s+"
_WATER_RULES = (
    ("at_or_above_ceiling", re.compile(_REACHED + r"(the\s+)?ceilings?\b", re.I), True),
    ("below_outlets", re.compile(r"\b(below|under|beneath|short of)\s+" + _TARGET, re.I), True),
    ("at_or_above_outlets", re.compile(_REACHED + _TARGET, re.I), True),
    ("crawlspace_or_basement", re.compile(r"\b(basement|crawl\s?space|cellar)\b", re.I), False),
)


def water_line_from_text(text: str, *, quote: bool = True) -> str | None:
    """Read the water line from words someone said, like "water came up past the outlets".

    The basement rule only applies to a quote already about the water line (quote=True),
    since a basement is often mentioned for other reasons.
    """
    for value, pattern, anywhere in _WATER_RULES:
        if not (anywhere or quote):
            continue
        m = pattern.search(text or "")
        if m and not _NOT.search(text[:m.start()]):
            return value
    return None


def public_category(element: str | None) -> tuple[str | None, str]:
    if element in _CATEGORY:
        cat, name = _CATEGORY[element]
        return cat, f"Category {cat}, {name}: the evidence shows damage to a {element.replace('_', ' ')}."
    return None, "The evidence doesn't show which FEMA category applies."
