"""Round 2：给指定 doc_id 的文本前面拼接【标题路径】+【本段证型清单】，产出一份新的
docs.jsonl（只含目标文档，其余文档不动，用于小范围 trial 或后续拼回正式 split）。

背景（research/round0_connectivity.md / round2 调查）：抽样确认孤岛的真正机制不是"模型
不知道自己在讲哪个病"（疾病名"所属疾病：X"本来就在正文开头），而是一个 chunk 里塞了多个
并列的证型小节（如"中风·中脏腑"一个 chunk 里塞了 4 个闭证/脱证证型）时，模型生成到后面
容易漏建边——越靠后的证型越容易被漏，跟"标题路径"无关，跟"chunk 内有几个证型、模型有没
有意识到要覆盖全部"更相关。所以这版注入的不是简单复述标题，而是：
  1. 【标题路径】：docs.jsonl 里已有的 title 字段（"·"分隔的面包屑），原样给模型，
     成本几乎为零。
  2. 【本段证型清单】：从正文里用正则把"（N）名称"/"N.名称"/"N)名称"这类分型标记抠出来，
     显式告诉模型这个 chunk 一共有几个证型、每个都要覆盖，用来对抗"后面的证型被漏建"
     这个具体机制。

用法：
    .venv/bin/python scripts/round2_build_context_docs.py \\
        --split neike_conn_v1 --doc-ids research/round2_target_docs.json \\
        --out data/work/TCM/neike_conn_v2_trial/docs.jsonl
"""
import argparse
import json
import re
from pathlib import Path

# OCR 经常把"（1）证候名1）证候名临床表现："这类编号和标题粘在同一行、甚至粘在一起，
# 找不到可靠的行首/换行锚点，所以不按"行首编号"找，改成找"临床表现"这个 prompt 本身
# 就用来识别表现为关系的固定线索词，往回抠它前面 2-20 个字当候选证型名，再把编号前缀
# （（1）/1)/1./、等）洗掉。
LEADING_MARKER_RE = re.compile(r"^[（(]?[一二三四五六七八九十\d]+[）)、.\s]*")
BEFORE_MANIFEST_RE = re.compile(r"([^\n，。:：、（）()]{2,24}?)临床表现")


def extract_pattern_checklist(text: str) -> list[str]:
    names = []
    seen = set()
    for m in BEFORE_MANIFEST_RE.finditer(text):
        raw = m.group(1).strip()
        name = LEADING_MARKER_RE.sub("", raw).strip()
        if not name or len(name) < 2:
            continue
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def build_header(title: str, text: str) -> str:
    breadcrumb = title.replace("·", " > ") if title else ""
    checklist = extract_pattern_checklist(text)
    lines = []
    if breadcrumb:
        lines.append(f"【标题路径】{breadcrumb}")
    if len(checklist) >= 2:
        lines.append("【本段证型/分型清单，供自查用，下面每一项在原文里出现的位置都必须建立完整的"
                      "表现为/治法/方用/用药等关系，不要漏掉排在后面的条目】")
        for i, name in enumerate(checklist, 1):
            lines.append(f"  {i}. {name}")
        lines.append("（清单是从正文编号里自动抠出来的辅助自查项，可能包含个别非证型的编号"
                      "小标题，具体以正文实际内容为准，不要求逐字匹配清单措辞）")
    if not lines:
        return text
    return "\n".join(lines) + "\n\n" + text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="neike_conn_v1")
    ap.add_argument("--doc-ids", required=True, help="json file: list of doc_id strings")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    wd = Path("data/work/TCM") / args.split
    target_ids = set(json.load(open(args.doc_ids, encoding="utf-8")))

    docs = [json.loads(l) for l in open(wd / "docs.jsonl", encoding="utf-8") if l.strip()]
    out_rows = []
    n_checklist = 0
    for d in docs:
        if d["doc_id"] not in target_ids:
            continue
        new_text = build_header(d["title"], d["text"])
        if new_text != d["text"]:
            n_checklist += 1
        d2 = dict(d)
        d2["text"] = new_text
        out_rows.append(d2)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows)} docs to {out_path} ({n_checklist} got a header)")


if __name__ == "__main__":
    main()
