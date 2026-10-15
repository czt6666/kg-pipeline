"""Streaming QA endpoint -- runs a real HTTP server with a scripted agent (no network, no
graph data) and checks the SSE event sequence."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from assistant.actions import Evidence, EvidenceFact
from assistant.loop import TCMAgent
from assistant.reasoner import ScriptedReasoner
from assistant.retrieval_adapter import FakeRetrievalAdapter
from assistant.schema_spec import load_schema_spec
from assistant.state import AgentState
from services import kg_server
from services.backend_server import BackendHandler


def _read_events(resp):
    events, current = [], {}
    for raw in resp:
        line = raw.decode("utf-8").rstrip("\n")
        if not line:
            if current:
                events.append((current["event"], json.loads(current["data"])))
            current = {}
        elif line.startswith(":"):
            events.append(("heartbeat", None))
        else:
            k, _, v = line.partition(": ")
            current[k] = v
    return events


@pytest.fixture
def server(monkeypatch):
    schema = load_schema_spec("TCM")
    ev = {"柴胡": Evidence(query="柴胡", found=True,
                           resolved_entity={"entity_id": "h1", "name": "柴胡", "type": "中药"},
                           facts=[EvidenceFact(sentence="柴胡功效为疏肝解郁", source="P", relations=["功效"])])}
    script = {"controller": [{"action": "retrieve", "queries": [{"term": "柴胡"}]}, {"action": "answer"}],
              "answer": "柴胡能疏肝解郁。"}

    def build(**_):
        agent = TCMAgent(ScriptedReasoner(script), FakeRetrievalAdapter(schema, ev), schema)
        return agent, AgentState()

    monkeypatch.setattr(kg_server.TCMAgent, "build", staticmethod(build))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), BackendHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=10)


def test_stream_emits_steps_delta_and_done(server):
    with _post(server + "/api/kg/agent/chat/stream",
               {"messages": [{"role": "user", "content": "柴胡的功效？"}]}) as resp:
        assert resp.headers["Content-Type"].startswith("text/event-stream")
        assert resp.headers["X-Accel-Buffering"] == "no"
        events = _read_events(resp)

    kinds = [k for k, _ in events]
    assert kinds[-1] == "done"
    stages = [p["stage"] for k, p in events if k == "step"]
    assert stages == ["controller", "retrieval_result", "controller", "answer"]
    assert "".join(p["text"] for k, p in events if k == "delta") == "柴胡能疏肝解郁。"
    done = events[-1][1]
    assert done["reply"] == "柴胡能疏肝解郁。" and len(done["trace"]) == 4


def test_stream_heartbeats_while_agent_is_silent(server, monkeypatch):
    monkeypatch.setattr(kg_server, "HEARTBEAT_S", 0.05)
    original = ScriptedReasoner.think

    def slow_think(self, *a, **kw):
        import time
        time.sleep(0.3)
        return original(self, *a, **kw)

    monkeypatch.setattr(ScriptedReasoner, "think", slow_think)
    with _post(server + "/api/kg/agent/chat/stream",
               {"messages": [{"role": "user", "content": "柴胡的功效？"}]}) as resp:
        events = _read_events(resp)
    assert ("heartbeat", None) in events and events[-1][0] == "done"


def test_stream_reports_agent_errors(server, monkeypatch):
    def boom(self, *a, **kw):
        raise RuntimeError("controller exploded")

    monkeypatch.setattr(ScriptedReasoner, "think", boom)
    with _post(server + "/api/kg/agent/chat/stream",
               {"messages": [{"role": "user", "content": "x"}]}) as resp:
        events = _read_events(resp)
    assert events[-1][0] == "error" and "controller exploded" in events[-1][1]["error"]


def test_stream_rejects_bad_body(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(server + "/api/kg/agent/chat/stream", {"messages": []})
    assert e.value.code == 400
