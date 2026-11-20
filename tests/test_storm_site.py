"""StormLog site pipeline without models: FEMA rules, hazards, quote timing, assembly, store."""
from __future__ import annotations

import numpy as np

from backend import schemas as S
from backend.storm_store import FileStore
from backend.workers.site import Heard, Seen, assemble
from domain.storm import hazards as hz
from domain.storm import levels as lv
from domain.storm.tones import TONE_MIN, alarm_tone_fraction
from domain.verify import QUOTE_THRESHOLD, locate_quote

HOME = {"kind": "home", "home_type": "conventional", "water_line": "below_outlets", "roof": "none",
        "structure": "intact", "public_element": "none", "downed_lines": False, "road_passable": "yes",
        "visible_text": "", "description": "Muddy water on the living room floor."}

SEGMENTS = [
    {"t_start": 0.0, "t_end": 3.0, "text": "This is 14 Elm Street."},
    {"t_start": 3.0, "t_end": 7.5, "text": "Water came up past the outlets in the living room."},
    {"t_start": 7.5, "t_end": 10.0, "text": "I smell gas near the basement stairs."},
    {"t_start": 10.0, "t_end": 12.0, "text": "The garage roof caved in."},
]


def _site(seen=(), heard=(), typed=None) -> S.Site:
    return assemble(site_id="site_t", incident_id="inc_t", created_at="2026-11-19T00:00:00",
                    typed_location=typed, seen=list(seen), heard=list(heard))


# --------------------------------------------------------------------------- FEMA levels
def test_conventional_levels_follow_the_water_line():
    assert lv.assign_level({"water_line": "below_outlets", "roof": "none", "structure": "intact"}).level == "minor"
    assert lv.assign_level({"water_line": "at_or_above_outlets", "roof": "none", "structure": "intact"}).level == "major"
    assert lv.assign_level({"water_line": "at_or_above_ceiling"}).level == "destroyed"


def test_manufactured_homes_use_their_own_table():
    obs = {"home_type": "manufactured", "water_line": "below_outlets", "roof": "none", "structure": "intact"}
    result = lv.assign_level(obs)
    assert result.level == "major"
    assert "manufactured home" in result.reason and "p. 48" in result.reason


def test_most_severe_observation_wins_and_cites_a_page():
    result = lv.assign_level({"water_line": "none", "roof": "cosmetic", "structure": "collapsed"})
    assert result.level == "destroyed"
    assert "(p. 50)" in result.reason


def test_unknown_evidence_needs_inspection_and_no_damage_has_no_level():
    unknown = lv.assign_level({"water_line": "unknown", "roof": "unknown", "structure": "unknown"})
    assert unknown.level == "needs_inspection"
    assert lv.assign_level({"water_line": "none", "roof": "none", "structure": "intact"}).level is None


def test_public_category_by_element():
    assert lv.public_category("culvert")[0] == "C"
    assert lv.public_category("debris")[0] == "A"
    assert lv.public_category(None)[0] is None


def test_water_line_from_spoken_words():
    assert lv.water_line_from_text("Water came up past the outlets in the living room.") == "at_or_above_outlets"
    assert lv.water_line_from_text("It was just below the outlets.") == "below_outlets"
    assert lv.water_line_from_text("The water reached the ceiling upstairs.") == "at_or_above_ceiling"
    assert lv.water_line_from_text("The water didn't reach the outlets.") is None
    assert lv.water_line_from_text("It got almost to the ceiling.") is None
    assert lv.water_line_from_text("Two feet of water in the basement.") == "crawlspace_or_basement"
    assert lv.water_line_from_text("I smell gas near the basement stairs.", quote=False) is None


# --------------------------------------------------------------------------- hazards
def test_hazard_phrases_respect_negation():
    hits = hz.from_transcript([{"t_start": 65.0, "t_end": 68.0, "text": "The power lines are down on Elm."}])
    assert [h.type for h in hits] == ["downed_lines"]
    assert "at 1:05" in hz.message(hits[0])
    assert hz.from_transcript([{"t_start": 0, "t_end": 2, "text": "I don't smell gas anywhere."}]) == []
    assert [h.type for h in hz.from_transcript([{"t_start": 0, "t_end": 2, "text": "I smell gas."}])] == ["gas_smell"]
    said = hz.from_transcript([{"t_start": 0, "t_end": 2, "text": "The smoke alarm is still going off."}])
    assert [h.type for h in said] == ["alarm_sounding"]


def test_sound_hazards_use_per_label_thresholds_and_need_the_beep_for_alarms():
    events = [{"label": "smoke_alarm", "score": 0.3, "tone": 0.2, "t_start": 4.0, "t_end": 9.0},
              {"label": "co_alarm", "score": 0.7, "tone": 0.01, "t_start": 0.0, "t_end": 5.0},
              {"label": "co_alarm", "score": 0.2, "tone": 0.2, "t_start": 0.0, "t_end": 5.0},
              {"label": "rushing_water", "score": 0.35, "t_start": 0.0, "t_end": 5.0}]
    hits = hz.from_sounds(events)
    assert [h.type for h in hits] == ["alarm_sounding"]
    assert "smoke alarm" in hits[0].quote and "30%" in hits[0].quote and "3 kHz" in hits[0].quote


def _beeps(seconds: float, sr: int, on_s: float, period_s: float, freq: float = 3200.0) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * freq * t) * ((t % period_s) < on_s)).astype(np.float32)


def test_alarm_tone_check_hears_beeps_but_not_voices_or_rain():
    sr = 48000
    t = np.arange(5 * sr) / sr
    voice = sum((0.5 / k) * np.sin(2 * np.pi * 180 * k * t) for k in range(1, 40)).astype(np.float32)
    rain = (0.05 * np.random.default_rng(0).standard_normal(5 * sr)).astype(np.float32)
    assert alarm_tone_fraction(voice, sr) < TONE_MIN
    assert alarm_tone_fraction(rain, sr) < TONE_MIN
    assert alarm_tone_fraction(_beeps(5, sr, 0.5, 1.0), sr) > 0.2
    assert alarm_tone_fraction(voice * 0.1 + _beeps(5, sr, 0.1, 0.2), sr) > TONE_MIN


# --------------------------------------------------------------------------- quote timing
def test_locate_quote_finds_the_segment_and_rejects_made_up_quotes():
    t0, t1, score = locate_quote("water came up past the outlets", SEGMENTS)
    assert (t0, t1) == (3.0, 7.5) and score >= QUOTE_THRESHOLD
    assert locate_quote("the roof blew off", SEGMENTS)[2] < QUOTE_THRESHOLD


# --------------------------------------------------------------------------- assembly
def test_assemble_fuses_photo_and_voice_with_evidence():
    voice = Heard("voice", "a_voice", SEGMENTS, [], {
        "location": {"value": "14 Elm Street", "quote": "This is 14 Elm Street"},
        # The model picked the wrong level; the rule reads the verified quote instead.
        "water_line": {"value": "below_outlets", "quote": "Water came up past the outlets"},
        "people": {"value": "family of four", "quote": "a family of four lives here"},
        "damage": {"value": "flooded living room, garage roof caved in",
                   "quote": "Water came up past the outlets in the living room. The garage roof caved in."},
        "access": {"value": "", "quote": ""},
    })
    site = _site([Seen("photo", "a_photo", HOME, "/api/media/inc_t/site_t_photo.jpg")], [voice])
    ev = {e.id: e for e in site.evidence}

    assert site.kind == "home" and site.level == "major"
    assert "outlets" in site.level_reason
    water = next(o for o in site.observations if o.name == "water_line")
    assert water.value == "at_or_above_outlets" and ev[water.evidence_ids[0]].kind == "voice"
    assert ev[water.evidence_ids[0]].locator.t_start == 3.0

    assert site.location.source == "voice_note" and site.location.text == "14 Elm Street"
    damage = site.fields["damage"]
    assert not damage.needs_review and [ev[e].locator.t_start for e in damage.evidence_ids] == [3.0, 10.0]
    assert site.fields["people"].needs_review and site.fields["people"].value == "family of four"
    assert site.status == "needs_review"

    assert [h.type for h in site.hazards] == ["gas_smell"]
    gas = ev[site.hazards[0].evidence_ids[0]]
    assert gas.verified and gas.locator.t_start == 7.5
    keys = [(e.kind, e.quote, e.locator.t_start if e.locator else None) for e in site.evidence]
    assert len(keys) == len(set(keys))


def test_assemble_typed_location_wins_and_photo_gps_is_next():
    seen = Seen("photo", "a_photo", HOME, lat=44.10, lon=-69.10)
    assert _site([seen], typed="22 Main St").location.source == "typed"
    gps = _site([seen]).location
    assert gps.source == "photo_gps" and gps.lat == 44.10


def test_photo_text_is_a_location_hint_and_unknown_is_not_text():
    signed = _site([Seen("photo", "a_photo", HOME | {"visible_text": "1423"})])
    assert signed.location.source == "photo_text" and signed.fields["location"].needs_review
    blank = _site([Seen("photo", "a_photo", HOME | {"visible_text": "unknown"})])
    assert blank.location.source == "unknown" and blank.location.text is None


def test_assemble_public_site_gets_category_and_road_hazard():
    culvert = HOME | {"kind": "public", "public_element": "culvert", "road_passable": "no",
                      "water_line": "unknown", "roof": "unknown", "structure": "unknown"}
    site = _site([Seen("photo", "a_photo", culvert | {"roof": "none", "structure": "intact"})])
    assert site.kind == "public" and site.category == "C" and site.level is None
    assert [h.type for h in site.hazards] == ["road_impassable"]
    assert [o.name for o in site.observations] == ["road_passable"]


def test_assemble_with_nothing_visible_needs_inspection():
    blank = HOME | {"water_line": "unknown", "roof": "unknown", "structure": "unknown", "description": ""}
    site = _site([Seen("photo", "a_photo", blank)])
    assert site.level == "needs_inspection" and site.status == "needs_review"
    assert site.fields["location"].needs_review


def test_sound_alarm_becomes_a_verified_hazard():
    sounds = [{"label": "smoke_alarm", "score": 0.6, "tone": 0.3, "t_start": 2.0, "t_end": 7.0}]
    site = _site(heard=[Heard("voice", "a_voice", [], sounds, {})])
    assert [h.type for h in site.hazards] == ["alarm_sounding"]
    assert site.evidence[0].quote.startswith("Sounds like smoke alarm")


# --------------------------------------------------------------------------- store
def test_file_store_persists_sites(tmp_path):
    path = tmp_path / "store.json"
    store = FileStore(path)
    assert len(store.incidents) == 1 and not store.sites
    inc_id = next(iter(store.incidents))
    site = _site([Seen("photo", "a_photo", HOME)]).model_copy(update={"incident_id": inc_id})
    store.put_site(site)
    again = FileStore(path)
    assert again.sites[site.id].level == "minor"
