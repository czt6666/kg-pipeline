"""Turns present.py's bullet-point structured facts into a few paragraphs of plain-language
Chinese, via a small/fast model (deepseek-v4-flash on the SHEEPWALL gateway) rather than the
larger extraction-pipeline model -- this is a cheap on-the-fly rewrite of already-retrieved
facts, not a reasoning task, so it doesn't need the bigger model's budget or latency.

Disk-cached the same way as every other LLMClient call (key includes model, so this never
collides with the main model's cache entries even though it shares llm_cache/).
"""
from __future__ import annotations

from llm_client import LLMClient, LLMError

SUMMARY_MODEL = "deepseek-v4-flash"

PROMPT_TEMPLATE = """你是中医知识科普助手。下面是关于「{name}」（{type}）的结构化事实，均来自教材抽取的知识图谱，逐条列出、无先后逻辑：

{facts_block}

请只根据以上事实，用通顺的大白话写成2-3段自然段，面向没有中医背景的读者：说清楚这是什么、常见分型/表现、病因（如果有），最后专门用一段说明治疗方法（治法/方剂/用药，如果事实里没有治疗相关信息，就明确说"以上事实未提及具体治疗方法"，不要编造）。不要逐条翻译，不要输出列表或标题，不要添加事实之外的信息，全文使用中文，不要夹杂英文单词。"""


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
        record = client.chat(prompt, temperature=0.3, max_tokens=768)
    except LLMError:
        return None
    text = (record.get("response_raw") or "").strip()
    return text or None
