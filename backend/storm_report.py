"""Town report for an incident: totals and the FEMA county threshold, all by fixed rules (no models)."""
from __future__ import annotations

from backend import schemas as S
from domain.storm import thresholds

COLUMNS = ["site_id", "kind", "location", "level", "category", "est_cost", "status", "needs_review",
           "hazards", "road_closed", "damage"]


def build_report(incident: S.Incident, sites: list[S.Site]) -> S.IncidentReport:
    by_level: dict[str, int] = {}
    by_cat: dict[str, float] = {}
    for s in sites:
        if s.kind == "home" and s.level:
            by_level[s.level] = by_level.get(s.level, 0) + 1
        if s.kind == "public" and s.category:
            by_cat[s.category] = by_cat.get(s.category, 0.0) + (s.est_cost or 0.0)
    public = round(sum(by_cat.values()), 2)
    ind = thresholds.county_indicator(incident.county, incident.started)
    threshold = None
    if ind:
        threshold = S.Threshold(
            county=ind.county, population=ind.population, per_capita_usd=ind.per_capita_usd,
            fiscal_year=f"FY{ind.fiscal_year}", threshold_usd=ind.threshold_usd, public_damage_usd=public,
            percent_of_threshold=round(100 * public / ind.threshold_usd, 1), source=ind.source)
    return S.IncidentReport(
        incident=incident, sites=sites, totals_by_level=by_level, totals_by_category_usd=by_cat,
        hazards_open=sum(1 for s in sites for h in s.hazards if s.status != "approved"),
        threshold=threshold,
    )


def site_rows(sites: list[S.Site]) -> list[dict]:
    """One flat row per site, for the analysis table."""
    rows = []
    for s in sites:
        damage = s.fields.get("damage")
        road_closed = any(h.type == "road_impassable" for h in s.hazards) or any(
            o.name == "road_passable" and o.value is False for o in s.observations)
        rows.append({
            "site_id": s.id, "kind": s.kind, "location": s.location.text or "",
            "level": s.level or "", "category": s.category or "", "est_cost": s.est_cost,
            "status": s.status,
            "needs_review": s.status == "needs_review" or any(f.needs_review for f in s.fields.values()),
            "hazards": ";".join(h.type for h in s.hazards), "road_closed": road_closed,
            "damage": str(damage.value) if damage and damage.value is not None else "",
        })
    return rows
