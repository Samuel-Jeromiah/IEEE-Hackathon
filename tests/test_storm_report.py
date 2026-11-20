"""Town report without models: FEMA county threshold by rule, totals, and the analysis table."""
from __future__ import annotations

from datetime import date

import pytest

from backend import schemas as S
from backend.sandbox import runner
from backend.storm_report import build_report, site_rows
from backend.workers.analysis import EXAMPLES, preamble, problems
from backend.workers.code import parse_reply
from domain.storm import thresholds


def test_fiscal_year_starts_october_first():
    assert thresholds.fiscal_year(date(2026, 9, 30)) == 2026
    assert thresholds.fiscal_year(date(2026, 10, 1)) == 2027


def test_county_indicator_uses_incident_start_date_and_2020_census():
    knox = thresholds.county_indicator("Knox", "2026-11-17")
    assert (knox.county, knox.population, knox.per_capita_usd, knox.fiscal_year) == ("Knox", 40607, 5.03, 2027)
    assert knox.threshold_usd == 204253.21
    assert "91 FR 70093" in knox.source and "2020 Census" in knox.source
    earlier = thresholds.county_indicator("knox county", "2026-09-15")
    assert (earlier.per_capita_usd, earlier.fiscal_year) == (4.86, 2026)
    assert thresholds.county_indicator("Cumberland", "2026-11-17").population == 303069


def test_county_indicator_unknown_county_or_missing_year():
    assert thresholds.county_indicator("Coos", "2026-11-17") is None
    assert thresholds.county_indicator(None, "2026-11-17") is None
    later = thresholds.county_indicator("Knox", "2029-01-05")
    assert later.fiscal_year == 2027 and "FY2029 figures aren't loaded" in later.source


def _incident(county: str | None = "Knox") -> S.Incident:
    return S.Incident(id="inc_t", name="Test storm", town="Rockland", county=county, started="2026-11-17",
                      created_at="2026-11-17T12:00:00+00:00")


def _sites() -> list[S.Site]:
    culvert = S.Site(id="s1", incident_id="inc_t", created_at="t", kind="public", category="C", est_cost=48000.0,
                     hazards=[S.Hazard(type="road_impassable", message="m", severity="warning")])
    home = S.Site(id="s2", incident_id="inc_t", created_at="t", kind="home", level="major", status="needs_review",
                  location=S.Location(text='O\'Brien "Farm"\nRoad', source="typed"),
                  fields={"damage": S.FieldValue(value='water """ past outlets', needs_review=True)})
    return [culvert, home]


def test_report_totals_and_threshold():
    rep = build_report(_incident(), _sites())
    assert rep.totals_by_level == {"major": 1} and rep.totals_by_category_usd == {"C": 48000.0}
    assert rep.threshold.public_damage_usd == 48000.0 and rep.threshold.percent_of_threshold == 23.5
    assert rep.threshold.fiscal_year == "FY2027" and rep.hazards_open == 1
    assert build_report(_incident(None), _sites()).threshold is None


def test_site_rows_flatten_review_and_road_closed():
    rows = site_rows(_sites())
    assert rows[0]["road_closed"] and not rows[0]["needs_review"]
    assert rows[1]["needs_review"] and rows[1]["level"] == "major" and rows[1]["est_cost"] is None


def test_analysis_setup_runs_in_the_sandbox_with_awkward_text():
    rep = build_report(_incident(), _sites())
    code = preamble(site_rows(rep.sites), rep.threshold) + (
        "total = sites['est_cost'].sum()\n"
        "print(f'{total:.2f} {THRESHOLD_USD} {COUNTY}')\n"
        "print(sites.loc[1, 'location'])\n")
    result = runner.run_python(code, "assert len(sites) == 2\nassert sites['road_closed'].sum() == 1",
                               profile="data")
    assert result.ok, result.stderr
    assert result.stdout.splitlines()[0] == "48000.00 204253.21 Knox"
    assert 'O\'Brien "Farm"' in result.stdout


@pytest.mark.parametrize("task,reply", EXAMPLES)
def test_worked_examples_pass_the_checks_and_run(task, reply):
    draft = parse_reply(reply)
    assert draft.explanation and problems(draft.code, draft.tests, task) == []
    for county in ("Knox", None):
        rep = build_report(_incident(county), _sites())
        result = runner.run_python(preamble(site_rows(rep.sites), rep.threshold) + draft.code, draft.tests,
                                   profile="data")
        assert result.ok, result.stderr


@pytest.mark.parametrize("code,expected", [
    ("sites = pd.DataFrame({'a': [1]})\nprint(sites)", "Don't reassign sites"),
    ("THRESHOLD_USD = 1\nprint(THRESHOLD_USD)", "Don't reassign THRESHOLD_USD"),
    ("county_threshold = 100000.0\nprint(county_threshold)", "numbers like 100,000"),
    ("Sites needing review:\n   site_id  kind", "syntax error on line 1"),
    ("", "no code"),
])
def test_problems_catch_rebuilt_data_typed_numbers_and_pasted_output(code, expected):
    assert any(expected in p for p in problems(code, "", "Total the damage by category."))


def test_problems_allow_column_edits_percentages_and_numbers_from_the_question():
    code = ("sites['over'] = sites['est_cost'] > 10000\n"
            "public = sites[sites['kind'] == 'public']\n"
            "pct = 100 * public['est_cost'].sum() / THRESHOLD_USD\n"
            "print(pct)")
    tests = "assert len(public) <= len(sites)\nassert 0 <= pct <= 100"
    assert problems(code, tests, "Which sites cost more than $10,000?") == []


@pytest.mark.parametrize("tests,expected", [
    ("assert len(public) == 2", "numbers you were shown, like 2"),
    ("assert len(public) == 1", "like 1"),
    ("assert totals['C'] == 48000.0", "like 48000"),
    ("", "no tests"),
])
def test_problems_catch_tests_with_copied_values(tests, expected):
    assert any(expected in p for p in problems("public = sites[sites['kind'] == 'public']", tests, "Totals?"))
