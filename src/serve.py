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
  GET  /api/search?dataset=&split=&q=  -> {semantic:{nodes,passages}, lexical, graph}

Merged-graph endpoints (cross-document, one graph per dataset):
  GET  /api/merged                     -> [{dataset, n_nodes, n_edges, n_docs, ...}]
  GET  /api/merged/<dataset>           -> {stats, nodes, edges} (full graph)
  GET  /api/merged/<dataset>/search?q=&top_k= -> {semantic:[...], lexical:[...]}
  GET  /api/merged/<dataset>/node/<entity_id> -> node detail + provenance {sources:[...]}
  GET  /api/merged/<dataset>/doc/<doc_id>     -> full per-doc extraction {text,mentions,nodes,edges,split}
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from common import REPO_ROOT, read_jsonl, work_dir
from llm_client import LLMClient
from retrieval import graph_search, lexical_search, semantic_search

WEB_DIR = REPO_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
DOC_LIST_LIMIT = 1234

CONTENT_TYPES = {
    ".html": "text/html", ".js": "application/javascript", ".css": "text/css",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".json": "application/json", ".ico": "image/x-icon", ".woff2": "font/woff2",
}


def _json(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _load_work(dataset, split):
    wd = work_dir(dataset, split)
    if not (wd / "nodes.jsonl").exists():
        return None
    return wd


def _merged_dir(dataset):
    wd = work_dir(dataset, "merged")
    if not (wd / "nodes.jsonl").exists():
        return None
    return wd


def _list_datasets():
    """Dataset names = subdirectories of data/work/, discovered dynamically so adding a
    new dataset never requires a code change here."""
    root = REPO_ROOT / "data" / "work"
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


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


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        seg = path.split("/")  # ['', 'api', 'merged', 'genwiki', 'node', 'm#5']

        if path == "/" or path == "/index.html":
            return self._serve_file(DIST_DIR / "index.html", "text/html")

        # ---- debug-view endpoints ----
        if path == "/api/datasets":
            out = []
            for dataset in _list_datasets():
                base = REPO_ROOT / "data" / "work" / dataset
                if not base.exists():
                    continue
                for split_dir in sorted(base.iterdir()):
                    if not split_dir.is_dir() or split_dir.name == "merged":
                        continue
                    n_docs = sum(1 for _ in read_jsonl(split_dir / "docs.jsonl"))
                    if n_docs == 0:
                        continue
                    # Splits are often only partially processed (e.g. a handful of docs
                    # run through stage1 extraction as a smoke test) — surface that count
                    # so the UI can warn instead of silently showing empty results.
                    n_extracted = len({n["doc_id"] for n in read_jsonl(split_dir / "nodes.jsonl")})
                    out.append({"dataset": dataset, "split": split_dir.name, "n_docs": n_docs, "n_extracted": n_extracted})
            return self._send(200, _json(out))

        if path == "/api/docs":
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
            return self._send(200, _json(rows[:DOC_LIST_LIMIT]))

        if path.startswith("/api/doc/"):
            _, _, _, dataset, split, doc_id = path.split("/", 5)
            wd = work_dir(dataset, split)
            docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
            if doc_id not in docs:
                return self._send(404, _json({"error": "doc not found"}))
            mentions = [m for m in read_jsonl(wd / "mentions.jsonl") if m["doc_id"] == doc_id]
            nodes = [n for n in read_jsonl(wd / "nodes.jsonl") if n["doc_id"] == doc_id]
            edges = [e for e in read_jsonl(wd / "edges.jsonl") if e["doc_id"] == doc_id]
            return self._send(200, _json({
                "doc_id": doc_id, "text": docs[doc_id]["text"],
                "mentions": mentions, "nodes": nodes, "edges": edges,
            }))

        if path == "/api/search":
            dataset, split = qs.get("dataset", ["docred"])[0], qs.get("split", ["eval200"])[0]
            q = qs.get("q", [""])[0]
            wd = work_dir(dataset, split)
            client = LLMClient(wd / "llm_cache")
            sem = semantic_search(client, q, wd, top_k=10)
            lex = lexical_search(wd, q, top_k=10)
            seeds = [n["entity_id"] for n in sem["nodes"][:3]]
            graph = graph_search(wd, seeds, hops=2, node_budget=100) if seeds else {"nodes": [], "edges": []}
            return self._send(200, _json({"semantic": sem, "lexical": lex, "graph": graph}))

        # ---- merged-graph endpoints ----
        if path == "/api/merged":
            out = []
            for dataset in _list_datasets():
                wd = _merged_dir(dataset)
                if not wd or not (wd / "stats.json").exists():
                    continue
                stats = json.loads((wd / "stats.json").read_text())
                out.append({"dataset": dataset, **stats})
            return self._send(200, _json(out))

        if len(seg) >= 3 and seg[1] == "api" and seg[2] == "merged" and len(seg) == 4:
            # /api/merged/<dataset>
            dataset = seg[3]
            wd = _merged_dir(dataset)
            if not wd:
                return self._send(404, _json({"error": f"no merged graph for {dataset}"}))
            stats = json.loads((wd / "stats.json").read_text()) if (wd / "stats.json").exists() else {}
            nodes = list(read_jsonl(wd / "nodes.jsonl"))
            edges = list(read_jsonl(wd / "edges.jsonl"))
            return self._send(200, _json({"dataset": dataset, "stats": stats, "nodes": nodes, "edges": edges}))

        if len(seg) >= 5 and seg[1] == "api" and seg[2] == "merged" and seg[4] == "search":
            dataset = seg[3]
            wd = _merged_dir(dataset)
            if not wd:
                return self._send(404, _json({"error": f"no merged graph for {dataset}"}))
            q = qs.get("q", [""])[0]
            top_k = int(qs.get("top_k", ["10"])[0])
            client = LLMClient(wd / "llm_cache")
            sem = semantic_search(client, q, wd, top_k=top_k)
            lex = lexical_search(wd, q, top_k=top_k)
            seeds = [n["entity_id"] for n in sem["nodes"][:3]]
            graph = graph_search(wd, seeds, hops=2, node_budget=100) if seeds else {"nodes": [], "edges": []}
            return self._send(200, _json({"semantic": sem, "lexical": lex, "graph": graph}))

        if len(seg) >= 6 and seg[1] == "api" and seg[2] == "merged" and seg[4] == "node":
            dataset, entity_id = seg[3], unquote(seg[5])
            wd = _merged_dir(dataset)
            if not wd:
                return self._send(404, _json({"error": f"no merged graph for {dataset}"}))
            nodes = {n["entity_id"]: n for n in read_jsonl(wd / "nodes.jsonl")}
            node = nodes.get(entity_id)
            if not node:
                return self._send(404, _json({"error": "node not found"}))
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
            return self._send(200, _json({**node, "sources": sources}))

        if len(seg) >= 6 and seg[1] == "api" and seg[2] == "merged" and seg[4] == "doc":
            # /api/merged/<dataset>/doc/<doc_id> -> full per-doc extraction (text/mentions/
            # nodes/edges), so the merged-graph "sources" list can drill into the original
            # document the same way the debug view does.
            dataset, doc_id = seg[3], unquote(seg[5])
            wd = _merged_dir(dataset)
            if not wd:
                return self._send(404, _json({"error": f"no merged graph for {dataset}"}))
            docs = {d["doc_id"]: d for d in read_jsonl(wd / "docs.jsonl")}
            drec = docs.get(doc_id)
            if not drec:
                return self._send(404, _json({"error": "doc not found"}))
            split = drec.get("split")
            if not split:
                base = REPO_ROOT / "data" / "work" / dataset
                for d in (sorted(base.iterdir()) if base.exists() else []):
                    if not d.is_dir() or d.name == "merged":
                        continue
                    if any(x["doc_id"] == doc_id for x in read_jsonl(d / "docs.jsonl")):
                        split = d.name
                        break
            if not split:
                return self._send(404, _json({"error": "source split not found"}))
            swd = work_dir(dataset, split)
            mentions = [m for m in read_jsonl(swd / "mentions.jsonl") if m["doc_id"] == doc_id]
            nodes = [n for n in read_jsonl(swd / "nodes.jsonl") if n["doc_id"] == doc_id]
            edges = [e for e in read_jsonl(swd / "edges.jsonl") if e["doc_id"] == doc_id]
            return self._send(200, _json({
                "doc_id": doc_id, "split": split, "title": drec.get("title", ""),
                "text": drec.get("text", ""), "mentions": mentions, "nodes": nodes, "edges": edges,
            }))

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
