"""Load backend/guard/policy.yaml into a cached, typed object."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

POLICY_PATH = Path(__file__).with_name("policy.yaml")


class Limits(BaseModel):
    question_chars: int
    code_prompt_chars: int
    pasted_text_chars: int
    file_mb: float


class Answer(BaseModel):
    max_sentences: dict[str, int]
    max_tokens: dict[str, int]
    temperature: dict[str, float]


class Messages(BaseModel):
    abstain: dict[str, str]
    declined: str
    support: str


class Untrusted(BaseModel):
    delimit: bool = True


class Safety(BaseModel):
    decline: list[str]
    support: list[str]
    timeout_s: float
    on_error: str = "allow"
    decline_patterns: list[str] = []
    support_patterns: list[str] = []


class Sandbox(BaseModel):
    timeout_s: float
    output_bytes: int
    pure_modules: list[str]
    data_modules: list[str]
    blocked_names: list[str]
    blocked_attrs: list[str] = []


class Policy(BaseModel):
    limits: Limits
    defaults: dict[str, str]
    answer: Answer
    messages: Messages
    untrusted_text: Untrusted
    safety: Safety
    sandbox: Sandbox

    def abstain(self, task: str) -> str:
        return self.messages.abstain.get(task, self.messages.abstain["text"])

    def max_tokens(self, task: str) -> int:
        return self.answer.max_tokens.get(task, self.answer.max_tokens["text"])


@lru_cache(maxsize=1)
def load_policy() -> Policy:
    return Policy.model_validate(yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")))
