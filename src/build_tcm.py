"""Stage 0 (TCM): segment OCR'd page text into paragraph-level docs.jsonl.

Modern 中医内科学-style textbooks share one disease-entry layout across virtually every
chapter: 概述 -> 病因病机 -> 诊断与鉴别诊断 -> 【辨证论治】(辨证要点/治则治法/证治分类,
the last being a numbered list of syndrome patterns each with 临床表现/证机概要/治法/
代表方/常用药/加减) -> 临证备要 -> 预防调护 -> 小结 -> 古籍摘要 -> 名医验案 -> 文献推介.
This segmenter is written against that structure (verified by hand against the OCR'd
呃逆/腹痛 sections) rather than being a generic paragraph splitter, since chunking at the
book's own semantic units is what makes "分段落的提取详细结果" (per-user request)
meaningful -- one doc == one syndrome entry or one citation, not an arbitrary token window.

Each output doc is prefixed with "所属疾病：{disease}" for entity-linking context (see
prompts/tcm_fewshot.json, which is written in this exact style) since a syndrome's own
paragraph rarely repeats the disease name.

文献推介 (bibliography / journal citation lists) is dropped: it is not TCM domain
content, just reference metadata, and would only inject author/journal-name noise.
名医验案 (patient case records) are KEPT (real prescriptions in use) but the prompt
itself instructs the extractor to skip patient-identifying particulars (see rule 6 in
build_tcm_prompt.py's template).

Output: data/work/TCM/{split}/docs.jsonl, one row per paragraph-level chunk:
  {doc_id, title, text, book, section, page_start, page_end}

OCR-cleanup (load_pages/smart_join/strip_figure_blocks/page_range_for) and the CLI
driver are shared with build_tcm_generic.py -- see tcm_ocr.py.
"""
import re

from tcm_ocr import DISEASE_HEADER_RE, run_cli, split_paren_subheaders

BRACKET_HEADER_RE = re.compile(r"^【(.+?)】\s*$")
NUMBERED_ITEM_RE = re.compile(r"^\d+[.、]\s*\S+$")
CLASSIC_QUOTE_RE = re.compile(r"^《[^》]+》", re.MULTILINE)
DROP_SECTIONS = {"文献推介"}


def clean_disease_name(raw: str) -> str:
    raw = re.sub(r"^第[一二三四五六七八九十百]+节\s*", "", raw)
    raw = re.sub(r"^附\s+", "", raw)
    return re.sub(r"\s+", "", raw.strip())


def split_numbered_items(block: str):
    """Splits a 证治分类-style block into (header_line_or_None, item_text) parts, where
    header_line is any lead-in text before the first numbered item (e.g. sub-heading)."""
    lines = block.split("\n")
    idx_starts = [i for i, ln in enumerate(lines) if NUMBERED_ITEM_RE.match(ln.strip())]
    if not idx_starts:
        return [(None, block)]
    out = []
    if idx_starts[0] > 0:
        lead = "\n".join(lines[: idx_starts[0]]).strip()
        if lead:
            out.append((None, lead))
    for j, start in enumerate(idx_starts):
        end = idx_starts[j + 1] if j + 1 < len(idx_starts) else len(lines)
        out.append((lines[start].strip(), "\n".join(lines[start:end]).strip()))
    return out


def split_classic_quotes(block: str):
    """《书名》 citation lines each start a new quote in 古籍摘要 sections."""
    idx_starts = [m.start() for m in CLASSIC_QUOTE_RE.finditer(block)]
    if len(idx_starts) <= 1:
        return [block]
    idx_starts.append(len(block))
    return [block[idx_starts[i]:idx_starts[i + 1]].strip() for i in range(len(idx_starts) - 1)]


def segment(full_text: str, book_title_hint: str = ""):
    """Returns list of {disease, section, title, text} chunks. book_title_hint is unused
    here (accepted only so this has the same call signature as build_tcm_generic.segment,
    letting both plug into tcm_ocr.run_cli uniformly) -- disease boundaries come from
    DISEASE_HEADER_RE (第X节), not from the book title."""
    lines = full_text.split("\n")
    disease_bounds = []  # (start_line, disease_name)
    for i, ln in enumerate(lines):
        m = DISEASE_HEADER_RE.match(ln.strip())
        if m:
            disease_bounds.append((i, clean_disease_name(m.group(1))))
    if not disease_bounds:
        disease_bounds = [(0, "")]
    disease_bounds.append((len(lines), None))

    chunks = []
    for k in range(len(disease_bounds) - 1):
        start, disease = disease_bounds[k]
        end = disease_bounds[k + 1][0]
        body_lines = lines[start + 1 if disease else start: end]
        body = "\n".join(body_lines)

        idx_starts = []
        for i, ln in enumerate(body_lines):
            m = BRACKET_HEADER_RE.match(ln.strip())
            if m:
                idx_starts.append((i, m.group(1)))

        if not idx_starts:
            sections = [(None, body)]
        else:
            sections = []
            if idx_starts[0][0] > 0:
                lead = "\n".join(body_lines[: idx_starts[0][0]]).strip()
                if lead:
                    sections.append(("概述", lead))
            for j, (i, label) in enumerate(idx_starts):
                nxt = idx_starts[j + 1][0] if j + 1 < len(idx_starts) else len(body_lines)
                sections.append((label, "\n".join(body_lines[i + 1: nxt]).strip()))

        for label, text in sections:
            if not text or label in DROP_SECTIONS:
                continue

            paren_parts = split_paren_subheaders(text)
            if paren_parts:
                for sub_label, sub_text in paren_parts:
                    if not sub_text.strip():
                        continue
                    if sub_label and ("证治分类" in sub_label or sub_text.count("临床表现：") >= 2):
                        for num_header, num_text in split_numbered_items(sub_text):
                            if num_text.strip():
                                parts = [disease, label, sub_label, num_header]
                                title = "·".join(p for p in parts if p)
                                chunks.append({"disease": disease, "section": label, "title": title, "text": num_text})
                    else:
                        parts = [disease, label, sub_label]
                        title = "·".join(p for p in parts if p)
                        chunks.append({"disease": disease, "section": label, "title": title, "text": sub_text})
                continue

            if "证治分类" in (label or "") or text.count("临床表现：") >= 2:
                for sub_header, sub_text in split_numbered_items(text):
                    if sub_text.strip():
                        title = f"{disease}·{label}·{sub_header}" if sub_header else f"{disease}·{label}"
                        chunks.append({"disease": disease, "section": label, "title": title, "text": sub_text})
            elif label == "古籍摘要":
                for quote in split_classic_quotes(text):
                    if quote.strip():
                        chunks.append({"disease": disease, "section": label,
                                        "title": f"{disease}·{label}", "text": quote})
            else:
                chunks.append({"disease": disease, "section": label, "title": f"{disease}·{label}" if label else disease, "text": text})
    return chunks


if __name__ == "__main__":
    run_cli(segment, label_key="disease", prefix_template="所属疾病：{label}\n\n",
             description=__doc__)
