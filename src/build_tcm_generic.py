"""Stage 0 (TCM, generic): segment OCR'd page text into chunk-level docs.jsonl for books
that are NOT laid out as 中医内科学-style disease entries (build_tcm.py's segment()).

中医基础理论 and 中医诊断学 (and 中医内科学's own 上篇总论, chapters 1-3) share a plain
textbook hierarchy instead: 第X章 (chapter, title on the following line) > optionally 第X节
(section, title on the same line) and/or 一、二、三、... (Chinese-numeral enumeration) > optionally
（一）（二）（三） sub-headers. 节 and 一/二/三 headers are not consistently nested the same way
across chapters (some chapters go straight from 章 to 一、, others insert a 节 layer first), so
this segmenter does not assume a fixed tree depth: within a chapter it treats every 节-header or
一/二/三-header line as a same-level split point, in document order, then only descends into
（一）（二）（三） subheaders (and finally a raw paragraph-packing fallback) for chunks that come
out over MAX_CHUNK_CHARS.

Shares OCR-cleanup (load_pages/smart_join/strip_figure_blocks), the （一）（二）（三） splitter
and the CLI driver with build_tcm.py via tcm_ocr.py, so both segmenters treat running headers,
figure blocks, and page-break artifacts identically -- only the heading grammar differs.

Output: data/pipeline/TCM/splits/{split}/{out}, one row per chunk:
  {doc_id, title, text, book, section, page_start, page_end}
"""
from tcm_ocr import CHAPTER_STANDALONE_RE, CN_ENUM_RE, DISEASE_HEADER_RE, run_cli, split_paren_subheaders

MAX_CHUNK_CHARS = 1800


def find_chapter_bounds(lines: list[str]):
    """Returns [(start_line_idx, title), ...]. Chapter marker is a bare "第X章" line; the
    title is whatever the next non-empty line is (see module docstring)."""
    bounds = []
    n = len(lines)
    i = 0
    while i < n:
        if CHAPTER_STANDALONE_RE.match(lines[i].strip()):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            title = lines[j].strip() if j < n else ""
            bounds.append((i, title))
            i = j + 1
            continue
        i += 1
    return bounds


def find_subsection_bounds(lines: list[str]):
    """节-header or 一/二/三-enum lines within one chapter's body, in document order."""
    bounds = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if DISEASE_HEADER_RE.match(s) or CN_ENUM_RE.match(s):
            bounds.append((i, s))
    return bounds


def split_oversized(text: str, label: str):
    """Narrows an over-budget chunk: try （一）（二）（三） subheaders first (recursively, in
    case a subheader block is itself still too long), then fall back to packing
    blank-line-separated paragraphs into ~MAX_CHUNK_CHARS groups. Returns [(label, text), ...]."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [(label, text)]

    parts = split_paren_subheaders(text)
    if len(parts) > 1:
        out = []
        for sub_label, sub_text in parts:
            if not sub_text.strip():
                continue
            full_label = f"{label}·{sub_label}" if sub_label else label
            out.extend(split_oversized(sub_text, full_label))
        return out

    paras = [p for p in text.split("\n\n") if p.strip()]
    out, buf, buf_len, part_idx = [], [], 0, 1
    for p in paras:
        if buf and buf_len + len(p) > MAX_CHUNK_CHARS:
            out.append((f"{label}（{part_idx}）", "\n\n".join(buf)))
            part_idx += 1
            buf, buf_len = [], 0
        buf.append(p)
        buf_len += len(p)
    if buf:
        out.append((f"{label}（{part_idx}）", "\n\n".join(buf)))
    return out if len(out) > 1 else [(label, text)]


def segment(full_text: str, book_title_hint: str = ""):
    """Returns list of {chapter, section, title, text} chunks."""
    lines = full_text.split("\n")
    chapter_bounds = find_chapter_bounds(lines)
    if not chapter_bounds:
        chapter_bounds = [(0, book_title_hint)]
    elif chapter_bounds[0][0] > 0:
        # content before the first "第X章" marker -- every book sampled opens with a bare
        # "绪论" (introduction) line here rather than a numbered chapter; without this, that
        # whole preamble (survey of the field, historical background) silently vanishes,
        # since the main loop below only ever covers [chapter_bounds[i][0], next_start).
        chapter_bounds = [(0, "绪论")] + chapter_bounds
    ends = [b[0] for b in chapter_bounds[1:]] + [len(lines)]

    chunks = []
    for (start, chapter_title), end in zip(chapter_bounds, ends):
        body_lines = lines[start:end]
        sub_bounds = find_subsection_bounds(body_lines)
        if not sub_bounds:
            sections = [(None, "\n".join(body_lines))]
        else:
            sections = []
            if sub_bounds[0][0] > 0:
                lead = "\n".join(body_lines[: sub_bounds[0][0]]).strip()
                if lead:
                    sections.append((None, lead))
            for j, (i, label) in enumerate(sub_bounds):
                nxt = sub_bounds[j + 1][0] if j + 1 < len(sub_bounds) else len(body_lines)
                sections.append((label, "\n".join(body_lines[i:nxt]).strip()))

        for label, text in sections:
            if not text.strip():
                continue
            base_title = f"{chapter_title}·{label}" if label else chapter_title
            for sub_title, sub_text in split_oversized(text, base_title):
                if sub_text.strip():
                    chunks.append({"chapter": chapter_title, "section": label,
                                    "title": sub_title, "text": sub_text})
    return chunks


if __name__ == "__main__":
    run_cli(segment, label_key="chapter", prefix_template="所属章节：{label}\n\n",
             description=__doc__)
