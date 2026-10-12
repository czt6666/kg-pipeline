"""Cached LLM client for the SHEEPWALL gateway and OpenAI question answering.

Gateway chat uses the Anthropic-style /v1/messages endpoint with extended thinking
disabled; OpenAI chat uses /v1/chat/completions. Both providers support embeddings.

deepseek-v4-pro on this gateway has a hard 8192-token *total* output cap (thinking +
content share the same budget) via the OpenAI-compatible /v1/chat/completions endpoint,
and for our extraction prompts it reliably spends the entire budget on reasoning_content,
leaving zero room for the actual JSON answer (finish_reason=length, content=""). Passing
`"thinking": {"type": "disabled"}` on /v1/messages removes the reasoning pass entirely,
so max_tokens covers only the JSON answer -- verified empirically (see session notes) to
finish in single-digit seconds with well-formed output. Gateway chat therefore uses
/v1/messages.

Gateway cache key = sha256(model + prompt + temperature + max_tokens); OpenAI keys also
include the provider. A hit skips the network
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


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cache_dir: Path, model: str = None, provider: str = "gateway"):
        config = load_config()
        cfg = config["llm"]
        if provider == "openai":
            qa_cfg = config["qa"]
            self.base_url = qa_cfg["base_url"].rstrip("/") + "/"
            self.api_key = os.environ[qa_cfg["api_key_env"]]
            self.model = model or qa_cfg["model"]
            self.embedding_model = qa_cfg["embedding_model"]
        elif provider == "gateway":
            self.base_url = os.environ[cfg["base_url_env"]].rstrip("/") + "/"
            self.api_key = os.environ[cfg["api_key_env"]]
            self.model = model or os.environ[cfg["model_env"]]
            self.embedding_model = os.environ[cfg["embedding_model_env"]]
        else:
            raise ValueError(f"unknown LLM provider: {provider}")
        self.provider = provider
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
        if self.provider == "openai":
            raw = "openai|" + raw
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

    def _post_with_retry(self, url: str, payload: dict, headers: dict = None) -> requests.Response:
        headers = headers or self._headers()
        delay = self.retry_base_delay_s
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_s)
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
             cache_salt: str = None) -> dict:
        """Returns the cache record dict (see llm_cache/{sha256}.json schema in DESIGN.md 6).

        OpenAI calls use Chat Completions; gateway calls use /v1/messages with
        thinking disabled (see module docstring).

        cache_salt is mixed into the cache key only -- never sent to the model -- so
        multi-round sampling (same prompt/temperature/max_tokens, called N times to get
        N independent completions) can pass cache_salt=f"round{i}" to force N separate
        network calls instead of N cache hits on the same entry.
        """
        temperature = self.temperature if temperature is None else temperature
        max_tokens = self.max_output_tokens if max_tokens is None else max_tokens
        key = self._cache_key(prompt, temperature, max_tokens, cache_salt)
        cache_path = self._cache_path(key)
        if cache_path.exists():
            return json.loads(cache_path.read_text())

        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "temperature": temperature}
        if self.provider == "openai":
            payload["max_completion_tokens"] = max_tokens
            url = self.base_url + "v1/chat/completions"
            headers = self._headers()
        else:
            payload["max_tokens"] = max_tokens
            payload["thinking"] = {"type": "disabled"}
            url = self.base_url + "v1/messages"
            headers = self._messages_headers()
        t0 = time.time()
        resp = self._post_with_retry(url, payload, headers=headers)
        latency_ms = int((time.time() - t0) * 1000)
        data = resp.json()
        if self.provider == "openai":
            choice = data["choices"][0]
            response_text = choice["message"].get("content") or ""
            thinking = None
            finish_reason = choice.get("finish_reason")
        else:
            response_text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            thinking = "".join(b.get("thinking", "") for b in data.get("content", []) if b.get("type") == "thinking")
            finish_reason = data.get("stop_reason")
        record = {
            "cache_key": key,
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_raw": response_text,
            "reasoning_content": thinking or None,
            "finish_reason": finish_reason,
            "usage": data.get("usage"),
            "latency_ms": latency_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        cache_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        return record

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.embedding_model, "input": texts}
        resp = self._post_with_retry(self.base_url + "v1/embeddings", payload)
        data = resp.json()
        ordered = sorted(data["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in ordered]
