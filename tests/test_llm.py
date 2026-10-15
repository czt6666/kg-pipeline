"""Verify the SHEEPWALL gateway wire format and cache without network access."""

import pytest

from core.llm import LLMClient

BASE = "https://gateway.test/llm/"


@pytest.fixture
def gateway_env(monkeypatch):
    monkeypatch.setenv("SHEEPWALL_BASE_URL", BASE)
    monkeypatch.setenv("SHEEPWALL_API_KEY", "test-key")
    monkeypatch.setenv("SHEEPWALL_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SHEEPWALL_EMBEDDING_MODEL", "azure/text-embedding-3-small")


def test_chat_uses_messages_endpoint_without_thinking_and_caches(gateway_env, monkeypatch, tmp_path):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {
                "content": [{"type": "text", "text": "您好"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }

    def fake_post(url, headers, json, timeout, stream=False):
        calls.append((url, headers, json))
        return Response()

    monkeypatch.setattr("core.llm.requests.post", fake_post)
    client = LLMClient(tmp_path)
    result = client.chat("你好", temperature=0, max_tokens=32)

    assert calls == [(
        BASE + "v1/messages",
        {"x-api-key": "test-key", "anthropic-version": "2023-06-01",
         "Content-Type": "application/json"},
        {"model": "deepseek-v4-pro", "messages": [{"role": "user", "content": "你好"}],
         "temperature": 0, "max_tokens": 32, "thinking": {"type": "disabled"}},
    )]
    assert result["response_raw"] == "您好"
    assert result["finish_reason"] == "end_turn"
    assert client.chat("你好", temperature=0, max_tokens=32) == result
    assert len(calls) == 1


def test_chat_does_not_cache_empty_answer(gateway_env, monkeypatch, tmp_path):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {
                "content": [{"type": "thinking", "thinking": "嗯……"}],
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 5, "output_tokens": 32},
            }

    def fake_post(url, headers, json, timeout, stream=False):
        calls.append(url)
        return Response()

    monkeypatch.setattr("core.llm.requests.post", fake_post)
    client = LLMClient(tmp_path)
    result = client.chat("你好", temperature=0, max_tokens=32)

    assert result["response_raw"] == ""
    assert result["finish_reason"] == "max_tokens"
    assert list(tmp_path.glob("*.json")) == []
    client.chat("你好", temperature=0, max_tokens=32)
    assert len(calls) == 2


def test_agent_build_uses_gateway_for_decisions_answers_and_retrieval(gateway_env):
    from assistant.loop import TCMAgent

    agent, _ = TCMAgent.build()
    assert agent.reasoner.client.base_url == BASE
    assert agent.reasoner.client.model == "deepseek-v4-pro"
    assert agent.reasoner.answer_client is agent.reasoner.client
    assert not hasattr(agent.adapter, "embedding_provider")


def test_embeddings_use_bearer_auth_and_order_results(gateway_env, monkeypatch, tmp_path):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]}

    def fake_post(url, headers, json, timeout, stream=False):
        calls.append((url, headers, json))
        return Response()

    monkeypatch.setattr("core.llm.requests.post", fake_post)
    client = LLMClient(tmp_path)
    assert client.embed(["柴胡", "桂枝"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert calls == [(
        BASE + "v1/embeddings",
        {"Authorization": "Bearer test-key", "Content-Type": "application/json"},
        {"model": "azure/text-embedding-3-small", "input": ["柴胡", "桂枝"]},
    )]


def test_chat_streams_text_deltas_and_caches_full_record(gateway_env, monkeypatch, tmp_path):
    lines = [
        'event: message_start',
        'data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}',
        '',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"想"}}',
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"您"}}',
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"好"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}',
        'data: {"type":"message_stop"}',
    ]
    sent = []

    class Response:
        status_code = 200
        encoding = None

        def iter_lines(self, decode_unicode=False):
            return iter(lines)

        def close(self):
            pass

    def fake_post(url, headers, json, timeout, stream=False):
        sent.append((json, stream))
        return Response()

    monkeypatch.setattr("core.llm.requests.post", fake_post)
    client = LLMClient(tmp_path)
    chunks = []
    result = client.chat("你好", temperature=0, max_tokens=32, on_text=chunks.append)

    assert sent[0][0]["stream"] is True and sent[0][1] is True
    assert chunks == ["您", "好"]
    assert result["response_raw"] == "您好" and result["reasoning_content"] == "想"
    assert result["finish_reason"] == "end_turn"
    assert result["usage"] == {"input_tokens": 5, "output_tokens": 3}

    replay = []
    assert client.chat("你好", temperature=0, max_tokens=32, on_text=replay.append) == result
    assert replay == ["您好"] and len(sent) == 1
