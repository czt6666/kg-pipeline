"""Visualization backend: serves the KG data + retrieval endpoints and the static frontend.

The frontend is a Vite+React SPA in web/ (source in web/src/); this only serves its
built output (web/dist/, produced by `npm run build`). For frontend dev with hot
reload, run `npm run dev` in web/ instead — it proxies /api/* to this server.

Run:  .venv/bin/python src/serve.py --port 8787
Then open http://localhost:8787

Debug-view endpoints (per-doc, per-split):
  GET  /                              -> web/index.html
  GET  /api/datasets                   -> available {dataset, split} with doc counts
  GET  /api/docs?dataset=&split=&q=    -> doc list (id + text preview)
  GET  /api/doc/<dataset>/<split>/<doc_id> -> {text, mentions, nodes, edges}

Merged-graph endpoints (cross-document; a dataset may hold more than one independently-merged
graph, e.g. TCM's merged_neike/merged_jichu/merged_zhenduan -- one per source book -- alongside
or instead of a plain "merged" dir. <merge> is the data/work/{dataset}/ subdirectory name; it
defaults to "merged" when omitted, so single-graph datasets (docred, genwiki) keep working
unchanged with the old 4-segment URLs):
  GET  /api/merged                            -> [{dataset, merge, n_nodes, n_edges, n_docs, ...}]
  GET  /api/merged/<dataset>[/<merge>]           -> {stats, nodes, edges} (full graph)
  GET  /api/merged/<dataset>[/<merge>]/node/<entity_id> -> node detail + provenance {sources:[...]}
  GET  /api/merged/<dataset>[/<merge>]/doc/<doc_id>     -> full per-doc extraction {text,mentions,nodes,edges,split}

Hybrid retrieval endpoints (src/retrieval/pipeline.py -- agent-facing entity lookup: a
precise TCM term in, ranked facts + a subgraph + readable text out; see
docs/retrieval_graph_patterns.md for the graph-pattern design. This is the only search
path left in the app -- the old dual/triple-path debug-view search (`/api/search`,
`/api/merged/.../search`, backed by src/retrieval/basic.py) was retired in favor of it):
  GET  /api/retrieval/search?dataset=&merge=&term=&top_k=&expand=   -> {term, candidates,
                                 resolved}; expand=0 skips graph-pattern search entirely
                                 and returns resolved:null (candidates only, for a plain
                                 "jump to this entity" search box). `resolved.summary` is
                                 always null here -- deliberately LLM-free/synchronous, see
                                 /api/retrieval/summary below.
  GET  /api/retrieval/expand?dataset=&merge=&entity_id=&top_k= -> expand_entity() output
                                 (`summary` always null), for drilling into a
                                 disambiguation candidate other than the top one `search`
                                 already expanded
  GET  /api/retrieval/summary?dataset=&merge=&entity_id=&top_k= -> {entity_id, summary}
                                 -- the one LLM call in this module (a few seconds), split
                                 out from search/expand so the UI can render facts/subgraph
                                 immediately and fetch this afterward instead of blocking
                                 the whole panel on it. `summary` is null if the entity
                                 doesn't exist or the LLM call fails; caller falls back to
                                 the template-rendered `text` from expand/search.

Eval-benchmark endpoints (repo-root eval/, not data/work/ -- the TCM neike round-loop's
100-question benchmark and its per-graph-version results, see PROGRESS.md/versions.md):
  GET  /api/eval/runs        -> [{name, label, n, hits, hit_rate, by_type}] one per
                                 eval/baseline_results_<name>.jsonl, in versions.md order
  GET  /api/eval/run/<name>  -> [{id, type, question, answer, evidence, hit, retrieved}]
                                 (questions.jsonl joined with that run's results by id)

Prompt-viewer endpoints (prompts/*.txt -- the generated files stage1_extract.py actually
sends the model, see CLAUDE.md "硬性规则" on why these are generated, not hand-edited):
  GET  /api/prompts        -> [{name, size, mtime}]
  GET  /api/prompts/<name> -> {name, content}

Preprocess-review endpoints (data/work/{dataset}/{split}/simplified.jsonl, produced by
preprocess/simplify.py -- one row per doc (whole-doc LLM call, not per-paragraph); see
that module's docstring for the file schema):
  GET  /api/preprocess/splits                      -> [{dataset, split, n_docs}]
  GET  /api/preprocess/docs?dataset=&split=         -> [{doc_id, title}]
  GET  /api/preprocess/doc/<dataset>/<split>/<doc_id> -> {doc_id, title, context,
                                                         original_text, normalized_text,
                                                         simplified_text}

OCR-review endpoints (data/work/{dataset}/{split}/ocr_pages.jsonl, produced by
src/stage0_ocr.py -- one row per source PDF page, {page_index, text}):
  GET  /api/ocr/splits                       -> [{dataset, split, n_pages}]
  GET  /api/ocr/pages?dataset=&split=        -> [{page_index, preview}]
  GET  /api/ocr/page/<dataset>/<split>/<page_index> -> {page_index, text}

Route handlers below are plain functions (qs/path pieces in, an ApiResult out) with no
knowledge of http.server -- Handler.do_GET is only a dispatch table + a thin adapter that
writes the response. This keeps each endpoint's data logic testable/readable on its own
and keeps the one place that knows about sockets/headers (Handler) from also having to
know about jsonl schemas.
"""
import argparse
import json
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from common import REPO_ROOT, read_jsonl, work_dir
from llm_client import LLMError
from retrieval.pipeline import expand_entity, generate_summary, hybrid_search

WEB_DIR = REPO_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
DOC_LIST_LIMIT = 1234
EVAL_DIR = REPO_ROOT / "eval"
PROMPTS_DIR = REPO_ROOT / "prompts"
# Display order for eval runs -- matches the round-loop story in versions.md (v0 baseline,
# then each round's attempt in order) rather than alphabetical/mtime, which wouldn't convey
# "this is the sequence rounds happened in."
EVAL_RUN_ORDER = ["v0", "v1_boundaryfix", "v2_retrybudget", "v3_zhengsuffix", "v4_surgical"]

CONTENT_TYPES = {
    ".html": "text/html", ".js": "application/javascript", ".css": "text/css",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".json": "application/json", ".ico": "image/x-icon", ".woff2": "font/woff2",
}


@dataclass
class ApiResult:
    status: int
    body: Any


def _json(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _load_work(dataset, split):
    wd = work_dir(dataset, split)
    if not (wd / "nodes.jsonl").exists():
        return None
    return wd


def _merged_dir(dataset, merge="merged"):
    wd = work_dir(dataset, merge)
    if not (wd / "nodes.jsonl").exists():
        return None
    return wd


def _list_merged_graphs():
    """(dataset, merge_dir_name) for every data/work/{dataset}/merged* dir that has a
    finished nodes.jsonl -- a dataset may hold several independently-merged graphs
    (e.g. TCM's merged_neike/merged_jichu/merged_zhenduan, one per source book)."""
    root = REPO_ROOT / "data" / "work"
    out = []
    if not root.exists():
        return out
    for dataset_dir in sorted(root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        for sub in sorted(dataset_dir.iterdir()):
            if not sub.is_dir() or not sub.name.startswith("merged"):
                continue
            if (sub / "nodes.jsonl").exists():
                out.append((dataset_dir.name, sub.name))
    return out


MERGED_SUBPATHS = {"node", "doc"}


def _parse_merged_path(seg):
    """seg = path.split('/'); seg[:3] == ['', 'api', 'merged']. <merge> is optional in the
    URL and defaults to 'merged' -- distinguished from a sub-endpoint keyword by membership
    in MERGED_SUBPATHS, so old 4/5-segment URLs (single-graph datasets) keep working
    unchanged. Returns (dataset, merge, sub, rest) or None if seg is too short."""
    if len(seg) < 4:
        return None
    dataset = seg[3]
    rest = seg[4:]
    if not rest:
        return dataset, "merged", None, []
    if rest[0] in MERGED_SUBPATHS:
        return dataset, "merged", rest[0], rest[1:]
    merge = rest[0]
    rest = rest[1:]
    if not rest:
        return dataset, merge, None, []
    return dataset, merge, rest[0], rest[1:]


def _list_datasets():
    """Dataset names = subdirectories of data/work/, discovered dynamically so adding a
    new dataset never requires a code change here."""
    root = REPO_ROOT / "data" / "work"
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


_ROUND_ARTIFACT_RE = re.compile(r"_r\d+$")


def _is_internal_split(name: str) -> bool:
    """True for split directories that are raw intermediate artifacts, not a real
    dataset a user should pick from a dropdown: merged-graph output dirs (already
    surfaced through the dedicated /api/merged/* endpoints) and the per-round scratch
    splits scripts/extract_multiround.py writes (…_r0, …_r1, … -- each is just one
    round's raw extraction_valid.jsonl with no nodes.jsonl/graph of its own; the actual
    usable result is the sibling split merge/pipeline.py writes without the _rN suffix)."""
    return name.startswith("merged") or bool(_ROUND_ARTIFACT_RE.search(name))


def _snippet(text, names, width=200):
    """Window around the first occurrence of any surface name, else text head."""
    low = text.lower()
    best = None
    for nm in names:
        i = low.find(nm.lower())
        if i != -1:
            best = i if best is None else min(best, i)
    if best is None:
        return text[:width]
    start = max(0, best - width // 3)
    end = min(len(text), best + width)
    s = text[start:end]
    return ("…" if start > 0 else "") + s + ("…" if end < len(text) else "")


# ---- debug-view endpoints ----

def get_datasets(qs):
    out = []
    for dataset in _list_datasets():
        base = REPO_ROOT / "data" / "work" / dataset
        if not base.exists():
            continue
        for split_dir in sorted(base.iterdir()):
            if not split_dir.is_dir() or _is_internal_split(split_dir.name):
                continue
            n_docs = sum(1 for _ in read_jsonl(split_dir / "docs.jsonl"))
            if n_docs == 0:
                continue
            # Splits are often only partially processed (e.g. a handful of docs
            # run through stage1 extraction as a smoke test) — surface that count
            # so the UI can warn instead of silently showing empty results.
            n_extracted = len({n["doc_id"] for n in read_jsonl(split_dir / "nodes.jsonl")})
            out.append({"dataset": dataset, "split": split_dir.name, "n_docs": n_docs, "n_extracted": n_extracted})
    return ApiResult(200, out)


def get_docs(qs):
    dataset, split = qs.get("dataset", ["docred"])[0], qs.get("split", ["eval200"])[0]
    wd = work_dir(dataset, split)
    q = (qs.get("q", [""])[0] or "").lower()
    extracted_ids = {n["doc_id"] for n in read_jsonl(wd / "nodes.jsonl")}
    rows = []
    for d in read_jsonl(wd / "docs.jsonl"):
        if q and q not in d["text"].lower():
            continue
        rows.append({
            "doc_id": d["doc_id"], "preview": d["text"][:160],
            "has_extraction": d["doc_id"] in extracted_ids,
        })
    # Docs with extraction results are usually a small minority of a split
    # (extraction is run incrementally) — put them first so they aren't
    # buried under hundreds of not-yet-processed docs.
    rows.sort(key=lambda r: not r["has_extraction"])
    return ApiResult(200, rows[:DOC_LIST_LIMIT])


def get_doc(dataset, split, doc_id):
    wd = work_dir(dataset, split)
    docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
    if doc_id not in docs:
        return ApiResult(404, {"error": "doc not found"})
    mentions = [m for m in read_jsonl(wd / "mentions.jsonl") if m["doc_id"] == doc_id]
    nodes = [n for n in read_jsonl(wd / "nodes.jsonl") if n["doc_id"] == doc_id]
    edges = [e for e in read_jsonl(wd / "edges.jsonl") if e["doc_id"] == doc_id]
    return ApiResult(200, {
        "doc_id": doc_id, "text": docs[doc_id]["text"],
        "mentions": mentions, "nodes": nodes, "edges": edges,
    })


# ---- merged-graph endpoints ----

def get_merged_list(qs):
    out = []
    for dataset, merge in _list_merged_graphs():
        wd = work_dir(dataset, merge)
        stats = json.loads((wd / "stats.json").read_text()) if (wd / "stats.json").exists() else {}
        out.append({"dataset": dataset, "merge": merge, **stats})
    return ApiResult(200, out)


def get_merged_graph(dataset, merge, wd):
    stats = json.loads((wd / "stats.json").read_text()) if (wd / "stats.json").exists() else {}
    nodes = list(read_jsonl(wd / "nodes.jsonl"))
    edges = list(read_jsonl(wd / "edges.jsonl"))
    return ApiResult(200, {"dataset": dataset, "merge": merge, "stats": stats, "nodes": nodes, "edges": edges})


def get_retrieval_search(qs):
    dataset = qs.get("dataset", ["TCM"])[0]
    merge = qs.get("merge", ["merged_neike"])[0]
    term = qs.get("term", [""])[0].strip()
    top_k = int(qs.get("top_k", ["10"])[0])
    # expand=0 skips graph-pattern search + LLM summarization, for callers (e.g.
    # GraphExplorer's "find an entity to jump to" search box) that only need candidates.
    expand = qs.get("expand", ["1"])[0] != "0"
    if not term:
        return ApiResult(400, {"error": "missing term"})
    try:
        result = hybrid_search(dataset, merge, term, top_k=top_k, expand=expand)
    except LLMError as e:
        return ApiResult(500, {"error": f"embedding request failed: {e}"})
    return ApiResult(200, result)


def get_retrieval_expand(qs):
    dataset = qs.get("dataset", ["TCM"])[0]
    merge = qs.get("merge", ["merged_neike"])[0]
    entity_id = qs.get("entity_id", [""])[0]
    top_k = int(qs.get("top_k", ["10"])[0])
    if not entity_id:
        return ApiResult(400, {"error": "missing entity_id"})
    wd = work_dir(dataset, merge)
    expanded = expand_entity(wd, entity_id, top_k=top_k)
    if expanded is None:
        return ApiResult(404, {"error": "entity not found"})
    return ApiResult(200, expanded)


def get_retrieval_summary(qs):
    dataset = qs.get("dataset", ["TCM"])[0]
    merge = qs.get("merge", ["merged_neike"])[0]
    entity_id = qs.get("entity_id", [""])[0]
    top_k = int(qs.get("top_k", ["10"])[0])
    if not entity_id:
        return ApiResult(400, {"error": "missing entity_id"})
    wd = work_dir(dataset, merge)
    try:
        summary = generate_summary(wd, entity_id, top_k=top_k)
    except LLMError as e:
        return ApiResult(500, {"error": f"summary request failed: {e}"})
    return ApiResult(200, {"entity_id": entity_id, "summary": summary})


def post_agent_chat(body):
    """POST /api/agent/chat -- one turn of the TCM agent loop. Stateless: the client sends
    the full message history; the last message must be the new user turn. Prior messages
    seed the transcript (the loop re-understands from the transcript each turn). Returns
    {action, reply}; pass debug:true to also get the per-stage trace for inspection.

    Body: {messages:[{role,content}], dataset?, merge?, max_rounds?, debug?}."""
    from agent import TCMAgent  # lazy: keep the agent package off serve.py's import path cost

    messages = body.get("messages") or []
    if not messages or messages[-1].get("role") != "user":
        return ApiResult(400, {"error": "messages must be non-empty and end with a user turn"})
    try:
        agent, state = TCMAgent.build(
            dataset=body.get("dataset"), merge=body.get("merge"),
            max_ask_rounds=int(body.get("max_rounds", 3)),
        )
    except FileNotFoundError as e:
        return ApiResult(404, {"error": f"unknown dataset/merge: {e}"})
    # Seed prior turns; run_turn appends the new user message itself.
    state.conversation = [{"role": m["role"], "content": m["content"]} for m in messages[:-1]]
    try:
        result = agent.run_turn(state, messages[-1]["content"])
    except LLMError as e:
        return ApiResult(502, {"error": f"llm/retrieval failed: {e}"})
    return ApiResult(200, result.to_dict(include_trace=bool(body.get("debug"))))


def get_merged_node(wd, entity_id):
    nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
    node = nodes.get(entity_id)
    if not node:
        return ApiResult(404, {"error": "node not found"})
    docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
    names = [node["name"]] + list(node.get("aliases") or [])
    sources = []
    for doc_id in node.get("source_doc_ids", []):
        d = docs.get(doc_id)
        if not d:
            continue
        sources.append({
            "doc_id": doc_id,
            "title": d.get("title", ""),
            "snippet": _snippet(d.get("text", ""), names),
        })
    return ApiResult(200, {**node, "sources": sources})


def get_merged_doc(dataset, wd, doc_id):
    """/api/merged/<dataset>[/<merge>]/doc/<doc_id> -> full per-doc extraction
    (text/mentions/nodes/edges), so the merged-graph "sources" list can drill into the
    original document the same way the debug view does."""
    docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
    drec = docs.get(doc_id)
    if not drec:
        return ApiResult(404, {"error": "doc not found"})
    split = drec.get("split")
    if not split:
        base = REPO_ROOT / "data" / "work" / dataset
        for d in (sorted(base.iterdir()) if base.exists() else []):
            if not d.is_dir() or _is_internal_split(d.name):
                continue
            if any(x["doc_id"] == doc_id for x in read_jsonl(d / "docs.jsonl")):
                split = d.name
                break
    if not split:
        return ApiResult(404, {"error": "source split not found"})
    swd = work_dir(dataset, split)
    mentions = [m for m in read_jsonl(swd / "mentions.jsonl") if m["doc_id"] == doc_id]
    nodes = [n for n in read_jsonl(swd / "nodes.jsonl") if n["doc_id"] == doc_id]
    edges = [e for e in read_jsonl(swd / "edges.jsonl") if e["doc_id"] == doc_id]
    return ApiResult(200, {
        "doc_id": doc_id, "split": split, "title": drec.get("title", ""),
        "text": drec.get("text", ""), "mentions": mentions, "nodes": nodes, "edges": edges,
    })


def route_merged(seg, qs):
    """Dispatches every /api/merged/... URL except the bare listing (handled directly in
    do_GET). Mirrors the original nested-if structure of _parse_merged_path's contract."""
    dataset, merge, sub, rest = _parse_merged_path(seg)
    wd = _merged_dir(dataset, merge)
    if not wd:
        return ApiResult(404, {"error": f"no merged graph for {dataset}/{merge}"})

    if sub is None:
        return get_merged_graph(dataset, merge, wd)
    if sub == "node":
        return get_merged_node(wd, unquote(rest[0]))
    if sub == "doc":
        return get_merged_doc(dataset, wd, unquote(rest[0]))
    return ApiResult(404, {"error": "not found"})


# ---- eval-benchmark endpoints ----

def get_eval_runs(qs):
    names = [f.stem.replace("baseline_results_", "", 1)
             for f in EVAL_DIR.glob("baseline_results_*.jsonl")]
    # Known rounds first in their natural order, then anything unrecognized (e.g. a future
    # round) appended so new runs still show up without a code change.
    ordered = [n for n in EVAL_RUN_ORDER if n in names] + sorted(n for n in names if n not in EVAL_RUN_ORDER)

    out = []
    for name in ordered:
        results = list(read_jsonl(EVAL_DIR / f"baseline_results_{name}.jsonl"))
        if not results:
            continue
        by_type = {}
        for r in results:
            slot = by_type.setdefault(r["type"], {"hits": 0, "n": 0})
            slot["n"] += 1
            slot["hits"] += 1 if r["hit"] else 0
        for slot in by_type.values():
            slot["rate"] = slot["hits"] / slot["n"] if slot["n"] else 0
        hits = sum(1 for r in results if r["hit"])
        out.append({
            "name": name, "label": "v0 (baseline)" if name == "v0" else name,
            "n": len(results), "hits": hits,
            "hit_rate": hits / len(results) if results else 0,
            "by_type": by_type,
        })
    return ApiResult(200, out)


def get_eval_run_detail(name):
    results_path = EVAL_DIR / f"baseline_results_{name}.jsonl"
    if not results_path.exists():
        return ApiResult(404, {"error": f"no eval run named {name}"})
    questions = {q["id"]: q for q in read_jsonl(EVAL_DIR / "questions.jsonl")}
    out = []
    for r in read_jsonl(results_path):
        q = questions.get(r["id"], {})
        out.append({
            "id": r["id"], "type": r["type"], "question": q.get("question"),
            "answer": q.get("answer"), "evidence": q.get("evidence"),
            "hit": r["hit"], "retrieved": r["retrieved"],
        })
    return ApiResult(200, out)


# ---- prompt-viewer endpoints ----

def get_prompts(qs):
    if not PROMPTS_DIR.exists():
        return ApiResult(200, [])
    out = []
    for f in sorted(PROMPTS_DIR.glob("*.txt")):
        st = f.stat()
        out.append({"name": f.name, "size": st.st_size, "mtime": st.st_mtime})
    return ApiResult(200, out)


def get_prompt(name):
    path = PROMPTS_DIR / name
    if path.suffix != ".txt" or PROMPTS_DIR not in path.resolve().parents or not path.exists():
        return ApiResult(404, {"error": "prompt not found"})
    return ApiResult(200, {"name": name, "content": path.read_text(encoding="utf-8")})


# ---- preprocess-review endpoints ----

def _list_preprocess_splits():
    """(dataset, split) for every data/work/{dataset}/{split}/ that has run
    preprocess/simplify.py (simplified.jsonl present)."""
    root = REPO_ROOT / "data" / "work"
    out = []
    if not root.exists():
        return out
    for dataset_dir in sorted(root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        for split_dir in sorted(dataset_dir.iterdir()):
            if not split_dir.is_dir() or _is_internal_split(split_dir.name):
                continue
            if (split_dir / "simplified.jsonl").exists():
                out.append((dataset_dir.name, split_dir.name))
    return out


def get_preprocess_splits(qs):
    out = []
    for dataset, split in _list_preprocess_splits():
        wd = work_dir(dataset, split)
        rows = list(read_jsonl(wd / "simplified.jsonl"))
        out.append({"dataset": dataset, "split": split, "n_docs": len(rows)})
    return ApiResult(200, out)


def get_preprocess_docs(qs):
    dataset, split = qs.get("dataset", [""])[0], qs.get("split", [""])[0]
    wd = work_dir(dataset, split)
    if not (wd / "simplified.jsonl").exists():
        return ApiResult(404, {"error": "no preprocess output for this split"})
    rows = [{"doc_id": r["doc_id"], "title": r.get("title")} for r in read_jsonl(wd / "simplified.jsonl")]
    return ApiResult(200, rows)


def get_preprocess_doc(dataset, split, doc_id):
    wd = work_dir(dataset, split)
    row = next((r for r in read_jsonl(wd / "simplified.jsonl") if r["doc_id"] == doc_id), None)
    if row is None:
        return ApiResult(404, {"error": "doc not found"})
    return ApiResult(200, row)


# ---- OCR-review endpoints ----

def _list_ocr_splits():
    """(dataset, split) for every data/work/{dataset}/{split}/ that has run stage0_ocr.py
    (ocr_pages.jsonl present)."""
    root = REPO_ROOT / "data" / "work"
    out = []
    if not root.exists():
        return out
    for dataset_dir in sorted(root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        for split_dir in sorted(dataset_dir.iterdir()):
            if not split_dir.is_dir() or _is_internal_split(split_dir.name):
                continue
            if (split_dir / "ocr_pages.jsonl").exists():
                out.append((dataset_dir.name, split_dir.name))
    return out


def get_ocr_splits(qs):
    out = []
    for dataset, split in _list_ocr_splits():
        wd = work_dir(dataset, split)
        rows = list(read_jsonl(wd / "ocr_pages.jsonl"))
        out.append({"dataset": dataset, "split": split, "n_pages": len(rows)})
    return ApiResult(200, out)


def get_ocr_pages(qs):
    dataset, split = qs.get("dataset", [""])[0], qs.get("split", [""])[0]
    wd = work_dir(dataset, split)
    if not (wd / "ocr_pages.jsonl").exists():
        return ApiResult(404, {"error": "no OCR output for this split"})
    rows = [{"page_index": r["page_index"], "preview": r.get("text", "")[:80]}
            for r in read_jsonl(wd / "ocr_pages.jsonl")]
    return ApiResult(200, rows)


def get_ocr_page(dataset, split, page_index):
    wd = work_dir(dataset, split)
    row = next((r for r in read_jsonl(wd / "ocr_pages.jsonl") if str(r["page_index"]) == str(page_index)), None)
    if row is None:
        return ApiResult(404, {"error": "page not found"})
    return ApiResult(200, row)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_api(self, result: ApiResult):
        return self._send(result.status, _json(result.body))

    def do_OPTIONS(self):
        # CORS preflight for the POST agent endpoint (frontend dev server is a different origin).
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send(400, _json({"error": "invalid JSON body"}))

        if parsed.path == "/api/agent/chat":
            return self._send_api(post_agent_chat(body))

        return self._send(404, _json({"error": "not found"}))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        seg = path.split("/")  # ['', 'api', 'merged', 'genwiki', 'node', 'm#5']

        if path == "/" or path == "/index.html":
            return self._serve_file(DIST_DIR / "index.html", "text/html")

        if path == "/api/datasets":
            return self._send_api(get_datasets(qs))

        if path == "/api/docs":
            return self._send_api(get_docs(qs))

        if path.startswith("/api/doc/"):
            _, _, _, dataset, split, doc_id = path.split("/", 5)
            return self._send_api(get_doc(dataset, split, doc_id))

        if path == "/api/merged":
            return self._send_api(get_merged_list(qs))

        if len(seg) >= 3 and seg[1] == "api" and seg[2] == "merged":
            return self._send_api(route_merged(seg, qs))

        if path == "/api/retrieval/search":
            return self._send_api(get_retrieval_search(qs))

        if path == "/api/retrieval/expand":
            return self._send_api(get_retrieval_expand(qs))

        if path == "/api/retrieval/summary":
            return self._send_api(get_retrieval_summary(qs))

        if path == "/api/eval/runs":
            return self._send_api(get_eval_runs(qs))

        if path.startswith("/api/eval/run/"):
            name = unquote(path[len("/api/eval/run/"):])
            return self._send_api(get_eval_run_detail(name))

        if path == "/api/prompts":
            return self._send_api(get_prompts(qs))

        if path.startswith("/api/prompts/"):
            name = unquote(path[len("/api/prompts/"):])
            return self._send_api(get_prompt(name))

        if path == "/api/preprocess/splits":
            return self._send_api(get_preprocess_splits(qs))

        if path == "/api/preprocess/docs":
            return self._send_api(get_preprocess_docs(qs))

        if path.startswith("/api/preprocess/doc/"):
            _, _, _, _, dataset, split, doc_id = path.split("/", 6)
            return self._send_api(get_preprocess_doc(dataset, split, unquote(doc_id)))

        if path == "/api/ocr/splits":
            return self._send_api(get_ocr_splits(qs))

        if path == "/api/ocr/pages":
            return self._send_api(get_ocr_pages(qs))

        if path.startswith("/api/ocr/page/"):
            _, _, _, _, dataset, split, page_index = path.split("/", 6)
            return self._send_api(get_ocr_page(dataset, split, unquote(page_index)))

        # ---- built frontend static assets (web/dist/assets/*.js, *.css, ...) ----
        if not path.startswith("/api/"):
            candidate = DIST_DIR / path.lstrip("/")
            if candidate.is_file() and DIST_DIR in candidate.resolve().parents:
                ctype = CONTENT_TYPES.get(candidate.suffix, "application/octet-stream")
                return self._serve_file(candidate, ctype)

        return self._send(404, _json({"error": "not found"}))

    def _serve_file(self, path: Path, ctype):
        if not path.exists():
            return self._send(404, b"not found", "text/plain")
        body = path.read_bytes()
        return self._send(200, body, ctype)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"serving on http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
