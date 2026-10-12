"""Bridges preprocess/simplify.py's output back into a docs.jsonl the extraction
pipeline (stage1_extract.py etc.) can consume, so triples get extracted from the
translated/coreference-resolved text instead of raw OCR text.

Reconstructs the same doc["text"] shape stage0 produces (a "所属疾病：X"/"所属章节：X"
prefix line, verbatim from the source split, + body) so nothing downstream needs
special-casing -- only the body changes, from original_text to simplified_text.

Usage:
    .venv/bin/python scripts/build_simplified_docs.py \
        --dataset TCM --split neike_trial --out neike_trial_simplified
"""
import argparse
import re
import sys
from pathlib import Path

from core.common import read_jsonl, work_dir, write_jsonl

_METADATA_PREFIX_RE = re.compile(r"^所属(?:疾病|章节)[:：].+$")


def original_prefix_line(orig_text: str) -> str | None:
    first = orig_text.split("\n\n", 1)[0].strip()
    return first if _METADATA_PREFIX_RE.match(first) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True, help="source split with simplified.jsonl (preprocess/simplify.py output)")
    ap.add_argument("--out", required=True, help="new split name to write docs.jsonl into")
    args = ap.parse_args()

    src_wd = work_dir(args.dataset, args.split)
    simplified = list(read_jsonl(src_wd / "simplified.jsonl"))
    orig_docs = {d["doc_id"]: d for d in read_jsonl(src_wd / "docs.jsonl")}

    out_wd = work_dir(args.dataset, args.out)
    out_wd.mkdir(parents=True, exist_ok=True)

    rows = []
    skipped = 0
    for r in simplified:
        if not r["simplified_text"]:
            skipped += 1
            continue
        orig = orig_docs.get(r["doc_id"], {})
        prefix = original_prefix_line(orig.get("text", ""))
        text = f"{prefix}\n\n{r['simplified_text']}" if prefix else r["simplified_text"]
        rows.append({
            "doc_id": r["doc_id"],
            "title": r.get("title"),
            "text": text,
            "book": r.get("book"),
            "section": r.get("section"),
            "page_start": orig.get("page_start"),
            "page_end": orig.get("page_end"),
        })

    write_jsonl(out_wd / "docs.jsonl", rows)
    print(f"wrote {len(rows)} docs to {out_wd/'docs.jsonl'} ({skipped} skipped: empty simplified_text)")


if __name__ == "__main__":
    main()
