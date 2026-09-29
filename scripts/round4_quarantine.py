"""Round 4：给"合理不连边"的孤立节点打隔离区标记，不再当成待修的连通性问题。

背景：Round 0-3 反复确认，孤立节点里有一大块是"概述/源流""古籍摘要""临证备要"
"名医验案""小结""预防调护""辨证要点""辨治概要""治则治法""辨主症"这类段落——按
`prompts/tcm_prompt_template_v2_pro.txt` 第一节的段落分类表，这些段落要么明确不
允许分型/表现为（概述/源流），要么压根不在表里、只能按"显式线索"抽（其余大多是纯
讨论/医案叙述，没有"某证候表现为某症状"这种可引用的直接陈述）。继续想办法给它们
"连边"违反硬约束"新增的每条边必须能引用原文依据"——原文根本没有这类陈述可引用。

处理方式：不删除、不强行连边，打 `quarantined=true` + `quarantine_reason`，从"孤立率"
的分子分母里都排除（`compute_isolation.py --exclude-quarantined`），同时写一份
`quarantine.jsonl`（entity_id/name/type/reason/source_doc_ids/原文标题）供调试面板展示。

判定条件（保守，宁可漏判也不错判）：该节点**所有**来源文档的 title 第三段（或退化到
用 section 字段）都落在上述"讨论型"小节名单里，且 parse_status==ok（截断问题不算，
留给以后的抽取修复，不能用隔离掩盖真正的抽取缺陷）。
"""
import json
from collections import Counter
from pathlib import Path

NARRATIVE_SUBSECTIONS = {
    "概述", "源流", "古籍摘要", "临证备要", "名医验案", "小结", "预防调护",
    "辨证要点", "辨治概要", "治则治法", "辨主症",
}

MERGED_DIR = Path("data/work/TCM/merged_neike_conn_v3")
SPLIT_DIR = Path("data/work/TCM/neike_conn_v3")
OUT_MERGED = Path("data/work/TCM/merged_neike_conn_v4")


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_jsonl(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def subsection(title: str, section: str) -> str:
    parts = (title or "").split("·")
    if len(parts) > 2:
        return parts[2].lstrip("0123456789一二三四五六七八九十、. ")
    return section or ""


def main():
    nodes = load_jsonl(MERGED_DIR / "nodes.jsonl")
    edges = load_jsonl(MERGED_DIR / "edges.jsonl")
    deg = Counter()
    for e in edges:
        deg[e["head"]] += 1
        deg[e["tail"]] += 1
    isolated_ids = {n["entity_id"] for n in nodes if deg[n["entity_id"]] == 0}

    raw = load_jsonl(SPLIT_DIR / "extraction_raw.jsonl")
    status_by_doc = {r["doc_id"]: r.get("parse_status") for r in raw}
    docs = load_jsonl(SPLIT_DIR / "docs.jsonl")
    title_by_doc = {d["doc_id"]: d["title"] for d in docs}
    section_by_doc = {d["doc_id"]: d["section"] for d in docs}

    quarantined = []
    for n in nodes:
        if n["entity_id"] not in isolated_ids:
            continue
        docs_ = n["source_doc_ids"]
        if any(status_by_doc.get(d) != "ok" for d in docs_):
            continue  # leave truncation-adjacent docs for extraction fixes, not quarantine
        subsecs = {subsection(title_by_doc.get(d, ""), section_by_doc.get(d, "")) for d in docs_}
        if subsecs and subsecs.issubset(NARRATIVE_SUBSECTIONS):
            quarantined.append({
                "entity_id": n["entity_id"],
                "name": n["name"],
                "type": n["type"],
                "reason": f"来源段落属于讨论/医案性质（{'/'.join(sorted(subsecs))}），"
                          "原文没有可引用的'某证候表现为/治法/方用...'式陈述，不强行连边",
                "source_doc_ids": docs_,
            })

    quarantined_ids = {q["entity_id"] for q in quarantined}
    print(f"总孤立节点: {len(isolated_ids)}  隔离区: {len(quarantined_ids)}  "
          f"仍待处理: {len(isolated_ids) - len(quarantined_ids)}")

    # copy merged dir, add quarantined flag to nodes.jsonl, write quarantine.jsonl
    import shutil
    if OUT_MERGED.exists():
        shutil.rmtree(OUT_MERGED)
    shutil.copytree(MERGED_DIR, OUT_MERGED)

    new_nodes = []
    for n in nodes:
        n = dict(n)
        n["quarantined"] = n["entity_id"] in quarantined_ids
        new_nodes.append(n)
    write_jsonl(OUT_MERGED / "nodes.jsonl", new_nodes)
    write_jsonl(OUT_MERGED / "quarantine.jsonl", quarantined)

    print(f"wrote {OUT_MERGED}/nodes.jsonl (quarantined flag added) and quarantine.jsonl")


if __name__ == "__main__":
    main()
