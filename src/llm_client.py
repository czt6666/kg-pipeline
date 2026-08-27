"""SHEEPWALL gateway client: chat via the Anthropic-style /v1/messages endpoint with
extended thinking explicitly disabled, plus OpenAI-style /v1/embeddings.

deepseek-v4-pro on this gateway has a hard 8192-token *total* output cap (thinking +
content share the same budget) via the OpenAI-compatible /v1/chat/completions endpoint,
and for our extraction prompts it reliably spends the entire budget on reasoning_content,
leaving zero room for the actual JSON answer (finish_reason=length, content=""). Passing
`"thinking": {"type": "disabled"}` on /v1/messages removes the reasoning pass entirely,
so max_tokens covers only the JSON answer -- verified empirically (see session notes) to
finish in single-digit seconds with well-formed output. This is why chat() below targets
/v1/messages rather than /v1/chat/completions.

Cache key = sha256(model + prompt + temperature + max_tokens); a hit skips the network
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

from common import count_tokens, load_config, load_env

load_env()


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cache_dir: Path):
        cfg = load_config()["llm"]
        self.base_url = os.environ[cfg["base_url_env"]].rstrip("/") + "/"
        self.api_key = os.environ[cfg["api_key_env"]]
        self.model = os.environ[cfg["model_env"]]
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

    def _cache_key(self, prompt: str, temperature: float, max_tokens: int) -> str:
        raw = f"{self.model}|{prompt}|{temperature}|{max_tokens}"
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
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                resp.raise_for_status()
                return resp
            except (requests.RequestException, LLMError) as e:
                last_exc = e
                if attempt == self.max_retries:
                    break
                time.sleep(min(delay, self.retry_max_delay_s) + random.uniform(0, 0.5))
                delay *= 2
        raise LLMError(f"request failed after {self.max_retries + 1} attempts: {last_exc}")

    def chat(self, prompt: str, temperature: float = None, max_tokens: int = None) -> dict:
        """Returns the cache record dict (see llm_cache/{sha256}.json schema in DESIGN.md 6).

        Uses /v1/messages with thinking disabled (see module docstring) -- max_tokens here
        bounds only the answer, not a reasoning pass.
        """
        temperature = self.temperature if temperature is None else temperature
        max_tokens = self.max_output_tokens if max_tokens is None else max_tokens
        key = self._cache_key(prompt, temperature, max_tokens)
        cache_path = self._cache_path(key)
        if cache_path.exists():
            return json.loads(cache_path.read_text())

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},
        }
        t0 = time.time()
        resp = self._post_with_retry(
            self.base_url + "v1/messages", payload, headers=self._messages_headers()
        )
        latency_ms = int((time.time() - t0) * 1000)
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        thinking = "".join(b.get("thinking", "") for b in data.get("content", []) if b.get("type") == "thinking")
        record = {
            "cache_key": key,
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_raw": text,
            "reasoning_content": thinking or None,
            "finish_reason": data.get("stop_reason"),
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
