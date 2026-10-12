"""Stage 1: run LLM extraction over docs.jsonl, cache responses, parse to extraction_raw.jsonl.

Parse fallback order: json.loads -> json_repair -> one retry with the parse error
appended to the prompt -> mark failed.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import json_repair
from tqdm import tqdm

from core.common import read_jsonl, work_dir, write_jsonl
from core.llm import LLMClient
from prompting import PromptStore, write_prompt_lock


def try_parse(raw_text: str):
    """Returns (parsed, method, err) where method is 'ok' or 'repaired' on success."""
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return None, None, "empty_response"
    try:
        return json.loads(raw_text), "ok", None
    except json.JSONDecodeError as e:
        try:
            repaired = json_repair.loads(raw_text)
            if isinstance(repaired, dict) and "entities" in repaired and "triples" in repaired:
                return repaired, "repaired", None
            return None, None, f"repair_missing_keys: {e}"
        except Exception as e2:
            return None, None, f"json_repair_failed: {e2}"


def extract_one(client: LLMClient, prompt: str, max_tokens: int = None, temperature: float = None,
                cache_salt: str = None):
    record = client.chat(prompt, max_tokens=max_tokens, temperature=temperature, cache_salt=cache_salt)
    parsed, method, err = try_parse(record["response_raw"])
    if parsed is not None:
        return record, parsed, method, None

    retry_prompt = (
        prompt
        + f"\n\n上一次的输出无法解析为 JSON（错误：{err}）。请只输出严格合法的 JSON，不要任何解释或代码围栏，重新生成。"
    )
    record2 = client.chat(retry_prompt, max_tokens=max_tokens, temperature=temperature, cache_salt=cache_salt)
    parsed2, method2, err2 = try_parse(record2["response_raw"])
    if parsed2 is not None:
        return record2, parsed2, "retried", None
    return record2, None, "failed", err2 or err


def _load_template(dataset: str, override: str | None):
    if override:
        path = Path(override)
        return path.read_text(encoding="utf-8"), [{"key": "override", "version": "manual", "asset": "template", "path": str(path), "sha256": "manual"}], str(path)
    asset = PromptStore().extraction(dataset)
    return asset.read_text("template"), [asset.lock_record("template"), asset.lock_record("fewshot")], f"{asset.key}@{asset.version}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=12, help="concurrent LLM requests")
    ap.add_argument("--prompt", default=None,
                    help="override prompt template path; otherwise use the central prompt registry")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="override max_output_tokens for this run only")
    ap.add_argument("--temperature", type=float, default=None,
                    help="override config.yaml's llm.temperature for this run only")
    ap.add_argument("--cache-salt", default=None,
                    help="mixed into the LLM cache key only; useful for multi-round sampling")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    template, prompt_locks, prompt_desc = _load_template(args.dataset, args.prompt)
    docs = list(read_jsonl(wd / "docs.jsonl"))
    if args.limit:
        docs = docs[: args.limit]
    print(f"using prompt template: {prompt_desc}")
    write_prompt_lock(wd / "prompt_lock.json", prompt_locks)

    client = LLMClient(wd / "llm_cache")

    def process(doc):
        prompt = template.replace("{TEXT}", doc["text"])
        record, parsed, status, err = extract_one(
            client, prompt, max_tokens=args.max_tokens,
            temperature=args.temperature, cache_salt=args.cache_salt,
        )
        return {
            "doc_id": doc["doc_id"],
            "chunk_id": None,
            "cache_key": record["cache_key"],
            "parse_status": status,
            "parsed": parsed,
            "error": err,
        }

    rows_by_doc_id = {}
    status_counts = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process, doc): doc["doc_id"] for doc in docs}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="extracting"):
            row = fut.result()
            rows_by_doc_id[row["doc_id"]] = row
            status_counts[row["parse_status"]] = status_counts.get(row["parse_status"], 0) + 1

    rows = [rows_by_doc_id[doc["doc_id"]] for doc in docs]
    write_jsonl(wd / "extraction_raw.jsonl", rows)
    print(f"wrote {len(rows)} rows to {wd/'extraction_raw.jsonl'}")
    print(f"status counts: {status_counts}")


if __name__ == "__main__":
    main()
