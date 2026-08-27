"""Stage 0: convert data/raw/docred/dev.json into data/work/docred/dev/docs.jsonl.

Text is the raw space-joined DocRED tokenization (same convention as
build_docred_fewshot.py), so mention strings extracted by the LLM remain exact
substrings of `text` and Stage 2.6 exact-match alignment works without a detokenization
mismatch. Chunking (DESIGN.md 2.1) is a fallback only: DocRED docs are far under
max_input_tokens so `chunks` is null for every row here.
"""
import argparse
import json
from pathlib import Path

from common import REPO_ROOT, count_tokens, load_config, work_dir, write_jsonl

RAW_PATH = REPO_ROOT / "data/raw/docred/dev.json"


def doc_text(doc) -> str:
    return " ".join(w for s in doc["sents"] for w in s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only take first N docs (for smoke tests)")
    args = ap.parse_args()

    cfg = load_config()
    max_input_tokens = cfg["extraction"]["max_input_tokens"]

    docs = json.loads(RAW_PATH.read_text())
    if args.limit:
        docs = docs[: args.limit]

    rows = []
    for i, doc in enumerate(docs):
        text = doc_text(doc)
        n_tokens = count_tokens(text)
        rows.append(
            {
                "doc_id": f"docred_dev_{i:04d}",
                "title": doc["title"],
                "text": text,
                "n_tokens": n_tokens,
                "chunks": None if n_tokens <= max_input_tokens else "TODO_CHUNKING_NOT_NEEDED_YET",
            }
        )

    out_dir = work_dir("docred", "dev")
    write_jsonl(out_dir / "docs.jsonl", rows)
    over_budget = [r for r in rows if r["chunks"] is not None]
    print(f"wrote {len(rows)} docs to {out_dir/'docs.jsonl'}")
    print(f"docs over max_input_tokens ({max_input_tokens}): {len(over_budget)}")
    print(f"token stats: min={min(r['n_tokens'] for r in rows)} max={max(r['n_tokens'] for r in rows)} "
          f"mean={sum(r['n_tokens'] for r in rows)/len(rows):.1f}")


if __name__ == "__main__":
    main()
