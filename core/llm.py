"""Cached LLM client for the SHEEPWALL gateway (the only LLM provider in this repo).

Chat uses the Anthropic-style /v1/messages endpoint with extended thinking disabled;
embeddings use /v1/embeddings.

deepseek-v4-pro on this gateway has a hard 8192-token *total* output cap (thinking +
content share the same budget). We still send `"thinking": {"type": "disabled"}` on
/v1/messages, but as of 2026-10 the gateway ignores it: every response carries a thinking
block, and thinking eats into max_tokens before any text is written. Callers must
therefore budget for thinking + answer (the agent and summary calls use the full
GATEWAY_MAX_OUTPUT_TOKENS); a small budget yields finish_reason=max_tokens with truncated
or empty text.

Cache key = sha256(model + prompt + temperature + max_tokens). A hit skips the network
call entirely (DESIGN.md 2.5). Retries only apply to the network/HTTP layer, not to
content-level parse failures (those are handled one level up, in stage 2 validation).
"""
import hashlib
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .common import count_tokens, load_config, load_env

load_env()

# The gateway's hard ceiling on output tokens (thinking + text combined). Interactive
# callers (QA agent, entity summaries) use it instead of a tighter per-call budget, since
# the gateway always thinks first and any smaller cap risks a truncated or empty answer.
GATEWAY_MAX_OUTPUT_TOKENS = 8192


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cache_dir: Path, model: str = None):
        cfg = load_config()["llm"]
        self.base_url = os.environ[cfg["base_url_env"]].rstrip("/") + "/"
        self.api_key = os.environ[cfg["api_key_env"]]
        self.model = model or os.environ[cfg["model_env"]]
        self.embedding_model = os.environ[cfg["embedding_model_env"]]
        self.temperature = cfg["temperature"]
        self.max_output_tokens = cfg["max_output_tokens"]
        self.max_retries = cfg["max_retries"]
        self.retry_base_delay_s = cfg["retry_base_delay_s"]
        self.retry_max_delay_s = cfg["retry_max_delay_s"]
        self.timeout_s = cfg["request_timeout_s"]
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _messages_headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _cache_key(self, prompt: str, temperature: float, max_tokens: int, cache_salt: str = None) -> str:
        raw = f"{self.model}|{prompt}|{temperature}|{max_tokens}"
        if cache_salt is not None:
            # Appended only when the caller opts in (e.g. multi-round sampling needs N
            # independent calls against an otherwise-identical (model, prompt,
            # temperature, max_tokens) tuple, which would otherwise collapse onto one
            # cache entry). Omitting it entirely when unset keeps every pre-existing
            # cache key byte-identical -- this must never change the hash for existing
            # callers or it invalidates every cache dir in the repo.
            raw += f"|{cache_salt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _post_with_retry(self, url: str, payload: dict, headers: dict = None,
                         stream: bool = False) -> requests.Response:
        headers = headers or self._headers()
        delay = self.retry_base_delay_s
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_s,
                                     stream=stream)
            except requests.RequestException as e:
                last_exc = e
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                elif resp.status_code >= 400:
                    # Other 4xx (bad/expired key, malformed request, ...) won't succeed on
                    # retry -- fail fast instead of burning the whole ~60s retry budget on
                    # a request that was never going to work.
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                else:
                    return resp
            if attempt == self.max_retries:
                break
            time.sleep(min(delay, self.retry_max_delay_s) + random.uniform(0, 0.5))
            delay *= 2
        raise LLMError(f"request failed after {self.max_retries + 1} attempts: {last_exc}")

    def chat(self, prompt: str, temperature: float = None, max_tokens: int = None,
             cache_salt: str = None, on_text=None, on_thinking=None) -> dict:
        """Returns the cache record dict (see llm_cache/{sha256}.json schema in DESIGN.md 6).

        Calls /v1/messages with thinking disabled (see module docstring).

        cache_salt is mixed into the cache key only -- never sent to the model -- so
        multi-round sampling (same prompt/temperature/max_tokens, called N times to get
        N independent completions) can pass cache_salt=f"round{i}" to force N separate
        network calls instead of N cache hits on the same entry.

        on_text / on_thinking, if given, are called with each chunk of answer text / model
        thinking as it arrives (the request is made with stream=true); on a cache hit they
        get the whole text at once. Streaming doesn't change the cache key or record format.
        """
        temperature = self.temperature if temperature is None else temperature
        max_tokens = self.max_output_tokens if max_tokens is None else max_tokens
        key = self._cache_key(prompt, temperature, max_tokens, cache_salt)
        cache_path = self._cache_path(key)
        if cache_path.exists():
            record = json.loads(cache_path.read_text())
            if on_thinking and record.get("reasoning_content"):
                on_thinking(record["reasoning_content"])
            if on_text and record.get("response_raw"):
                on_text(record["response_raw"])
            return record

        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "temperature": temperature,
                   "max_tokens": max_tokens,
                   "thinking": {"type": "disabled"}}
        t0 = time.time()
        if on_text or on_thinking:
            payload["stream"] = True
            resp = self._post_with_retry(self.base_url + "v1/messages", payload,
                                         headers=self._messages_headers(), stream=True)
            response_text, thinking, finish_reason, usage = _read_message_stream(resp, on_text, on_thinking)
        else:
            resp = self._post_with_retry(self.base_url + "v1/messages", payload,
                                         headers=self._messages_headers())
            data = resp.json()
            blocks = data.get("content", [])
            response_text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            thinking = "".join(b.get("thinking", "") for b in blocks if b.get("type") == "thinking")
            finish_reason = data.get("stop_reason")
            usage = data.get("usage")
        latency_ms = int((time.time() - t0) * 1000)
        record = {
            "cache_key": key,
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_raw": response_text,
            "reasoning_content": thinking or None,
            "finish_reason": finish_reason,
            "usage": usage,
            "latency_ms": latency_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # An empty answer (budget spent on thinking) is never worth replaying: caching it
        # would make every later identical call return the same empty result.
        if response_text.strip():
            cache_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        return record

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.embedding_model, "input": texts}
        resp = self._post_with_retry(self.base_url + "v1/embeddings", payload)
        data = resp.json()
        ordered = sorted(data["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in ordered]


def _read_message_stream(resp: requests.Response, on_text=None,
                         on_thinking=None) -> tuple[str, str, str, dict]:
    """Consumes an Anthropic-style /v1/messages SSE stream, forwarding each text / thinking
    delta to on_text / on_thinking. Returns (text, thinking, stop_reason, usage)."""
    resp.encoding = "utf-8"
    text, thinking = [], []
    stop_reason, usage = None, {}
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            ev = json.loads(raw)
            etype = ev.get("type")
            if etype == "message_start":
                usage.update((ev.get("message") or {}).get("usage") or {})
            elif etype == "content_block_delta":
                delta = ev.get("delta") or {}
                if delta.get("type") == "text_delta":
                    chunk = delta.get("text", "")
                    text.append(chunk)
                    if chunk and on_text:
                        on_text(chunk)
                elif delta.get("type") == "thinking_delta":
                    chunk = delta.get("thinking", "")
                    thinking.append(chunk)
                    if chunk and on_thinking:
                        on_thinking(chunk)
            elif etype == "message_delta":
                stop_reason = (ev.get("delta") or {}).get("stop_reason") or stop_reason
                usage.update(ev.get("usage") or {})
            elif etype == "error":
                raise LLMError(f"stream error: {ev.get('error')}")
    except (requests.RequestException, ValueError) as e:
        raise LLMError(f"stream interrupted: {e}") from e
    finally:
        resp.close()
    return "".join(text), "".join(thinking), stop_reason, usage or None
