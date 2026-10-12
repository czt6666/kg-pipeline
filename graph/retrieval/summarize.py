"""Turns present.py's bullet-point structured facts into a few paragraphs of plain-language
Chinese, via a small/fast model (deepseek-v4-flash on the SHEEPWALL gateway) rather than the
larger extraction-pipeline model -- this is a cheap on-the-fly rewrite of already-retrieved
facts, not a reasoning task, so it doesn't need the bigger model's budget or latency.

Disk-cached the same way as every other LLMClient call (key includes model, so this never
collides with the main model's cache entries even though it shares llm_cache/).
"""
from __future__ import annotations

from core.llm import LLMClient, LLMError
from prompting import PromptStore

SUMMARY_MODEL = "deepseek-v4-flash"
PROMPT_TEMPLATE = PromptStore().retrieval_summary().read_text("template")


def summarize_facts(client: LLMClient, seed: dict, facts: list[dict]) -> str | None:
    """seed={entity_id,name,type}; facts = present_result()'s facts list. Returns the
    summary text, or None if there are no facts to summarize or the call fails (caller
    should fall back to the template-rendered `text` field, never crash retrieval over a
    summarization hiccup)."""
    if not facts:
        return None
    facts_block = "\n".join(f"- {f['sentence']}" for f in facts)
    prompt = PROMPT_TEMPLATE.format(name=seed["name"], type=seed["type"], facts_block=facts_block)
    try:
        record = client.chat(prompt, temperature=0.3, max_tokens=4096)
    except LLMError:
        return None
    text = (record.get("response_raw") or "").strip()
    return text or None
