"""Reconstructs the TRUE per-doc disease label for data/work/TCM/neike/docs_gelun.jsonl,
independent of the (buggy) `所属疾病` field baked into docs.jsonl.

Why this exists (see research/round0_segmentation_bug.md for full evidence): build_tcm.py's
chapter-boundary detector matches "第X节" with a literal Chinese numeral. OCR sometimes drops
that numeral (e.g. "第二节 咳嗽" -> "第节咳嗽" on ocr_pages.jsonl page 75), so the detector
misses the boundary and every doc until the next successfully-matched header keeps inheriting
the PREVIOUS disease's label. Appendix subsections marked "附 XXX" (e.g. 多寐 under 不寐) are a
second, legitimate boundary marker the chunker does successfully catch.

This script re-derives boundaries directly from data/work/TCM/neike/ocr_pages.jsonl (both the
well-formed "第X节" headers and the bare "第节" ones), reconstructs what the chunker's internal
"current disease" state would have been at each page (frozen across bare boundaries, updated at
numbered/附 boundaries), and compares that reconstruction against each doc's actual recorded
title to confirm which docs are really contaminated (vs. incidental page-boundary noise).

Usage: .venv/bin/python scripts/boundary_map.py
Writes research/neike_disease_boundary_map.json: {doc_id: true_disease} for every docs_gelun.jsonl doc.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data/work/TCM/neike"

BARE = re.compile(r"第节([^\n]{0,10})")
NUMBERED = re.compile(r"第([一二三四五六七八九十百]+|[0-9]+)节[\s　]*([^\n]{0,15})")
FU = re.compile(r"(?:^|\n)附[\s　]+([^\n]{1,8})")


def clean(name: str) -> str:
    name = name.replace(" ", "").replace("　", "")
    return name.replace("黄疽", "黄疸")


def build_boundaries():
    pages = [json.loads(l) for l in open(WORK / "ocr_pages.jsonl")]
    pages = [p for p in pages if 66 <= p["page_index"] <= 450]  # 下篇各论 range only

    boundaries = []  # (page, disease_name, is_bare)
    for p in pages:
        for m in BARE.finditer(p["text"]):
            boundaries.append((p["page_index"], clean(m.group(1).strip()), True))
        for m in NUMBERED.finditer(p["text"]):
            boundaries.append((p["page_index"], clean(m.group(2).strip()), False))
        for m in FU.finditer(p["text"]):
            boundaries.append((p["page_index"], clean(m.group(1).strip()), False))
    boundaries.sort(key=lambda x: x[0])
    return boundaries


def build_timeline(boundaries):
    """true_disease updates at every boundary; tracked_disease (what the buggy chunker
    actually wrote to 所属疾病) only updates at non-bare boundaries."""
    timeline = []
    true_d = tracked_d = None
    for i, (pg, name, is_bare) in enumerate(boundaries):
        true_d = name
        if not is_bare:
            tracked_d = name
        next_pg = boundaries[i + 1][0] if i + 1 < len(boundaries) else 10**9
        timeline.append((pg, next_pg, true_d, tracked_d))
    return timeline


def lookup(timeline, page):
    for a, b, true_d, tracked_d in timeline:
        if a <= page < b:
            return true_d, tracked_d
    return None, None


def main():
    boundaries = build_boundaries()
    timeline = build_timeline(boundaries)
    docs = [json.loads(l) for l in open(WORK / "docs_gelun.jsonl")]

    out = {}
    confirmed = []
    for d in docs:
        true_d, tracked_d = lookup(timeline, d["page_start"])
        labeled = d["title"].split("·")[0]
        out[d["doc_id"]] = true_d or labeled
        if true_d and true_d != tracked_d and labeled == tracked_d:
            confirmed.append((d["doc_id"], d["page_start"], labeled, true_d))

    out_path = ROOT / "research/neike_disease_boundary_map.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out_path} ({len(out)} docs)")
    print(f"confirmed contaminated docs: {len(confirmed)}")

    # Separate, conservative artifact for actually PATCHING data: only the docs where the
    # bug mechanism was cross-validated (predicted buggy tracked_d == the doc's actual
    # recorded label). The full `out` map above has false positives at chapter-tail docs
    # whose page_start happens to coincide with the NEXT chapter's boundary page (e.g.
    # "感冒·古籍摘要" content that's actually 哮病's tail, sharing a page number with 喘证's
    # header) -- confirmed by manual inspection, see PROGRESS.md Round 1 notes. Do not use
    # `out` directly for patching; use this instead.
    confirmed_map = {doc_id: true_d for doc_id, _, _, true_d in confirmed}
    confirmed_path = ROOT / "research/neike_confirmed_contamination_map.json"
    confirmed_path.write_text(json.dumps(confirmed_map, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {confirmed_path} ({len(confirmed_map)} docs, safe for patching)")


if __name__ == "__main__":
    main()
