"""Reasoner: the thin, replaceable boundary between the agent loop and the LLM.

Every stage calls `reasoner.think(prompt, tag=...)` for a structured JSON judgement or
`reasoner.write(prompt, tag=...)` for prose (final answer / follow-up question). The loop
depends only on this interface, so tests inject `ScriptedReasoner` (canned per-tag outputs,
no network) and the whole loop runs deterministically offline.

`LLMReasoner` wraps the existing LLMClient (same gateway, same disk cache). JSON parsing is
tolerant of ```json fences and surrounding prose, with exactly one stricter repair retry
against a fresh cache key before giving up.
"""
from __future__ import annotations

import json
import re

from llm_client import LLMClient


class AgentError(RuntimeError):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Best-effort parse: whole string, then fenced block, then first {...last }."""
    text = (text or "").strip()
    if not text:
        raise AgentError("empty model output")
    for candidate in _json_candidates(text):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise AgentError(f"no JSON object found in model output: {text[:200]!r}")


def _json_candidates(text: str):
    yield text
    m = _FENCE_RE.search(text)
    if m:
        yield m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        yield text[start : end + 1]


class LLMReasoner:
    def __init__(self, client: LLMClient, answer_client: LLMClient | None = None):
        self.client = client
        # Prose answers can use a lighter/warmer model if the caller supplies one; defaults
        # to the same decision client so a single LLMClient is enough to run the agent.
        self.answer_client = answer_client or client

    def think(self, prompt: str, tag: str = "", temperature: float = 0.0,
              max_tokens: int = 1024) -> dict:
        raw = self.client.chat(prompt, temperature=temperature, max_tokens=max_tokens)
        text = raw.get("response_raw") or ""
        try:
            return extract_json(text)
        except AgentError:
            strict = prompt + "\n\n重要：只输出一个合法的 JSON 对象，不要任何解释、前后缀或代码块标记。"
            raw2 = self.client.chat(strict, temperature=temperature, max_tokens=max_tokens)
            return extract_json(raw2.get("response_raw") or "")

    def write(self, prompt: str, tag: str = "", temperature: float = 0.3,
              max_tokens: int = 1200) -> str:
        raw = self.answer_client.chat(prompt, temperature=temperature, max_tokens=max_tokens)
        return (raw.get("response_raw") or "").strip()


class ScriptedReasoner:
    """Test double. `script` maps a stage tag -> either a single response or a list of
    responses consumed in order (for stages called multiple times, e.g. decide across
    retrieval rounds). think() returns dicts; write() returns strings. Raises if a tag is
    requested with no script left, so tests fail loudly on an unexpected extra LLM call."""

    def __init__(self, script: dict):
        self._script = {k: (list(v) if isinstance(v, list) else [v]) for k, v in script.items()}
        self.calls: list[tuple[str, str]] = []  # (tag, prompt) for assertions

    def _pop(self, tag: str):
        queue = self._script.get(tag)
        if not queue:
            raise AgentError(f"ScriptedReasoner: no scripted response for tag '{tag}'")
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def think(self, prompt: str, tag: str = "", **_) -> dict:
        self.calls.append((tag, prompt))
        return self._pop(tag)

    def write(self, prompt: str, tag: str = "", **_) -> str:
        self.calls.append((tag, prompt))
        return self._pop(tag)
