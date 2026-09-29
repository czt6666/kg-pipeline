"""Step 2 of the preprocess layer: 文言翻译 + 指代消解 + 实体对齐, one LLM call per
*document* (not per paragraph). A "doc" here is already a properly-sized textbook
chunk (courtesy of build_tcm.py / build_tcm_generic.py's chunking, e.g. one disease's
辨证论治 section) -- sending it whole in a single call lets the model resolve
references ("本方"/"诸药"/承前省略的主语) using the real surrounding context instead of
us hand-tracking state (代表方 etc.) across separate per-paragraph calls, which was
both more complex and a source of bugs (see git history: a regex that tracked the
current 方剂 name across paragraphs once picked up a trailing "加减" and injected
"XX方加减" into a later sentence's inferred subject, producing "加减加党参" nonsense --
gone now that there's no cross-call context-injection to get wrong).

See preprocess/prompts/simplify_system.md, the single source of truth for what the
model does; this module only builds the whole-doc prompt and stores the result.

Reuses existing infra rather than inventing new plumbing:
  - LLMClient (src/llm_client.py) for the HTTP call, its network-level retry/backoff, and
    its sha256(model+prompt+temperature+max_tokens)-keyed disk cache -- pointed at
    data/work/{dataset}/{split}/cache/simplify/ instead of the stage1 llm_cache/ dir.
  - common.read_jsonl/write_jsonl/work_dir, common.load_config.
  - retry-with-error-appended pattern from stage1_extract.py, but the only thing that
    counts as a failure here is an empty response -- there's no structured schema to
    validate against (whole-paragraph/whole-doc output, not JSON).

Idempotent + resumable: like stage1_extract.py, every run reprocesses every input doc,
but a cache hit is a disk read, so re-running after a crash (or just to pick up new
docs) is fast and produces byte-identical output for already-cached docs
(temperature=0).

Context line: simplify_system.md expects an optional first input line
"上下文：疾病=X" to help it resolve "本病" etc. when the doc's own text doesn't spell the
disease name out again in every paragraph. It comes from the doc's own
"所属疾病：X"/"所属章节：X" metadata line (stage0 prepends it; this module reads it back
out and strips it from the body instead of sending it to the LLM as if it were prose).

Output (data/work/{dataset}/{split}/simplified.jsonl), one row per doc:
  {doc_id, title, book, section, context, original_text, normalized_text, simplified_text}
  simplified_text is "" iff the LLM never returned a non-empty response after retries.
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import load_config, read_jsonl, work_dir, write_jsonl  # noqa: E402
from llm_client import LLMClient  # noqa: E402

from normalize import normalize  # noqa: E402

from concurrent.futures import ThreadPoolExecutor, as_completed

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_METADATA_PREFIX_RE = re.compile(r"^所属(?:疾病|章节)[:：](.+)$")
_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|```$")

_SYSTEM_PROMPT = (PROMPTS_DIR / "simplify_system.md").read_text(encoding="utf-8")


def doc_context_and_body(doc_text: str) -> tuple[str | None, str]:
    """Splits off stage0's synthetic "所属疾病：X"/"所属章节：X" prefix line (if
    present) from the rest of the doc text. Returns (context_label_or_None, body),
    where body is the remaining paragraphs rejoined on blank lines -- paragraph breaks
    are kept (not flattened) so the model can see and preserve the original
    structure, but the whole body goes into a single prompt/call."""
    paras = [p.strip() for p in doc_text.split("\n\n") if p.strip()]
    if paras and _METADATA_PREFIX_RE.match(paras[0]):
        label = _METADATA_PREFIX_RE.match(paras[0]).group(1).strip()
        return label, "\n\n".join(paras[1:])
    return None, "\n\n".join(paras)


def build_prompt(body_text: str, context: str | None) -> str:
    input_block = f"上下文：疾病={context}\n{body_text}" if context else body_text
    return (
        _SYSTEM_PROMPT
        + "\n\n## 待处理正文\n\n输入：\n\n" + input_block + "\n\n输出：\n\n"
        "只输出改写后的正文文本本身，保持与输入相同的段落（空行）结构，不要任何前后说明、不要代码围栏。"
    )


def _clean(raw_text: str) -> str:
    text = (raw_text or "").strip()
    text = _CODE_FENCE_RE.sub("", text).strip()
    return text


def simplify_doc(client: LLMClient, body_text: str, context: str | None, max_tokens: int,
                  max_retries: int, retry_base_delay_s: float) -> str:
    """Returns simplified_text, or "" if every attempt came back empty."""
    prompt = build_prompt(body_text, context)
    for attempt in range(max_retries + 1):
        record = client.chat(prompt, max_tokens=max_tokens)
        text = _clean(record["response_raw"])
        if text:
            return text
        # A fresh prompt string (new nudge appended) earns its own cache key, same
        # reasoning as stage1_extract.py's retry -- otherwise a cached empty response
        # would just be replayed forever instead of actually retried.
        prompt = build_prompt(body_text, context) + "\n\n（上一次输出为空，请直接输出改写后的正文文本，不要任何解释或说明。）"
        if attempt < max_retries:
            time.sleep(retry_base_delay_s * (2 ** attempt))
    print(f"  [failed after {max_retries + 1} attempts: empty response] doc body: {body_text[:60]}...",
          file=sys.stderr)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True)
    ap.add_argument("--limit", type=int, default=None, help="only process the first N docs (e.g. one chapter for a trial run)")
    ap.add_argument("--workers", type=int, default=None, help="overrides preprocess.workers in config.yaml")
    args = ap.parse_args()

    cfg = load_config()["preprocess"]
    workers = args.workers or cfg["workers"]
    max_retries = cfg["max_retries"]
    retry_base_delay_s = cfg["retry_base_delay_s"]
    max_tokens = cfg["max_output_tokens"]

    wd = work_dir(args.dataset, args.split)
    docs = list(read_jsonl(wd / "docs.jsonl"))
    if args.limit:
        docs = docs[: args.limit]

    client = LLMClient(wd / "cache" / "simplify")

    units = []  # (doc, context, normalized_body, raw_body)
    for doc in docs:
        context, raw_body = doc_context_and_body(doc["text"])
        units.append((doc, context, normalize(raw_body), raw_body))

    def process(unit):
        doc, context, norm_body, raw_body = unit
        simplified = simplify_doc(client, norm_body, context, max_tokens, max_retries, retry_base_delay_s)
        return doc, context, raw_body, norm_body, simplified

    doc_rows = []
    n_failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(process, u) for u in units]
        done = 0
        for fut in as_completed(futures):
            doc, context, raw_body, norm_body, simplified = fut.result()
            doc_rows.append({
                "doc_id": doc["doc_id"], "title": doc.get("title"), "book": doc.get("book"),
                "section": doc.get("section"), "context": context,
                "original_text": raw_body, "normalized_text": norm_body,
                "simplified_text": simplified,
            })
            if not simplified:
                n_failed += 1
            done += 1
            if done % 20 == 0 or done == len(units):
                print(f"  {done}/{len(units)} docs", file=sys.stderr)

    doc_order = {d["doc_id"]: i for i, d in enumerate(docs)}
    doc_rows.sort(key=lambda r: doc_order[r["doc_id"]])

    write_jsonl(wd / "simplified.jsonl", doc_rows)
    stale = wd / "paragraphs.jsonl"
    if stale.exists():
        stale.unlink()  # obsolete per-paragraph output format, superseded by simplified.jsonl above

    ok_rows = [r for r in doc_rows if r["simplified_text"]]
    len_ratio = (sum(len(r["simplified_text"]) for r in ok_rows) / sum(len(r["normalized_text"]) for r in ok_rows)) if ok_rows else 0.0
    print(f"\n docs: {len(docs)}")
    print(f" output/input char length ratio: {len_ratio:.2f}")
    print(f" docs with empty output after retries: {n_failed}")
    print(f"\nwrote {wd/'simplified.jsonl'}")


if __name__ == "__main__":
    main()
