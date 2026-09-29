"""Round 3 fix: normalize 证候-type entity names to the schema's own canonical form.

prompts/tcm_prompt_template_v2_pro.txt rule 1 says 证候 names should be normalized to end in
"证" (e.g. "胃中寒冷"->"胃中寒冷证"), but the LLM doesn't always apply this consistently --
in merged_neike_v1_boundaryfix, 396/818 证候 nodes are missing the suffix, and 112 of those
have a same-name-plus-证 sibling already in the graph (e.g. both "气虚" and "气虚证" exist as
separate 证候 nodes for what the schema itself says should be one canonical name). This is a
mechanical string-canonicalization fix mandated by the schema's own rule, not a judgment call
about whether two different concepts should merge -- both nodes are already typed 证候 by the
extraction model, so appending the missing suffix and letting the existing stage3/stage7
exact-name+type merge logic collapse them is safe and consistent with how every other
same-named 证候 node in the graph already merges across diseases.

Operates on extraction_valid.jsonl (entity list only) in a copied split, no LLM calls needed
-- stage3_align/stage4_build_graph/stage7_merge re-derive everything else from there.

Usage: .venv/bin/python scripts/fix_zhenghou_suffix.py --split neike_v3_zhengsuffix
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common import read_jsonl, work_dir, write_jsonl  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True)
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    rows = list(read_jsonl(wd / "extraction_valid.jsonl"))

    n_renamed = 0
    for row in rows:
        for e in row["entities"]:
            if e["type"] == "证候" and e["name"] and not e["name"].endswith("证"):
                e["name"] = e["name"] + "证"
                n_renamed += 1

    write_jsonl(wd / "extraction_valid.jsonl", rows)
    print(f"renamed {n_renamed} 证候 entities to add missing 证 suffix")


if __name__ == "__main__":
    main()
