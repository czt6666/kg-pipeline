"""Stage 3: intra-document entity alignment (DESIGN.md section 4).

Scope is a single document only -- no cross-document merging (same-named entities in
different documents stay distinct nodes, per DESIGN.md 4: "不同文档中同名实体为不同节点").

Step A (mentions grouping) is already done by the LLM's own entity/mentions output from
stage 1-2, so local_id already identifies one entity within a document. Step B here only
merges *different* local_ids within the same doc whose normalized name collides.
"""
import argparse
import re
import unicodedata
from collections import defaultdict

from core.common import read_jsonl, work_dir, write_jsonl

LEADING_ARTICLES = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = LEADING_ARTICLES.sub("", s)
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return s.lower()


class UnionFind:
    def __init__(self, keys):
        self.parent = {k: k for k in keys}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def align_doc(doc_id, entities):
    """Returns list of {doc_id, local_id, entity_id} and canonical-name/alias info
    keyed by entity_id, for stage 4 to consume."""
    keys = [e["local_id"] for e in entities]
    uf = UnionFind(keys)

    groups = defaultdict(list)
    for e in entities:
        key = (normalize_name(e["name"]), e["type"])
        groups[key].append(e["local_id"])
    for _, local_ids in groups.items():
        for lid in local_ids[1:]:
            uf.union(local_ids[0], lid)

    root_to_members = defaultdict(list)
    for e in entities:
        root_to_members[uf.find(e["local_id"])].append(e)

    alignment_rows = []
    entity_records = {}
    for i, (root, members) in enumerate(sorted(root_to_members.items())):
        entity_id = f"{doc_id}#{i}"
        canonical = max(members, key=lambda e: len(e["name"]))
        aliases = sorted({m["name"] for m in members if m["name"] != canonical["name"]})
        entity_records[entity_id] = {
            "name": canonical["name"],
            "type": canonical["type"],
            "aliases": aliases,
            "member_local_ids": [m["local_id"] for m in members],
        }
        for m in members:
            alignment_rows.append({"doc_id": doc_id, "local_id": m["local_id"], "entity_id": entity_id})

    return alignment_rows, entity_records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="docred")
    ap.add_argument("--split", default="dev")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    alignment_rows = []
    n_docs = n_before = n_after = 0
    for doc in read_jsonl(wd / "extraction_valid.jsonl"):
        rows, entity_records = align_doc(doc["doc_id"], doc["entities"])
        alignment_rows.extend(rows)
        n_docs += 1
        n_before += len(doc["entities"])
        n_after += len(entity_records)

    write_jsonl(wd / "alignment_map.jsonl", alignment_rows)
    print(f"docs={n_docs} entities_before_merge={n_before} entities_after_merge={n_after} "
          f"(merged {n_before-n_after})")


if __name__ == "__main__":
    main()
