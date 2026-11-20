"""Checkpoint 1: input gate. Pure functions, no model calls."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.guard.policy import load_policy

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class GateResult:
    ok: bool
    question: str | None = None  # cleaned question, or the per-kind default when empty
    text: str | None = None  # cleaned pasted text
    reason: str | None = None
    message: str | None = None


def clean(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    return _CONTROL.sub("", s).strip()


def check_request(
    *,
    kind: str,
    prompt: str | None,
    text: str | None,
    file_sizes: list[int] | None = None,
) -> GateResult:
    """Validate sizes and lengths; fill the default task when the question is empty."""
    pol = load_policy()
    lim = pol.limits
    question = clean(prompt)
    body = clean(text)

    for size in file_sizes or []:
        if size > lim.file_mb * 1024 * 1024:
            return GateResult(False, reason="file_too_large",
                              message=f"That file is larger than {lim.file_mb:g} MB. Try a shorter or smaller one.")

    q_limit = lim.code_prompt_chars if kind == "code" else lim.question_chars
    if len(question) > q_limit:
        return GateResult(False, reason="question_too_long",
                          message=f"That question is over {q_limit:,} characters. Please shorten it.")
    if len(body) > lim.pasted_text_chars:
        return GateResult(False, reason="text_too_long",
                          message=f"The pasted text is over {lim.pasted_text_chars:,} characters. Upload it as a file instead.")

    if kind == "code" and not (question or body):
        return GateResult(False, reason="empty_code_prompt",
                          message="Describe the code you want, for example: a function that checks for palindromes.")
    if not question and kind in pol.defaults and kind not in {"text", "code"}:
        question = pol.defaults[kind]
    return GateResult(True, question=question or None, text=body or None)
