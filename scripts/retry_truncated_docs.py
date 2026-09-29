"""Round 2 fix: re-run stage1 extraction with a bigger max_tokens budget for every doc whose
extraction_raw.jsonl parse_status is not a clean "ok" (i.e. "failed", "repaired", or "retried").

Root cause (see PROGRESS.md Round 2 notes): config.yaml's max_output_tokens=4096 is too small
for some 证治分类 docs with many 证型 sub-blocks -- the LLM's JSON response gets cut off
mid-string, and either fails to parse entirely ("failed") or gets patched by json_repair in a
way that silently drops whatever was after the cut point ("repaired"/"retried" can both still
be lossy, since repair just closes unterminated structures rather than recovering the lost
tail). Bumping max_tokens for just the affected docs (not globally -- LLMClient's cache key
includes max_tokens, so a global bump would invalidate and re-pay for the entire ~1150-doc
corpus) gives the model room to finish and removes the whole failure class at once.

Usage: .venv/bin/python scripts/retry_truncated_docs.py --split neike_v2_retrybudget --max-tokens 8192
Rewrites {split}/extraction_raw.jsonl in place (only rows for retried doc_ids change).
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common import read_jsonl, work_dir, write_jsonl  # noqa: E402
from llm_client import LLMClient  # noqa: E402
from stage1_extract import try_parse  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True)
    ap.add_argument("--prompt", default="prompts/tcm_prompt_template_v2_pro.txt")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    template = open(ROOT / args.prompt, encoding="utf-8").read()
    docs_by_id = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
    raw_rows = list(read_jsonl(wd / "extraction_raw.jsonl"))

    to_retry = [r for r in raw_rows if r.get("parse_status") != "ok"]
    print(f"{len(to_retry)} / {len(raw_rows)} docs need a retry (parse_status != 'ok')")

    client = LLMClient(wd / "llm_cache")

    def process(row):
        doc_id = row["doc_id"]
        doc = docs_by_id.get(doc_id)
        if doc is None:
            return doc_id, None, "no_doc"
        prompt = template.replace("{TEXT}", doc["text"])
        record = client.chat(prompt, max_tokens=args.max_tokens)
        parsed, status, err = try_parse(record["response_raw"])
        old_n = len((row.get("parsed") or {}).get("triples", []))
        new_n = len((parsed or {}).get("triples", []))
        if parsed is not None and new_n >= old_n:
            result = {
                "doc_id": doc_id,
                "chunk_id": row.get("chunk_id"),
                "cache_key": record["cache_key"],
                "parse_status": status,
                "parsed": parsed,
                "error": err,
            }
            return doc_id, result, ("improved" if new_n > old_n else "same_count")
        elif parsed is not None:
            print(f"  {doc_id}: retry produced FEWER triples ({new_n} < {old_n}), keeping original")
            return doc_id, None, "regressed_kept_old"
        else:
            print(f"  {doc_id}: still failed to parse ({err})")
            return doc_id, None, "still_failed"

    results_by_doc = {}
    n_improved = n_same_or_worse = n_still_failed = n_regressed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process, row) for row in to_retry]
        for fut in as_completed(futures):
            doc_id, result, tag = fut.result()
            if result is not None:
                results_by_doc[doc_id] = result
            if tag == "improved":
                n_improved += 1
            elif tag == "same_count":
                n_same_or_worse += 1
            elif tag == "regressed_kept_old":
                n_regressed += 1
            else:
                n_still_failed += 1

    out_rows = [results_by_doc.get(r["doc_id"], r) for r in raw_rows]
    write_jsonl(wd / "extraction_raw.jsonl", out_rows)

    print(f"improved (more triples): {n_improved}")
    print(f"same triple count (took new): {n_same_or_worse}")
    print(f"regressed (kept old, new had fewer triples): {n_regressed}")
    print(f"still failed after retry: {n_still_failed}")


if __name__ == "__main__":
    main()
