"""Shared OCR-cleanup + CLI driver for the TCM stage-0 segmenters.

build_tcm.py (中医内科学-style disease-entry layout) and build_tcm_generic.py (plain
第X章/第X节/一二三 textbook layout) segment OCR'd pages into paragraph-level docs.jsonl
chunks. They differ only in *how a page's text is cut into chunks* (segment()); running
headers, line-wrap/page-break joining, figure-block stripping, page-range lookup and the
docs.jsonl-row assembly / CLI are identical between them, so that shared machinery lives
here and each segmenter supplies its own `segment(full_text, book_title_hint) -> chunks`
as a Strategy plugged into `run_cli()`.

A chunk is a dict with `section`, `title`, `text`, plus one caller-chosen key (see
`run_cli`'s `label_key`) holding the enclosing disease/chapter name used to build the
"所属疾病："/"所属章节：" prefix line prepended to `text` (a syndrome's own paragraph
rarely repeats the disease/chapter name, so downstream extraction needs it restated).
"""
import argparse
import bisect
import re

from common import read_jsonl, work_dir, write_jsonl

RUNNING_HEADER_RE = re.compile(
    r"^\s*(\d{1,4}\s+\S{2,10}|第[一二三四五六七八九十百]+章\s+\S+\s+\d{1,4})\s*$"
)
FIGURE_CAPTION_RE = re.compile(r"^图\s*\d+[-—]\d+")
PAREN_SUBHEADER_RE = re.compile(r"^[（(]([一二三四五六七八九十]+)[）)]\s*(\S+)")

# 第X节 (section, title on the same line -- see build_tcm.DISEASE_HEADER_RE naming: it
# was written for 中医内科学's disease sections but build_tcm_generic reuses it verbatim
# as the generic "节-header" boundary for 中医基础理论/中医诊断学).
DISEASE_HEADER_RE = re.compile(r"^(第[一二三四五六七八九十百]+节\s*\S.*|附\s+\S.*)$")

# 第一章 (chapter, title usually on the *following* OCR line) and top-level Chinese-
# numeral enumeration ("一、气一元论"). Neither appears in 中医内科学's 下篇各论 (what
# build_tcm.segment() was written against), but both are the primary structural units of
# 中医基础理论 and 中医诊断学 (build_tcm_generic.segment()) and of 中医内科学's own 上篇总论.
# Recognizing them here in _looks_like_new_unit is what keeps smart_join() from swallowing
# these headers into the surrounding paragraph when OCR runs them together without a real
# line break.
CHAPTER_STANDALONE_RE = re.compile(r"^第[一二三四五六七八九十百]+章\s*$")
CN_ENUM_RE = re.compile(r"^[一二三四五六七八九十]+、\S+")

SENTENCE_END_CHARS = "。！？」』”’）)"


def _looks_like_new_unit(line: str) -> bool:
    """Headings/numbered items that always start a new unit regardless of surrounding
    punctuation. Deliberately excludes 《书名》 citation starts: in ordinary prose
    "金•李东垣《医学发明》曰：..." is one continuous sentence -- an author name directly
    followed by a book title with no punctuation between them -- so treating 《 as a
    forced break here would fracture it. (build_tcm.split_classic_quotes() handles the
    书名 case where it *is* a real boundary, inside a dedicated 古籍摘要 section.)"""
    line = line.strip()
    return bool(
        re.match(r"^【(.+?)】\s*$", line) or DISEASE_HEADER_RE.match(line)
        or re.match(r"^\d+[.、]\s*\S+$", line) or PAREN_SUBHEADER_RE.match(line)
        or CHAPTER_STANDALONE_RE.match(line) or CN_ENUM_RE.match(line)
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
    page texts, fixing sentences split by a page break) -- same rule, two granularities.

    One case _join_sep can't see on its own: a bare "第X章" marker is immediately followed
    by the chapter title on its own OCR line (e.g. "第一章" / "中医学的哲学基础" / "气一元
    论……"), but the title itself is arbitrary short text that matches no heading regex --
    so nothing tells _join_sep to force a break *after* it, and it silently fuses into the
    chapter's opening paragraph. force_breaks counts down 2 forced "\\n\\n" separators right
    after a marker line: one before the title, one after it."""
    if not fragments:
        return ""
    out = [fragments[0]]
    full_so_far = fragments[0]
    force_breaks = 2 if CHAPTER_STANDALONE_RE.match(fragments[0].strip()) else 0
    for frag in fragments[1:]:
        if force_breaks > 0:
            sep = "\n\n"
            force_breaks -= 1
        else:
            sep = _join_sep(full_so_far, frag)
        out.append(sep)
        out.append(frag)
        full_so_far = frag  # only the tail matters for the next _join_sep call
        if CHAPTER_STANDALONE_RE.match(frag.strip()):
            force_breaks = 2
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


def load_pages(wd, start_page=None, end_page=None):
    """Returns (full_text, page_offsets) where page_offsets[i] = (page_index, start_char)
    for the i-th page's first character in full_text, sorted by start_char.

    start_page/end_page (both inclusive, 0-based into the source PDF) let a caller carve
    a sub-range out of one ocr_pages.jsonl -- e.g. 中医内科学 OCRs its 上篇总论 and 下篇各论
    into one split, then segments each range with a different segmenter (build_tcm_generic
    vs build_tcm's disease-entry segment()); see CLAUDE.md's TCM extraction section."""
    page_texts = []
    for row in read_jsonl(wd / "ocr_pages.jsonl"):
        if start_page is not None and row["page_index"] < start_page:
            continue
        if end_page is not None and row["page_index"] > end_page:
            continue
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


def split_paren_subheaders(block: str):
    """Splits on （一）（二）（三） sub-headers within a block, e.g. 【辨证论治】's own
    (一)辨证要点 / (二)治则治法 / (三)证治分类. Returns [] if the block has no such
    sub-headers (caller falls back to treating it as flat). The heading line itself is
    stripped from the returned text (kept only as the label)."""
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


def run_cli(segment_fn, label_key: str, prefix_template: str, description: str):
    """Shared stage-0 TCM segmenter CLI: parse args, load_pages, run segment_fn, assemble
    docs.jsonl rows, write output.

    segment_fn(full_text, book_title_hint) -> list of chunk dicts, each with `section`,
    `title`, `text`, plus `label_key` holding the enclosing disease/chapter name (or a
    falsy value) that `prefix_template.format(label=...)` turns into the "所属疾病："/
    "所属章节：" line prepended to `text`.
    """
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True)
    ap.add_argument("--book", required=True, help="short book label stored on each doc")
    ap.add_argument("--start-page", type=int, default=None, help="0-based inclusive, filters ocr_pages.jsonl")
    ap.add_argument("--end-page", type=int, default=None, help="0-based inclusive, filters ocr_pages.jsonl")
    ap.add_argument("--doc-prefix", default=None, help="doc_id prefix, default tcm_{split}")
    ap.add_argument("--out", default="docs.jsonl", help="output filename under the split dir, "
                     "for combining multiple segmenter passes over sub-ranges of one split "
                     "(e.g. neike's 上篇总论 vs 下篇各论) before concatenating into docs.jsonl")
    args = ap.parse_args()

    wd = work_dir(args.dataset, args.split)
    full_text, offsets = load_pages(wd, args.start_page, args.end_page)
    chunks = segment_fn(full_text, args.book)

    doc_prefix = args.doc_prefix or f"tcm_{args.split}"
    docs = []
    for i, c in enumerate(chunks):
        start = full_text.find(c["text"])
        end = start + len(c["text"]) if start != -1 else 0
        p0, p1 = page_range_for(offsets, max(start, 0), max(end, 0))
        doc_id = f"{doc_prefix}_{i:04d}"
        label = c.get(label_key)
        prefix = prefix_template.format(label=label) if label else ""
        docs.append({
            "doc_id": doc_id,
            "title": c["title"],
            "text": prefix + c["text"],
            "book": args.book,
            "section": c["section"],
            "page_start": p0,
            "page_end": p1,
        })

    write_jsonl(wd / args.out, docs)
    print(f"wrote {len(docs)} docs to {wd/args.out}")
    for d in docs:
        print(f"  [{d['page_start']}-{d['page_end']}] {d['title']} ({len(d['text'])} chars)")
