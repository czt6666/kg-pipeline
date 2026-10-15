from __future__ import annotations

import argparse
import json
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from assistant import TCMAgent
from core.common import GRAPH_ROOT, PIPELINE_ROOT, graph_dir, read_jsonl, work_dir
from core.llm import LLMError
from graph.retrieval.pipeline import expand_entity, generate_summary, hybrid_search
from .http_utils import ApiResult, JsonHandler


def _snippet(text: str, names: list[str], radius: int = 60) -> str:
    low = text.lower()
    for name in names:
        idx = low.find(name.lower())
        if idx >= 0:
            start = max(0, idx - radius)
            end = min(len(text), idx + len(name) + radius)
            return text[start:end]
    return text[: radius * 2]


def list_graphs(_qs):
    out = []
    for dataset_dir in sorted(GRAPH_ROOT.iterdir()) if GRAPH_ROOT.exists() else []:
        for graph in sorted(dataset_dir.iterdir()):
            if not graph.is_dir() or not (graph / 'nodes.jsonl').exists():
                continue
            stats = json.loads((graph / 'stats.json').read_text()) if (graph / 'stats.json').exists() else {}
            out.append({"dataset": dataset_dir.name, "merge": graph.name, **stats})
    return ApiResult(200, out)


def get_graph(dataset, merge):
    wd = graph_dir(dataset, merge)
    if not (wd / 'nodes.jsonl').exists():
        return ApiResult(404, {"error": f"graph not found: {dataset}/{merge}"})
    stats = json.loads((wd / 'stats.json').read_text()) if (wd / 'stats.json').exists() else {}
    return ApiResult(200, {"dataset": dataset, "merge": merge, "stats": stats, "nodes": list(read_jsonl(wd / 'nodes.jsonl')), "edges": list(read_jsonl(wd / 'edges.jsonl'))})


def get_node(dataset, merge, entity_id):
    wd = graph_dir(dataset, merge)
    nodes = {n['entity_id']: n for n in read_jsonl(wd / 'nodes.jsonl')}
    node = nodes.get(entity_id)
    if not node:
        return ApiResult(404, {"error": "node not found"})
    docs = {d['doc_id']: d for d in read_jsonl(wd / 'docs.jsonl')}
    names = [node['name']] + list(node.get('aliases') or [])
    sources = []
    for doc_id in node.get('source_doc_ids', []):
        d = docs.get(doc_id)
        if not d:
            continue
        sources.append({"doc_id": doc_id, "title": d.get('title', ''), "snippet": _snippet(d.get('text', ''), names)})
    return ApiResult(200, {**node, 'sources': sources})


def get_doc(dataset, merge, doc_id):
    wd = graph_dir(dataset, merge)
    docs = {d['doc_id']: d for d in read_jsonl(wd / 'docs.jsonl')}
    drec = docs.get(doc_id)
    if not drec:
        return ApiResult(404, {"error": "doc not found"})
    split = drec.get('split')
    if not split:
        splits_root = PIPELINE_ROOT / dataset / 'splits'
        for split_dir in sorted(splits_root.iterdir()) if splits_root.exists() else []:
            if any(x['doc_id'] == doc_id for x in read_jsonl(split_dir / 'docs.jsonl')):
                split = split_dir.name
                break
    if not split:
        return ApiResult(404, {"error": "source split not found"})
    swd = work_dir(dataset, split)
    mentions = [m for m in read_jsonl(swd / 'mentions.jsonl') if m['doc_id'] == doc_id]
    nodes = [n for n in read_jsonl(swd / 'nodes.jsonl') if n['doc_id'] == doc_id]
    edges = [e for e in read_jsonl(swd / 'edges.jsonl') if e['doc_id'] == doc_id]
    return ApiResult(200, {"doc_id": doc_id, "split": split, "title": drec.get('title', ''), "text": drec.get('text', ''), "mentions": mentions, "nodes": nodes, "edges": edges})


def retrieval_search(qs):
    dataset = qs.get('dataset', ['TCM'])[0]
    merge = qs.get('merge', ['merged'])[0]
    term = qs.get('term', [''])[0].strip()
    top_k = int(qs.get('top_k', ['10'])[0])
    expand = qs.get('expand', ['1'])[0] != '0'
    if not term:
        return ApiResult(400, {"error": "missing term"})
    try:
        return ApiResult(200, hybrid_search(dataset, merge, term, top_k=top_k, expand=expand))
    except LLMError as e:
        return ApiResult(500, {"error": f"embedding request failed: {e}"})


def retrieval_expand(qs):
    dataset = qs.get('dataset', ['TCM'])[0]
    merge = qs.get('merge', ['merged'])[0]
    entity_id = qs.get('entity_id', [''])[0]
    top_k = int(qs.get('top_k', ['10'])[0])
    if not entity_id:
        return ApiResult(400, {"error": "missing entity_id"})
    expanded = expand_entity(graph_dir(dataset, merge), entity_id, top_k=top_k)
    return ApiResult(200, expanded) if expanded else ApiResult(404, {"error": "entity not found"})


def retrieval_summary(qs):
    dataset = qs.get('dataset', ['TCM'])[0]
    merge = qs.get('merge', ['merged'])[0]
    entity_id = qs.get('entity_id', [''])[0]
    top_k = int(qs.get('top_k', ['10'])[0])
    if not entity_id:
        return ApiResult(400, {"error": "missing entity_id"})
    try:
        summary = generate_summary(graph_dir(dataset, merge), entity_id, top_k=top_k)
    except LLMError as e:
        return ApiResult(500, {"error": f"summary request failed: {e}"})
    return ApiResult(200, {"entity_id": entity_id, "summary": summary})


def agent_chat(body):
    messages = body.get('messages') or []
    if not messages or messages[-1].get('role') != 'user':
        return ApiResult(400, {"error": "messages must be non-empty and end with a user turn"})
    try:
        agent, state = TCMAgent.build(dataset=body.get('dataset'), merge=body.get('merge'), max_ask_rounds=int(body.get('max_rounds', 3)))
    except FileNotFoundError as e:
        return ApiResult(404, {"error": f"unknown dataset/merge: {e}"})
    state.conversation = [{"role": m['role'], "content": m['content']} for m in messages[:-1]]
    try:
        result = agent.run_turn(state, messages[-1]['content'])
    except LLMError as e:
        return ApiResult(502, {"error": f"llm/retrieval failed: {e}"})
    # trace is always returned now -- the QA UI shows the reasoning process by default,
    # not behind an opt-in debug flag (see web/src/pages/Chat.jsx's ReasoningView).
    return ApiResult(200, result.to_dict(include_trace=True))


class KgHandler(JsonHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b'{}'
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return self.send_bytes(400, b'{"error":"invalid JSON body"}')
        if parsed.path == '/api/kg/agent/chat':
            return self.send_api_with_heartbeat(lambda: agent_chat(body))
        return self.send_api(ApiResult(404, {"error": "not found"}))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        seg = path.split('/')
        if path == '/api/kg/merged':
            return self.send_api(list_graphs(qs))
        if len(seg) >= 6 and seg[1] == 'api' and seg[2] == 'kg' and seg[3] == 'merged':
            dataset, merge = seg[4], seg[5]
            if len(seg) == 6:
                return self.send_api(get_graph(dataset, merge))
            if len(seg) >= 8 and seg[6] == 'node':
                return self.send_api(get_node(dataset, merge, unquote(seg[7])))
            if len(seg) >= 8 and seg[6] == 'doc':
                return self.send_api(get_doc(dataset, merge, unquote(seg[7])))
        if path == '/api/kg/retrieval/search':
            return self.send_api(retrieval_search(qs))
        if path == '/api/kg/retrieval/expand':
            return self.send_api(retrieval_expand(qs))
        if path == '/api/kg/retrieval/summary':
            return self.send_api(retrieval_summary(qs))
        return self.send_api(ApiResult(404, {"error": "not found"}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=53786)
    args = ap.parse_args()
    server = ThreadingHTTPServer(('0.0.0.0', args.port), KgHandler)
    print(f'kg server listening on http://localhost:{args.port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
