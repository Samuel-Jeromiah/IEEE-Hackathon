"""Checkpoint 2: safety check on the question only (never the file).

Two layers: narrow regex patterns from policy.yaml (always on), then the optional guard
model on servers.guard. Any guard failure allows the request (policy: on_error=allow).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import httpx

from backend.guard.policy import load_policy

_SAFETY_RE = re.compile(r"Safety:\s*(Safe|Unsafe|Controversial)", re.I)
_CATS_RE = re.compile(r"Categories:\s*(.+)", re.I)


@dataclass
class SafetyResult:
    action: str = "allow"  # allow | decline | support
    reason: str | None = None
    source: str = "none"  # pattern | guard | none


@lru_cache(maxsize=1)
def _patterns() -> tuple[list[re.Pattern], list[re.Pattern]]:
    s = load_policy().safety
    return ([re.compile(p, re.I) for p in s.decline_patterns],
            [re.compile(p, re.I) for p in s.support_patterns])


def check_patterns(question: str | None) -> SafetyResult:
    if not question:
        return SafetyResult()
    decline, support = _patterns()
    if any(p.search(question) for p in support):
        return SafetyResult("support", "self_harm", "pattern")
    if any(p.search(question) for p in decline):
        return SafetyResult("decline", "harmful_request", "pattern")
    return SafetyResult()


def parse_guard_output(text: str) -> tuple[str, list[str]]:
    """Parse Qwen3Guard output: 'Safety: Unsafe\\nCategories: Violent, Jailbreak'."""
    m = _SAFETY_RE.search(text or "")
    label = m.group(1).capitalize() if m else "Safe"
    cats_m = _CATS_RE.search(text or "")
    cats = [c.strip() for c in cats_m.group(1).split(",")] if cats_m else []
    cats = [c for c in cats if c and c.lower() != "none"]
    return label, cats


def decide(label: str, categories: list[str]) -> SafetyResult:
    s = load_policy().safety
    if label != "Unsafe":
        return SafetyResult(source="guard")
    if any(c in s.support for c in categories):
        return SafetyResult("support", "self_harm", "guard")
    if any(c in s.decline for c in categories):
        return SafetyResult("decline", "harmful_request", "guard")
    return SafetyResult(source="guard")


async def classify(question: str | None, guard_url: str | None) -> SafetyResult:
    pat = check_patterns(question)
    if pat.action != "allow" or not question or not guard_url:
        return pat
    pol = load_policy().safety
    body = {
        "messages": [{"role": "user", "content": question}],
        "temperature": 0.0,
        "max_tokens": 32,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        async with httpx.AsyncClient(timeout=pol.timeout_s) as client:
            r = await client.post(f"{guard_url}/chat/completions", json=body)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return SafetyResult()  # on_error: allow
    return decide(*parse_guard_output(text))
