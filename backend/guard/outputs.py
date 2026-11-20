"""Checkpoint 4: output check. Same short format and the same abstain sentence every time."""
from __future__ import annotations

import re

from backend import schemas as S
from backend.guard.policy import load_policy

_THINK = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
# Variants models use to say "I don't know"; only matched when they open the answer.
# "I can't see any dogs" or "The photo doesn't show people" are real answers, so they don't match.
_ABSTAIN = re.compile(
    r"^\s*(i\s+(cannot|can't|can not|am unable to|am not able to|couldn't|could not)\s+"
    r"(determine|tell|answer|say|know)\b|"
    r"(it is|it's)\s+(not possible|impossible|unclear)\s+to\s+(tell|determine|say)\b|"
    r"(can't|cannot)\s+tell\b|there is not enough information|not enough information)",
    re.I,
)
_NUMBER_WORDS = {
    "zero": 0, "no": 0, "none": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_COUNT_Q = re.compile(r"^\s*how many\b", re.I)


def strip_thinking(text: str) -> str:
    return _THINK.sub("", text).strip()


def cap_sentences(text: str, n: int) -> str:
    if n <= 0 or "\n" in text.strip() or "```" in text:
        return text  # lists, code and transcripts keep their shape
    parts = _SENTENCE.split(text.strip())
    return " ".join(parts[:n]) if len(parts) > n else text.strip()


def number_words_to_digits(text: str) -> str:
    """For counting questions: 'There are three dogs.' -> 'There are 3 dogs.'"""
    def sub(m: re.Match) -> str:
        word = m.group(0)
        val = _NUMBER_WORDS[word.lower()]
        return str(val)
    pattern = r"\b(" + "|".join(k for k in _NUMBER_WORDS if k not in {"no", "none"}) + r")\b"
    return re.sub(pattern, sub, text, count=1, flags=re.I)


def is_abstain(text: str) -> bool:
    return bool(_ABSTAIN.search(text))


def finalize(task: str, raw: str | None, question: str | None = None) -> tuple[str | None, S.PolicyNote]:
    """Clean one answer and say whether it answered or abstained."""
    pol = load_policy()
    if raw is None:
        return None, S.PolicyNote()
    text = strip_thinking(raw)
    if not text or is_abstain(text):
        msg = pol.abstain(task)
        return msg, S.PolicyNote(action="abstained",
                                 reason="not_in_document" if task == "document" else "cant_tell",
                                 message=msg)
    if task == "document" and text == pol.abstain("document"):
        return text, S.PolicyNote(action="abstained", reason="not_in_document", message=text)
    if question and _COUNT_Q.search(question):
        text = number_words_to_digits(text)
    text = cap_sentences(text, pol.answer.max_sentences.get(task, 0))
    return text, S.PolicyNote()
