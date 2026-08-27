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
"""
import argparse
import bisect
import re

from common import read_jsonl, work_dir, write_jsonl

RUNNING_HEADER_RE = re.compile(
    r"^\s*(\d{1,4}\s+\S{2,10}|第[一二三四五六七八九十百]+章\s+\S+\s+\d{1,4})\s*$"
)
DISEASE_HEADER_RE = re.compile(r"^(第[一二三四五六七八九十百]+节\s*\S.*|附\s+\S.*)$")
BRACKET_HEADER_RE = re.compile(r"^【(.+?)】\s*$")
PAREN_SUBHEADER_RE = re.compile(r"^[（(]([一二三四五六七八九十]+)[）)]\s*(\S+)")
NUMBERED_ITEM_RE = re.compile(r"^\d+[.、]\s*\S+$")
CLASSIC_QUOTE_RE = re.compile(r"^《[^》]+》", re.MULTILINE)
FIGURE_CAPTION_RE = re.compile(r"^图\s*\d+[-—]\d+")
DROP_SECTIONS = {"文献推介"}


def clean_disease_name(raw: str) -> str:
    raw = re.sub(r"^第[一二三四五六七八九十百]+节\s*", "", raw)
    raw = re.sub(r"^附\s+", "", raw)
    return re.sub(r"\s+", "", raw.strip())


SENTENCE_END_CHARS = "。！？」』”’）)"


def _looks_like_new_unit(line: str) -> bool:
    """Headings/numbered items that always start a new unit regardless of surrounding
    punctuation. Deliberately excludes CLASSIC_QUOTE_RE (《书名》): that pattern is used
    by split_classic_quotes() to carve up a dedicated 古籍摘要 section (one 《书名》："..."
    citation per paragraph there), but in ordinary prose "金•李东垣《医学发明》曰：..." is
    one continuous sentence -- an author name directly followed by a book title with no
    punctuation between them -- so treating 《 as a forced break here fractures it."""
    line = line.strip()
    return bool(
        BRACKET_HEADER_RE.match(line) or DISEASE_HEADER_RE.match(line)
        or NUMBERED_ITEM_RE.match(line) or PAREN_SUBHEADER_RE.match(line)
    )


def _join_sep(prev_text: str, next_text: str) -> str:
    """"\\n\\n" only at a genuine sentence/structural boundary, "" otherwise. A line/page
    break in the source PDF is a print-layout artifact (fixed line width, fixed page
    size), not a paragraph boundary, so blindly inserting "\\n\\n" at every one fractures
    sentences (e.g. "循手\\n太阴之脉" from an OCR line wrap, or "立已；" / "大惊之，亦可
    已。" split across a page). The signal that a break is real: the text so far ends on
    sentence-final punctuation, or the previous/next line is itself a heading, numbered
    item, or citation start."""
    prev_last_line = prev_text.splitlines()[-1].strip() if prev_text else ""
    next_first_line = next_text.splitlines()[0].strip() if next_text else ""
    prev_ends_sentence = bool(prev_last_line) and prev_last_line[-1] in SENTENCE_END_CHARS
    is_real_break = prev_ends_sentence or _looks_like_new_unit(prev_last_line) or _looks_like_new_unit(next_first_line)
    return "\n\n" if is_real_break else ""


def smart_join(fragments: list[str]) -> str:
    """Joins a list of text fragments (each itself possibly multi-line) using _join_sep
    between every adjacent pair. Used both within a page (fragments = OCR-detected lines,
    fixing sentences wrapped by the print layout) and across pages (fragments = whole
    page texts, fixing sentences split by a page break) -- same rule, two granularities."""
    if not fragments:
        return ""
    out = [fragments[0]]
    full_so_far = fragments[0]
    for frag in fragments[1:]:
        sep = _join_sep(full_so_far, frag)
        out.append(sep)
        out.append(frag)
        full_so_far = frag  # only the tail matters for the next _join_sep call
    return "".join(out)


def strip_figure_blocks(lines: list[str]) -> list[str]:
    """Drops flattened flowchart/diagram box text. Vision OCR reads a diagram as a flat
    list of short text-detection boxes with no arrows/hierarchy, and in this book those
    boxes are immediately followed by a "图X-X ..." caption in OCR reading order (verified
    against 图7-5 呃逆病因病机演变, whose box text turned out to be a word-for-word subset
    of the neighboring 病因 prose paragraph -- so dropping it loses no information here,
    only the risk of the extractor guessing relations between disconnected phrases that
    have no real arrow between them). Heuristic: walk backward from each "图X-X" caption
    over short (<20 char) lines with no sentence-final punctuation -- that run is the
    diagram's boxes, not prose. Narrow to this book's caption placement; may not fire for
    a differently-formatted book, which is an acceptable miss (figures just pass through)."""
    def _short_and_unpunctuated(line: str) -> bool:
        return (
            len(line) < 20
            and not line.rstrip().endswith(tuple(SENTENCE_END_CHARS))
            and not _looks_like_new_unit(line)
        )

    out = list(lines)
    i = 0
    while i < len(out):
        if not FIGURE_CAPTION_RE.match(out[i].strip()):
            i += 1
            continue
        end = i + 1
        # some captions carry the title on the same line ("图 7-6 腹痛病因病机演变"),
        # others put it on the next line ("图 7-5" / "呃逆病因病机演变") -- only swallow
        # that next line if it doesn't itself look like a real header/subheader/etc.
        if end < len(out) and _short_and_unpunctuated(out[end]):
            end += 1
        start = i
        while start > 0 and _short_and_unpunctuated(out[start - 1]):
            start -= 1
        del out[start:end]
        i = start
    return out


def load_pages(wd):
    """Returns (full_text, page_offsets) where page_offsets[i] = (page_index, start_char)
    for the i-th page's first character in full_text, sorted by start_char."""
    page_texts = []
    for row in read_jsonl(wd / "ocr_pages.jsonl"):
        lines = [ln.strip() for ln in row["text"].splitlines()
                 if ln.strip() and not RUNNING_HEADER_RE.match(ln.strip())]
        lines = strip_figure_blocks(lines)
        text = smart_join(lines)
        if text:
            page_texts.append((row["page_index"], text))

    full_text, offsets = "", []
    for page_index, text in page_texts:
        if full_text:
            full_text += _join_sep(full_text, text)
        offsets.append((len(full_text), page_index))
        full_text += text
    return full_text, offsets


def page_range_for(offsets, start, end):
    starts = [o[0] for o in offsets]
    i0 = bisect.bisect_right(starts, start) - 1
    i1 = bisect.bisect_right(starts, end) - 1
    p0 = offsets[max(i0, 0)][1]
    p1 = offsets[max(i1, 0)][1]
    return p0, p1


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


def split_paren_subheaders(block: str):
    """Splits on （一）（二）（三） sub-headers within a 【...】 bracket section, e.g.
    【辨证论治】's own (一)辨证要点 / (二)治则治法 / (三)证治分类. Returns [] if the block
    has no such sub-headers (caller falls back to treating it as flat). The heading line
    itself is stripped from the returned text (kept only as the label)."""
    lines = block.split("\n")
    idx_starts = []
    for i, ln in enumerate(lines):
        m = PAREN_SUBHEADER_RE.match(ln.strip())
        if m:
            idx_starts.append((i, m.group(2)))
    if not idx_starts:
        return []
    out = []
    if idx_starts[0][0] > 0:
        lead = "\n".join(lines[: idx_starts[0][0]]).strip()
        if lead:
            out.append((None, lead))
    for j, (i, label) in enumerate(idx_starts):
        nxt = idx_starts[j + 1][0] if j + 1 < len(idx_starts) else len(lines)
        out.append((label, "\n".join(lines[i + 1: nxt]).strip()))
    return out


def split_classic_quotes(block: str):
    """《书名》 citation lines each start a new quote in 古籍摘要 sections."""
    idx_starts = [m.start() for m in CLASSIC_QUOTE_RE.finditer(block)]
    if len(idx_starts) <= 1:
        return [block]
    idx_starts.append(len(block))
    return [block[idx_starts[i]:idx_starts[i + 1]].strip() for i in range(len(idx_starts) - 1)]


def segment(full_text: str):
    """Returns list of {disease, section, title, text} chunks."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True)
    ap.add_argument("--book", required=True, help="short book label stored on each doc")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    full_text, offsets = load_pages(wd)
    chunks = segment(full_text)

    docs = []
    for i, c in enumerate(chunks):
        start = full_text.find(c["text"])
        end = start + len(c["text"]) if start != -1 else 0
        p0, p1 = page_range_for(offsets, max(start, 0), max(end, 0))
        doc_id = f"tcm_{args.split}_{i:04d}"
        prefix = f"所属疾病：{c['disease']}\n\n" if c["disease"] else ""
        docs.append({
            "doc_id": doc_id,
            "title": c["title"],
            "text": prefix + c["text"],
            "book": args.book,
            "section": c["section"],
            "page_start": p0,
            "page_end": p1,
        })

    write_jsonl(wd / "docs.jsonl", docs)
    print(f"wrote {len(docs)} docs to {wd/'docs.jsonl'}")
    for d in docs:
        print(f"  [{d['page_start']}-{d['page_end']}] {d['title']} ({len(d['text'])} chars)")


if __name__ == "__main__":
    main()
