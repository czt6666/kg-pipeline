"""Stage 0: build the docred/eval200 split -- the exact 200-doc DocRED sample used by
the official GenRES repo (github.com/pat-jj/GenRES), which GraphRefine's own appendix
says it reuses verbatim ("For any aspects not specified in our paper, we follow the
original implementation"). Using this specific sample maximizes comparability with the
paper's reported numbers instead of an arbitrary subset of DocRED dev.

docs.jsonl here uses OUR OWN text convention (raw space-joined DocRED tokens, see
build_docred_docs.py) for consistency with our own extraction/alignment pipeline --
identity with the GenRES sample is established by whitespace-insensitive text matching,
not by byte-identical strings. gold.jsonl carries the GenRES reference triples,
reordered from their [head, tail, relation] convention to our [head, relation, tail].
"""
import argparse
import json
import re
from pathlib import Path

from common import REPO_ROOT, count_tokens, load_config, work_dir, write_jsonl

DEV_PATH = REPO_ROOT / "data/raw/docred/dev.json"
GENRES_PATH = REPO_ROOT / "data/raw/genres_reference/docred_rand_200.json"


def doc_text(doc) -> str:
    return " ".join(w for s in doc["sents"] for w in s)


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def main():
    ap = argparse.ArgumentParser()
    args = ap.parse_args()

    cfg = load_config()
    max_input_tokens = cfg["extraction"]["max_input_tokens"]

    dev = json.loads(DEV_PATH.read_text())
    genres = json.loads(GENRES_PATH.read_text())

    dev_by_norm = {normalize_ws(doc_text(d)): d for d in dev}

    doc_rows = []
    gold_rows = []
    unmatched = 0
    for genres_text, genres_triples in genres.items():
        key = normalize_ws(genres_text)
        dev_doc = dev_by_norm.get(key)
        if dev_doc is None:
            unmatched += 1
            continue
        doc_id = f"docred_eval200_{len(doc_rows):04d}"
        text = doc_text(dev_doc)
        n_tokens = count_tokens(text)
        doc_rows.append(
            {
                "doc_id": doc_id,
                "title": dev_doc["title"],
                "text": text,
                "n_tokens": n_tokens,
                "chunks": None if n_tokens <= max_input_tokens else "TODO_CHUNKING_NOT_NEEDED_YET",
            }
        )
        # GenRES convention is [head, tail, relation]; normalize to [head, relation, tail]
        triples = [{"head": t[0], "relation": t[2], "tail": t[1]} for t in genres_triples]
        gold_rows.append({"doc_id": doc_id, "triples": triples})

    if unmatched:
        raise RuntimeError(f"{unmatched}/{len(genres)} GenRES docs failed to match against dev.json")

    out_dir = work_dir("docred", "eval200")
    write_jsonl(out_dir / "docs.jsonl", doc_rows)
    write_jsonl(out_dir / "gold.jsonl", gold_rows)
    print(f"matched {len(doc_rows)}/{len(genres)} docs")
    print(f"wrote {out_dir/'docs.jsonl'} and {out_dir/'gold.jsonl'}")
    print(f"gold triples total: {sum(len(g['triples']) for g in gold_rows)}")


if __name__ == "__main__":
    main()
