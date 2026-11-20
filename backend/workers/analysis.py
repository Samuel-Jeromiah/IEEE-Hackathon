"""Incident analysis: the coder writes pandas code over this incident's sites, and it runs in the sandbox.

The data is written into the script as a literal table, so the code needs no files, and the
printed output comes from code that actually ran on the town's sites. Small coder models like to
rebuild the table from the sample rows or type in a threshold of their own, so a static check
rejects that before anything runs and asks for a fix.
"""
from __future__ import annotations

import ast
import asyncio
import re
from dataclasses import replace

from backend import schemas as S
from backend.guard.prompts import with_rule, wrap_untrusted
from backend.sandbox import runner
from backend.storm_report import COLUMNS, site_rows
from backend.workers import code as code_worker

MAX_ATTEMPTS = 3
PROTECTED = {"sites", "pd", "COUNTY", "POPULATION", "PER_CAPITA_USD", "THRESHOLD_USD", "FISCAL_YEAR"}
COLUMN_NOTES = (
    "site_id (text); kind (\"home\" or \"public\"); location (text, empty when not set); level (FEMA level "
    "for homes: affected, minor, major, destroyed or needs_inspection, empty for public sites); category "
    "(FEMA Public Assistance category A to G for public sites, empty for homes); est_cost (float, USD "
    "entered by a person, NaN when not entered, only public sites have one); status (draft, needs_review "
    "or approved); needs_review (bool); hazards (hazard types joined by \";\", such as "
    "gas_smell;road_impassable, empty when none); road_closed (bool); damage (short text)"
)
SYSTEM = (
    "You analyze storm damage data with pandas. A DataFrame named `sites` is already loaded with the real "
    "data, one row per site, with columns: {columns}. These constants are already defined: {constants}. "
    "Reply with three parts in this order: (1) one plain sentence on the approach; (2) a ```python block "
    "that works out the answer from `sites` and the constants and prints it as short labelled lines (when "
    "listing sites, one line per site with its location, or 'location not set', and its site_id; dollar "
    "amounts like $1,234.56); (3) a second ```python block with 2 to 4 assert statements that check the "
    "result is consistent. Rules: never create or reassign `sites` "
    "or the constants (give filtered tables a new name); never type in numbers or rows you were shown, "
    "compute them; no plots, files, input() or network; only Python inside the blocks."
)
EXAMPLES = [
    ("How far is the public damage from the county threshold, split by review status?",
     "Add up the entered costs of public sites per status, then compare the total with THRESHOLD_USD.\n"
     "```python\n"
     "public = sites[sites['kind'] == 'public']\n"
     "by_status = public.groupby('status')['est_cost'].sum()\n"
     "total = by_status.sum()\n"
     "print(f\"Public damage entered: ${total:,.2f} across {len(public)} public sites\")\n"
     "for status, cost in by_status.items():\n"
     "    print(f\"- {status}: ${cost:,.2f}\")\n"
     "if THRESHOLD_USD is None:\n"
     "    print(\"No county threshold: set the incident's county first.\")\n"
     "else:\n"
     "    print(f\"{COUNTY} County threshold ({FISCAL_YEAR}): ${THRESHOLD_USD:,.2f}\")\n"
     "    print(f\"Reached: {100 * total / THRESHOLD_USD:.1f}%, still needed: "
     "${max(THRESHOLD_USD - total, 0):,.2f}\")\n"
     "```\n"
     "```python\n"
     "assert len(by_status) <= len(public) <= len(sites)\n"
     "assert total == public['est_cost'].fillna(0).sum()\n"
     "```"),
    ("Which sites have a gas smell?",
     "Keep the rows whose hazards include gas_smell and print one line for each.\n"
     "```python\n"
     "gas = sites[sites['hazards'].str.contains('gas_smell')]\n"
     "print(f\"Sites with a gas smell: {len(gas)} of {len(sites)}\")\n"
     "for _, row in gas.iterrows():\n"
     "    print(f\"- {row['location'] or 'location not set'} ({row['site_id']}, {row['status']})\")\n"
     "```\n"
     "```python\n"
     "assert len(gas) <= len(sites)\n"
     "assert gas['hazards'].str.contains('gas_smell').all()\n"
     "```"),
    ("How many sites are in each status?",
     "Count the rows per status and print one line for each.\n"
     "```python\n"
     "counts = sites['status'].value_counts()\n"
     "print(f\"Sites: {len(sites)}\")\n"
     "for status, n in counts.items():\n"
     "    print(f\"- {status}: {n}\")\n"
     "```\n"
     "```python\n"
     "assert counts.sum() == len(sites)\n"
     "assert set(counts.index) <= {'draft', 'needs_review', 'approved'}\n"
     "```"),
]


def preamble(rows: list[dict], threshold: S.Threshold | None) -> str:
    """The setup the model's code runs after: this incident's sites and the county threshold."""
    lines = ["import pandas as pd", "", "# This incident's sites, one row each (from the town report).",
             "sites = pd.DataFrame(["]
    lines += [f"    {row!r}," for row in rows]
    lines += [f"], columns={COLUMNS!r})", "sites['est_cost'] = sites['est_cost'].astype(float)", ""]
    t = threshold
    lines += [
        "# FEMA county threshold (domain/storm/thresholds.yaml).",
        f"COUNTY = {t.county if t else None!r}",
        f"POPULATION = {t.population if t else None!r}",
        f"PER_CAPITA_USD = {t.per_capita_usd if t else None!r}",
        f"THRESHOLD_USD = {t.threshold_usd if t else None!r}",
        f"FISCAL_YEAR = {t.fiscal_year if t else None!r}",
        "",
    ]
    return "\n".join(lines)


def _parse(text: str, label: str) -> tuple[ast.Module | None, list[str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return None, [f"The {label} block has a syntax error on line {exc.lineno} ({exc.msg}). "
                      "Put only Python inside the blocks, not printed output."]
    names = sorted({n.id for n in ast.walk(tree)
                    if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load) and n.id in PROTECTED})
    if names:
        return tree, [f"Don't reassign {', '.join(names)}: it already holds the real data. "
                      "Give filtered tables a new name."]
    return tree, []


def _typed(nodes, prompt: str, keep) -> list[float]:
    """Numbers written into the code that the question didn't give."""
    given = re.sub(r"[,$_]", "", prompt)
    return sorted({abs(n.value) for n in nodes if isinstance(n, ast.Constant) and type(n.value) in (int, float)
                   and keep(abs(n.value)) and f"{abs(n.value):.0f}" not in given})


def code_problems(code: str, prompt: str) -> list[str]:
    """Reasons not to run the code at all: syntax, rebuilt data, or a typed-in amount."""
    if not code.strip():
        return ["There was no code. Put the code in a ```python block."]
    tree, found = _parse(code, "code")
    typed = _typed(ast.walk(tree), prompt, lambda v: v >= 1000) if tree else []
    if typed:
        found.append(f"Don't type in numbers like {typed[0]:,.0f}: use THRESHOLD_USD, POPULATION or values "
                     "computed from `sites`.")
    return found


def assert_problems(tests: str, prompt: str) -> list[str]:
    """Tests must check consistency, not values copied from the rows the model was shown."""
    if not tests.strip():
        return ["There were no tests. Add a second ```python block with 2 to 4 assert statements."]
    tree, found = _parse(tests, "tests")
    typed = []
    for n in ast.walk(tree) if tree else []:
        if isinstance(n, ast.Compare):
            # bounds like 0 <= share <= 1 are fine; equality with a typed number is a copied value
            ok = (0,) if any(isinstance(op, (ast.Eq, ast.NotEq)) for op in n.ops) else (0, 1, 100)
            typed += _typed([n.left, *n.comparators], prompt, lambda v, ok=ok: v not in ok)
    if typed:
        found.append(f"Tests can't compare with numbers you were shown, like {typed[0]:g}: check the result "
                     "is consistent with `sites` instead, such as len(x) <= len(sites).")
    return found


def problems(code: str, tests: str, prompt: str) -> list[str]:
    return code_problems(code, prompt) + assert_problems(tests, prompt)


def _rank(result: runner.RunResult) -> tuple[bool, bool]:
    return result.ok, bool(result.stdout.strip())


def _messages(prompt: str, rows: list[dict], threshold: S.Threshold | None) -> list[dict]:
    constants = ("COUNTY, POPULATION, PER_CAPITA_USD, THRESHOLD_USD (county threshold in USD) and FISCAL_YEAR"
                 if threshold else "COUNTY, POPULATION, PER_CAPITA_USD, THRESHOLD_USD and FISCAL_YEAR, all None "
                 "because the incident has no county yet")
    sample = "\n".join(repr(r) for r in rows[:5]) or "(no sites yet)"
    wrapped, rule = wrap_untrusted(sample, "site rows")
    system = SYSTEM.format(columns=COLUMN_NOTES, constants=constants)
    messages = [{"role": "system", "content": with_rule(system, rule)}]
    for task, reply in EXAMPLES:
        messages += [{"role": "user", "content": f"Task: {task}"}, {"role": "assistant", "content": reply}]
    messages.append({"role": "user", "content": (
        f"Task: {prompt}\n\n`sites` has {len(rows)} rows. The first rows, for reference only:\n{wrapped}")})
    return messages


async def run(prompt: str, report: S.IncidentReport, *, timeout_s: float) -> S.AnalysisResult:
    rows = site_rows(report.sites)
    setup = preamble(rows, report.threshold)
    messages = _messages(prompt, rows, report.threshold)
    best: tuple[code_worker.Draft, runner.RunResult] | None = None
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        draft, _ = await code_worker.ask(messages, timeout_s)
        code_issues, test_issues = code_problems(draft.code, prompt), assert_problems(draft.tests, prompt)
        feedback = code_issues + test_issues
        if code_issues:
            result = runner.RunResult(False, stderr="Not run: " + " ".join(code_issues))
        else:
            # bad tests don't stop the code from running, so the answer can still be shown
            tests = "" if test_issues else draft.tests
            result = await asyncio.to_thread(runner.run_python, setup + draft.code, tests, profile="data")
            if result.blocked:
                feedback.append(f"The sandbox refused it ({result.blocked}). Use only pandas and the "
                                "standard library, with no files or network.")
            elif not result.ok:
                out = result.stdout.strip()
                feedback.append((f"It printed:\n{out[-1000:]}\n" if out else "")
                                + f"Then it failed:\n{result.stderr.strip()[-1500:]}\n"
                                "If the printed answer looks right, fix the failing test, not the code.")
            if test_issues:
                result = replace(result, ok=False,
                                 stderr=f"{result.stderr}\nTests not run: {' '.join(test_issues)}".strip())
        if best is None or _rank(result) >= _rank(best[1]):
            best = (draft, result)
        if not feedback or result.timed_out:
            break
        messages += [
            {"role": "assistant", "content": f"```python\n{draft.code}\n```\n```python\n{draft.tests}\n```"},
            {"role": "user", "content": "\n".join(feedback) + "\nFix it and reply in the same format."},
        ]
    draft, result = best
    source = (f"{setup}\n# Written by the code model\n{draft.code}"
              + ("\n\n# Tests\n" + draft.tests if draft.tests else ""))
    return S.AnalysisResult(prompt=prompt, code=S.CodeResult(
        source=source, stdout=result.stdout, stderr=result.stderr,
        tests_passed=result.ok and bool(draft.tests), attempts=attempts))
