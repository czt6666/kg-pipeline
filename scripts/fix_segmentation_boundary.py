"""Round 1 fix: rewrite the `所属疾病：` line and `title` prefix for the 247 docs confirmed
mislabeled by the round0 segmentation bug (research/round0_segmentation_bug.md), inside a
COPY of the neike split (never touches data/raw/ or the original data/work/TCM/neike/).

Only rewrites metadata that build_tcm.py itself writes (所属疾病 line + title prefix) —
the underlying OCR body text is untouched. Uses
research/neike_confirmed_contamination_map.json (the CONSERVATIVE subset of
scripts/boundary_map.py's output, cross-validated against each doc's actual recorded label
-- the broader neike_disease_boundary_map.json has false positives at chapter-tail docs
whose page_start coincides with the next chapter's boundary page, e.g. a "感冒·古籍摘要"
doc that's actually 哮病's tail content sharing a page number with 喘证's header; see
scripts/boundary_map.py main()) as the source of truth for the correct disease name.

Usage: .venv/bin/python scripts/fix_segmentation_boundary.py --target neike_v1_boundaryfix
Prereq: the target dir must already exist as a copy of data/work/TCM/neike (this script
refuses to run on the original `neike` dir to avoid clobbering the v0 baseline).
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch_file(path: Path, boundary_map: dict) -> int:
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    n_changed = 0
    out = []
    for line in lines:
        d = json.loads(line)
        true_d = boundary_map.get(d["doc_id"])
        old_label = d["title"].split("·", 1)[0]
        if true_d and true_d != old_label:
            rest_title = d["title"].split("·", 1)[1] if "·" in d["title"] else None
            d["title"] = f"{true_d}·{rest_title}" if rest_title else true_d
            if d["text"].startswith(f"所属疾病：{old_label}"):
                d["text"] = d["text"].replace(f"所属疾病：{old_label}", f"所属疾病：{true_d}", 1)
            n_changed += 1
        out.append(json.dumps(d, ensure_ascii=False))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return n_changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="split name under data/work/TCM/, must be a copy of neike")
    args = ap.parse_args()

    target_dir = ROOT / "data/work/TCM" / args.target
    if target_dir.resolve() == (ROOT / "data/work/TCM/neike").resolve():
        raise SystemExit("refusing to patch data/work/TCM/neike directly -- cp it to a new dir first")
    if not target_dir.exists():
        raise SystemExit(f"{target_dir} does not exist -- cp -r data/work/TCM/neike {target_dir} first")

    boundary_map = json.loads((ROOT / "research/neike_confirmed_contamination_map.json").read_text())

    for fname in ("docs.jsonl", "docs_gelun.jsonl"):
        n = patch_file(target_dir / fname, boundary_map)
        print(f"{fname}: patched {n} docs")


if __name__ == "__main__":
    main()
