"""Code worker: coder model writes a function and its own tests → sandbox → one repair.

The reply uses two fenced blocks, not JSON: small coder models end JSON strings early when
the code itself contains quotes, which truncates the tests.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

import httpx

from backend import schemas as S
from backend.clients import llm
from backend.guard.policy import load_policy
from backend.sandbox import runner

SYSTEM = (
    "You write correct, self-contained Python 3.12 using only the standard library "
    "(plus pandas, csv and io.StringIO when the task is about tables). Reply with three parts "
    "in this order: (1) one or two plain sentences explaining the approach; (2) a ```python block "
    "with the complete code, definitions only, with no example usage, input(), files or network; "
    "(3) a second ```python block with 3 to 6 assert statements that call the code. Work out each "
    "expected value carefully. If the request gives a function signature, keep it exactly."
)

_DATA_HINT = re.compile(r"\b(csv|pandas|dataframe|spreadsheet|table|columns?)\b", re.I)
_BLOCK = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\n(.*?)```", re.S | re.I)
_NUMBERING = re.compile(r"^\s*(\(?\d\)|\d\.)\s*")


@dataclass
class Draft:
    explanation: str
    code: str
    tests: str


def _clean_explanation(text: str) -> str:
    para = next((p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()), "")
    para = _NUMBERING.sub("", para).strip()
    if para.endswith(":"):
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", para)
    return " ".join(sentences[:2]).strip()


def add_missing_imports(code: str, allowed: set[str]) -> str:
    """Small models often use math./re./io. without importing them."""
    imported = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_]\w*)", code, re.M))
    aliases = {"pd": "pandas", "np": "numpy"}
    needed = []
    for name in sorted(set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\.", code))):
        module = aliases.get(name, name)
        if module in allowed and module not in imported and not re.search(
                rf"^\s*(def|class)\s+{name}\b|^\s*{name}\s*=", code, re.M):
            needed.append(f"import {module} as {name}" if name in aliases else f"import {module}")
    return "\n".join(needed + [code]) if needed else code


def parse_reply(raw: str) -> Draft:
    blocks = [b.strip() for b in _BLOCK.findall(raw or "")]
    first = (raw or "").find("```")
    explanation = _clean_explanation(raw[:first] if first >= 0 else "")
    if not blocks:  # no fences: treat the whole reply as code
        return Draft("", (raw or "").strip(), "")
    code = blocks[0]
    tests = "\n".join(blocks[1:]) if len(blocks) > 1 else ""
    if not tests:  # asserts appended to the code block
        lines = code.splitlines()
        cut = next((i for i, ln in enumerate(lines) if ln.startswith("assert ")), None)
        if cut is not None:
            code, tests = "\n".join(lines[:cut]).rstrip(), "\n".join(lines[cut:])
    return Draft(explanation, code, tests)


async def ask(messages: list[dict], timeout_s: float) -> tuple[Draft, str]:
    """Prefer the coder server; fall back to the VLM when the coder isn't resident."""
    max_tokens = load_policy().max_tokens("code")
    try:
        raw = await llm.chat("coder", messages, temperature=0.0, max_tokens=max_tokens, timeout_s=timeout_s)
        used = "coder"
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raw = await llm.chat("vlm", messages, temperature=0.0, max_tokens=max_tokens, timeout_s=timeout_s)
        used = "vlm"
    draft = parse_reply(raw)
    draft.code = add_missing_imports(draft.code, runner.allowed_modules("data"))
    return draft, used


async def run(prompt: str, *, model_name: str, timeout_s: float, on_delta=None) -> S.ArtifactResult:
    t0 = time.perf_counter()
    profile = "data" if _DATA_HINT.search(prompt) else "pure"
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        draft, used = await ask(messages, timeout_s)
        result = await asyncio.to_thread(runner.run_python, draft.code, draft.tests, profile=profile)
        attempts = 1
        if not result.ok and not result.timed_out:
            attempts = 2
            messages += [
                {"role": "assistant", "content": (
                    f"{draft.explanation}\n```python\n{draft.code}\n```\n```python\n{draft.tests}\n```"
                )},
                {"role": "user", "content": (
                    "Running the code with the tests failed:\n"
                    f"{(result.stderr or result.stdout)[-2000:]}\n"
                    "Fix whichever is wrong, the code or a test. Keep the same function names "
                    "and reply in the same format."
                )},
            ]
            draft2, used = await ask(messages, timeout_s)
            result2 = await asyncio.to_thread(runner.run_python, draft2.code, draft2.tests, profile=profile)
            if result2.ok or not draft.code:
                # the repair reply explains the fix, not the code, so keep the first explanation
                draft2.explanation = draft.explanation or draft2.explanation
                draft, result = draft2, result2

        explanation = draft.explanation or ("Here's the code." if draft.code else "")
        if result.ok and draft.tests:
            explanation = f"{explanation} It passed its own tests in the sandbox.".strip()
        if result.blocked:
            explanation = (f"{explanation} The code wasn't run because it uses something the "
                           f"sandbox doesn't allow ({result.blocked}).").strip()
        elif not result.ok:
            explanation = f"{explanation} Its own tests didn't pass, so check it before using it.".strip()
        if on_delta:
            on_delta(explanation)
        source = draft.code + ("\n\n# Tests\n" + draft.tests if draft.tests else "")
        return S.ArtifactResult(
            artifact_id="a_code", kind="code", answer=explanation or None,
            code=S.CodeResult(source=source, stdout=result.stdout, stderr=result.stderr,
                              tests_passed=result.ok, attempts=attempts),
            model=model_name if used == "coder" else f"{model_name} (fallback: vlm)",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            status="ok" if draft.code else "degraded",
        )
    except Exception as exc:  # noqa: BLE001
        return S.ArtifactResult(
            artifact_id="a_code", kind="code", answer=None, model=model_name,
            latency_ms=int((time.perf_counter() - t0) * 1000), status="failed",
            error=str(exc)[:500],
        )
