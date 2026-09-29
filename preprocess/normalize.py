"""Step 1 of the preprocess layer: deterministic character-level normalization, no LLM.

normalize(text) -> str applies, in order:
  1. 繁体转简体 (opencc, config t2s)
  2. 中医异体字/通假字映射表 (variant_chars.tsv)
  3. 标点/空白规范化 (全角转半角 + 顿号/逗号统一 + 页眉页脚行剔除 + 连续空白折叠)
  4. 单位规范 (錢->钱, 両->两)

Must be idempotent: normalize(normalize(x)) == normalize(x). Every sub-step here is
either a fixed character substitution (already-converted input has nothing left to
convert) or a whitespace/line filter that is stable once applied, so the whole pipeline
is idempotent by construction -- see test_normalize.py::test_idempotent for a mixed
end-to-end check rather than trusting that argument alone.
"""
import re
from pathlib import Path

import opencc

_PREPROCESS_DIR = Path(__file__).resolve().parent
VARIANT_TABLE_PATH = _PREPROCESS_DIR / "variant_chars.tsv"

_T2S = opencc.OpenCC("t2s")

# Private-use codepoint: guaranteed absent from real input, safe as a scratch marker.
_ZHENGJIA_GUARD = ""

UNIT_CHAR_MAP = {"錢": "钱", "両": "两"}

# Page-number / publisher-line residue that can survive stage0's own header stripping
# (tcm_ocr.RUNNING_HEADER_RE targets a specific running-header layout; this is a second,
# more permissive net at the paragraph level, e.g. plain page numbers or a lone
# "XX 出版社" credit line picked up mid-page by OCR).
_JUNK_LINE_RES = [
    re.compile(r"^第\s*[0-9〇一二三四五六七八九十百千]+\s*页$"),
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^ISBN[\s:：-]*[\dXx\-]+$"),
]

# 出版社/版权所有 are only checked against short, standalone lines (see _SHORT_LINE_MAX).
# 医案 paragraphs often end with an inline book citation, e.g. "...病情转危为安。（上海
# 市卫生局编，上海老中医经验·徐仲才医案，上海科学技术出版社.1980）" on ONE physical line
# with no internal newline (stage0 joins a whole case narrative into a single line) --
# an unbounded "contains 出版社 anywhere" match would nuke that entire clinical paragraph,
# not just the trailing citation. A real running-header credit line is short on its own.
_JUNK_LINE_RES_SHORT = [
    re.compile(r"^.*出版社.*$"),
    re.compile(r"^.*版权所有.*$"),
]
_SHORT_LINE_MAX = 40

# FF0C (，) is deliberately excluded from the generic fullwidth->halfwidth sweep --
# _unify_separators below is the single place that decides what comma-like marks look
# like, instead of half doing it here and half there.
_FULLWIDTH_TO_HALFWIDTH_EXCLUDE = {0xFF0C}

_VARIANT_TABLE = None


def _variant_table() -> dict:
    global _VARIANT_TABLE
    if _VARIANT_TABLE is None:
        table = {}
        for line in VARIANT_TABLE_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            src, dst = line.split("\t")
            table[src] = dst
        _VARIANT_TABLE = table
    return _VARIANT_TABLE


def _fullwidth_to_halfwidth(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if code in _FULLWIDTH_TO_HALFWIDTH_EXCLUDE:
            out.append(ch)
        elif code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def _unify_separators(text: str) -> str:
    """统一顿号/逗号: fold 、(U+3001, no fullwidth-ASCII-block codepoint so
    _fullwidth_to_halfwidth can't reach it) and the halfwidth "," that
    _fullwidth_to_halfwidth just produced from "，" into one canonical halfwidth comma.
    Judgment call (spec's one-liner doesn't say which direction "统一" goes) -- flagged
    to the user alongside the chapter-trial run for confirmation; easy to flip to
    "unify upward to fullwidth ，" instead if that reads better once seen on real text."""
    return text.replace("、", ",").replace("，", ",")


def _strip_junk_lines(text: str) -> str:
    def is_junk(ln: str) -> bool:
        if any(r.match(ln) for r in _JUNK_LINE_RES):
            return True
        return len(ln) <= _SHORT_LINE_MAX and any(r.match(ln) for r in _JUNK_LINE_RES_SHORT)

    lines = text.split("\n")
    kept = [ln for ln in lines if not is_junk(ln.strip())]
    return "\n".join(kept)


def _collapse_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(ln.strip() for ln in text.split("\n"))
    return text.strip()


def normalize(text: str) -> str:
    if not text:
        return text

    # Guard "癥瘕" before step 1: opencc's t2s dictionary maps 癥->症 on its own (verified
    # empirically), so the exception has to survive t2s, not just our own variant table.
    text = text.replace("癥瘕", _ZHENGJIA_GUARD)

    text = _T2S.convert(text)  # 1. 繁体转简体

    table = _variant_table()  # 2. 异体字/通假字
    text = "".join(table.get(ch, ch) for ch in text)

    text = text.replace(_ZHENGJIA_GUARD, "癥瘕")

    text = _fullwidth_to_halfwidth(text)  # 3. 标点/空白
    text = _unify_separators(text)
    text = _strip_junk_lines(text)
    text = _collapse_whitespace(text)

    text = "".join(UNIT_CHAR_MAP.get(ch, ch) for ch in text)  # 4. 单位规范

    return text
