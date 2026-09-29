"""Parses 证治分类 (辨证论治 -> per-pattern 症状/治法/代表方/常用药) blocks out of
data/work/TCM/neike/docs_gelun.jsonl, grounded with the corrected disease label from
research/neike_disease_boundary_map.json (not the buggy 所属疾病/title field) — see
research/round0_segmentation_bug.md.

This is read-only tooling for building eval/questions.jsonl (CLAUDE.md step 1: build the
eval set from source text before touching the graph). It doesn't write to data/work/.

Output: research/neike_patterns.jsonl, one record per 证型:
  {disease, pattern, symptoms:[...], principle, formula, meds:[...], doc_id, page_start, char_start}
`char_start` is the offset of this pattern's paragraph within the doc's `text`, so callers can
quote a verbatim excerpt as eval evidence.

Usage: .venv/bin/python scripts/parse_patterns.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data/work/TCM/neike"

# Two doc shapes seen in the source:
#  (a) multi-pattern docs (e.g. 咳嗽's "证治分类·1.外感咳嗽"): each 证型 is one paragraph,
#      marker+name+临床表现+content all inline: "（1） 风寒袭肺临床表现：恶寒……"
#  (b) single-pattern docs (e.g. 感冒's "证治分类·1.风寒束表"): the marker+name is its own
#      bare paragraph ("1.风寒束表"), and "临床表现：" starts the *next* paragraph.
# Multi-pattern docs also carry a bare category-header paragraph before the group (e.g.
# "1.外感咳嗽") that is NOT itself a 证型 — it's immediately followed by an inline (a)-style
# paragraph rather than a "临床表现：" one, which is how we tell the two bare-marker cases apart.
INLINE_MARKER = re.compile(r"^[（(](\d+)[）)]\s*([^\n]{1,12}?)临床表现[：:](.*)$", re.S)
BARE_MARKER = re.compile(r"^[（(]?(\d+)[）).、]\s*([^\n]{1,14})$")


def parse_doc(doc, true_disease):
    text = doc["text"]
    if text.startswith("所属疾病"):
        text = text.split("\n\n", 1)[1] if "\n\n" in text else ""
    paras = [p for p in text.split("\n\n") if p.strip()]

    def new_record(name):
        name = name.strip()
        if not name.endswith("证"):
            name += "证"
        return {
            "disease": true_disease,
            "pattern": name,
            "symptoms_raw": None,
            "principle": None,
            "formula": None,
            "meds_raw": None,
            "doc_id": doc["doc_id"],
            "page_start": doc["page_start"],
        }

    records = []
    cur = None
    pending_name = None  # from a bare marker paragraph, not yet confirmed as a real 证型
    for para in paras:
        p = para.strip()
        m = INLINE_MARKER.match(p)
        if m:
            if cur:
                records.append(cur)
            pending_name = None
            cur = new_record(m.group(2))
            cur["symptoms_raw"] = m.group(3).strip()
            continue
        bm = BARE_MARKER.match(p)
        if bm:
            # Could be a real single-pattern marker (next para is 临床表现) or a multi-pattern
            # category header (next para is an INLINE_MARKER, handled above) — defer until we
            # see what follows.
            pending_name = bm.group(2)
            continue
        if p.startswith("临床表现"):
            if pending_name is not None:
                if cur:
                    records.append(cur)
                cur = new_record(pending_name)
                pending_name = None
            if cur:
                cur["symptoms_raw"] = re.sub(r"^临床表现[：:]", "", p).strip()
            continue
        pending_name = None
        if cur is None:
            continue
        if para.startswith("证机概要"):
            continue  # 病机 not 症状/治法/方, schema explicitly excludes it as an entity
        if para.startswith("治法") and cur["principle"] is None:
            cur["principle"] = re.sub(r"^治法[：:]", "", para).strip()
        elif para.startswith("代表方") and cur["formula"] is None:
            cur["formula"] = re.sub(r"^代表方[：:]", "", para).strip()
        elif para.startswith("常用药") and cur["meds_raw"] is None:
            cur["meds_raw"] = re.sub(r"^常用药[：:]", "", para).strip()
    if cur:
        records.append(cur)
    return records


def main():
    boundary_map = json.loads((ROOT / "research/neike_disease_boundary_map.json").read_text())
    docs = [json.loads(l) for l in open(WORK / "docs_gelun.jsonl")]
    docs_by_id = {d["doc_id"]: d for d in docs}

    all_records = []
    for d in docs:
        if "证治分类" not in d["title"]:
            continue
        true_disease = boundary_map.get(d["doc_id"], d["title"].split("·")[0])
        all_records.extend(parse_doc(d, true_disease))

    out_path = ROOT / "research/neike_patterns.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    diseases = sorted(set(r["disease"] for r in all_records))
    print(f"parsed {len(all_records)} 证型 records across {len(diseases)} diseases -> {out_path}")
    missing_formula = sum(1 for r in all_records if not r["formula"])
    missing_principle = sum(1 for r in all_records if not r["principle"])
    print(f"missing formula: {missing_formula}, missing principle: {missing_principle}")


if __name__ == "__main__":
    main()
