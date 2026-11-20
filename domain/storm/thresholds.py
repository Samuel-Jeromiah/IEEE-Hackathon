"""FEMA county threshold for an incident: countywide indicator × county population, by fixed rule.

The indicator year follows the incident's start date (a federal fiscal year starts Oct 1).
Figures and their sources live in thresholds.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parent / "thresholds.yaml"


@dataclass(frozen=True)
class CountyIndicator:
    county: str
    population: int
    per_capita_usd: float
    fiscal_year: int
    threshold_usd: float
    source: str


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def fiscal_year(day: date) -> int:
    return day.year + 1 if day.month >= 10 else day.year


def _county_name(county: str | None) -> str | None:
    if not county:
        return None
    name = county.strip().removesuffix(" County").removesuffix(" county").strip().lower()
    return next((c for c in load()["counties"] if c.lower() == name), None)


def county_indicator(county: str | None, started: str | None, today: date | None = None) -> CountyIndicator | None:
    """None when the county isn't in the table; the town report then asks for it."""
    data = load()
    name = _county_name(county)
    if name is None:
        return None
    try:
        day = date.fromisoformat(started[:10]) if started else (today or date.today())
    except ValueError:
        day = today or date.today()
    years = sorted(data["indicators"])
    fy = fiscal_year(day)
    use = fy if fy in data["indicators"] else (years[-1] if fy > years[-1] else years[0])
    ind = data["indicators"][use]
    population = int(data["counties"][name])
    per_capita = float(ind["countywide"])
    note = "" if use == fy else f" FY{fy} figures aren't loaded, so FY{use} is used."
    source = (f"FEMA FY{use} countywide indicator ({ind['source']}) × {name} County population "
              f"({data['population_source']}).{note}")
    return CountyIndicator(name, population, per_capita, use, round(population * per_capita, 2), source)
