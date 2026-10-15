from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from core.common import PIPELINE_ROOT, REPO_ROOT, read_jsonl, work_dir
from prompting import PromptStore
from .http_utils import ApiResult, JsonHandler
from .kg_server import agent_chat, stream_agent_chat, get_doc as get_graph_doc, get_graph, get_node, list_graphs, retrieval_expand, retrieval_search, retrieval_summary

DIST_DIR = REPO_ROOT / "web" / "dist"
EVAL_DIR = REPO_ROOT / "eval"
DOC_LIST_LIMIT = 500


def _is_internal_split(name: str) -> bool:
    return name.startswith("_")


def _snippet(text: str, names: list[str], radius: int = 60) -> str:
    low = text.lower()
    for name in names:
        idx = low.find(name.lower())
        if idx >= 0:
            start = max(0, idx - radius)
            end = min(len(text), idx + len(name) + radius)
            return text[start:end]
    return text[: radius * 2]


def get_datasets(qs):
    out = []
    for dataset_dir in sorted(PIPELINE_ROOT.iterdir()) if PIPELINE_ROOT.exists() else []:
        splits_root = dataset_dir / "splits"
        if not splits_root.exists():
            continue
        for split_dir in sorted(splits_root.iterdir()):
            if not split_dir.is_dir() or _is_internal_split(split_dir.name):
                continue
            docs_path = split_dir / "docs.jsonl"
            if not docs_path.exists():
                continue
            n_docs = sum(1 for _ in read_jsonl(docs_path))
            if n_docs == 0:
                continue
            n_extracted = len({n["doc_id"] for n in read_jsonl(split_dir / "nodes.jsonl")})
            out.append({"dataset": dataset_dir.name, "split": split_dir.name, "n_docs": n_docs, "n_extracted": n_extracted})
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
        rows.append({"doc_id": d["doc_id"], "preview": d["text"][:160], "has_extraction": d["doc_id"] in extracted_ids})
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
    return ApiResult(200, {"doc_id": doc_id, "text": docs[doc_id]["text"], "mentions": mentions, "nodes": nodes, "edges": edges})


def get_prompts(_qs):
    store = PromptStore()
    rows = []
    for key in store.registry:
        asset = store.resolve(key)
        for name, path in asset.files.items():
            if path.suffix in {".txt", ".md"}:
                rows.append({"name": f"{key}:{name}", "version": asset.version, "path": str(path.relative_to(REPO_ROOT))})
    return ApiResult(200, rows)


def get_prompt(name):
    if ":" not in name:
        return ApiResult(404, {"error": "prompt name must be <key>:<asset>"})
    key, asset_name = name.split(":", 1)
    try:
        asset = PromptStore().resolve(key)
    except KeyError:
        return ApiResult(404, {"error": f"unknown prompt key: {key}"})
    path = asset.files.get(asset_name)
    if not path or not path.exists():
        return ApiResult(404, {"error": "prompt asset not found"})
    return ApiResult(200, {"name": name, "version": asset.version, "content": path.read_text(encoding="utf-8")})


def _list_preprocess_splits():
    out = []
    for dataset_dir in sorted(PIPELINE_ROOT.iterdir()) if PIPELINE_ROOT.exists() else []:
        splits_root = dataset_dir / "splits"
        if not splits_root.exists():
            continue
        for split_dir in sorted(splits_root.iterdir()):
            if (split_dir / "simplified.jsonl").exists():
                out.append({"dataset": dataset_dir.name, "split": split_dir.name})
    return out


def get_preprocess_splits(_qs):
    return ApiResult(200, _list_preprocess_splits())


def get_preprocess_docs(qs):
    dataset = qs.get("dataset", [""])[0]
    split = qs.get("split", [""])[0]
    wd = work_dir(dataset, split)
    rows = [{"doc_id": r["doc_id"], "preview": (r.get("simplified_text") or r.get("original_text") or "")[:120]} for r in read_jsonl(wd / "simplified.jsonl")]
    return ApiResult(200, rows)


def get_preprocess_doc(dataset, split, doc_id):
    wd = work_dir(dataset, split)
    row = next((r for r in read_jsonl(wd / "simplified.jsonl") if r["doc_id"] == doc_id), None)
    return ApiResult(200, row) if row else ApiResult(404, {"error": "doc not found"})


def _list_ocr_splits():
    out = []
    for dataset_dir in sorted(PIPELINE_ROOT.iterdir()) if PIPELINE_ROOT.exists() else []:
        splits_root = dataset_dir / "splits"
        if not splits_root.exists():
            continue
        for split_dir in sorted(splits_root.iterdir()):
            if (split_dir / "ocr_pages.jsonl").exists():
                out.append({"dataset": dataset_dir.name, "split": split_dir.name})
    return out


def get_ocr_splits(_qs):
    return ApiResult(200, _list_ocr_splits())


def get_ocr_pages(qs):
    dataset = qs.get("dataset", [""])[0]
    split = qs.get("split", [""])[0]
    wd = work_dir(dataset, split)
    rows = [{"page_index": r["page_index"], "preview": r.get("text", "")[:80]} for r in read_jsonl(wd / "ocr_pages.jsonl")]
    return ApiResult(200, rows)


def get_ocr_page(dataset, split, page_index):
    wd = work_dir(dataset, split)
    row = next((r for r in read_jsonl(wd / "ocr_pages.jsonl") if str(r["page_index"]) == str(page_index)), None)
    return ApiResult(200, row) if row else ApiResult(404, {"error": "page not found"})


def get_eval_runs(_qs):
    out = []
    for f in sorted(EVAL_DIR.glob("baseline_results_*.jsonl")):
        name = f.stem.replace("baseline_results_", "", 1)
        results = list(read_jsonl(f))
        hits = sum(1 for r in results if r.get("hit"))
        out.append({"name": name, "n": len(results), "hits": hits, "hit_rate": hits / len(results) if results else 0})
    return ApiResult(200, out)


def get_eval_run_detail(name):
    p = EVAL_DIR / f"baseline_results_{name}.jsonl"
    if not p.exists():
        return ApiResult(404, {"error": f"no eval run named {name}"})
    return ApiResult(200, list(read_jsonl(p)))


class BackendHandler(JsonHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self.send_api(ApiResult(400, {"error": "invalid JSON body"}))
        if parsed.path == "/api/kg/agent/chat":
            return self.send_api(agent_chat(body))
        if parsed.path == "/api/kg/agent/chat/stream":
            return stream_agent_chat(self, body)
        return self.send_api(ApiResult(404, {"error": "not found"}))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            return self._serve_file(DIST_DIR / "index.html", "text/html")
        if path == "/api/datasets":
            return self.send_api(get_datasets(qs))
        if path == "/api/docs":
            return self.send_api(get_docs(qs))
        if path.startswith("/api/doc/"):
            _, _, _, dataset, split, doc_id = path.split("/", 5)
            return self.send_api(get_doc(dataset, split, unquote(doc_id)))
        if path == "/api/prompts":
            return self.send_api(get_prompts(qs))
        if path.startswith("/api/prompts/"):
            return self.send_api(get_prompt(unquote(path[len('/api/prompts/'): ])))
        if path == "/api/preprocess/splits":
            return self.send_api(get_preprocess_splits(qs))
        if path == "/api/preprocess/docs":
            return self.send_api(get_preprocess_docs(qs))
        if path.startswith("/api/preprocess/doc/"):
            _, _, _, _, dataset, split, doc_id = path.split("/", 6)
            return self.send_api(get_preprocess_doc(dataset, split, unquote(doc_id)))
        if path == "/api/ocr/splits":
            return self.send_api(get_ocr_splits(qs))
        if path == "/api/ocr/pages":
            return self.send_api(get_ocr_pages(qs))
        if path.startswith("/api/ocr/page/"):
            _, _, _, _, dataset, split, page_index = path.split("/", 6)
            return self.send_api(get_ocr_page(dataset, split, unquote(page_index)))
        if path == "/api/eval/runs":
            return self.send_api(get_eval_runs(qs))
        if path.startswith("/api/eval/run/"):
            return self.send_api(get_eval_run_detail(unquote(path[len('/api/eval/run/'): ])))
        if path == "/api/kg/merged":
            return self.send_api(list_graphs(qs))
        seg = path.split("/")
        if len(seg) >= 6 and seg[1] == "api" and seg[2] == "kg" and seg[3] == "merged":
            dataset, merge = seg[4], seg[5]
            if len(seg) == 6:
                return self.send_api(get_graph(dataset, merge))
            if len(seg) >= 8 and seg[6] == "node":
                return self.send_api(get_node(dataset, merge, unquote(seg[7])))
            if len(seg) >= 8 and seg[6] == "doc":
                return self.send_api(get_graph_doc(dataset, merge, unquote(seg[7])))
        if path == "/api/kg/retrieval/search":
            return self.send_api(retrieval_search(qs))
        if path == "/api/kg/retrieval/expand":
            return self.send_api(retrieval_expand(qs))
        if path == "/api/kg/retrieval/summary":
            return self.send_api(retrieval_summary(qs))

        if path.startswith("/assets/"):
            return self._serve_file(DIST_DIR / path.lstrip("/"), mimetypes.guess_type(path)[0] or "application/octet-stream")
        return self._serve_file(DIST_DIR / "index.html", "text/html")

    def _serve_file(self, path: Path, ctype: str):
        if not path.exists():
            return self.send_bytes(404, b"not found", "text/plain")
        return self.send_bytes(200, path.read_bytes(), ctype)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=53785)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), BackendHandler)
    print(f"backend server listening on http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
