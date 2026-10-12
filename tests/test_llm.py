"""Verify the QA provider's wire format and cache without network access."""

from core.llm import LLMClient


def test_openai_chat_completion_and_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "您好"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            }

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        return Response()

    monkeypatch.setattr("core.llm.requests.post", fake_post)
    client = LLMClient(tmp_path, provider="openai")
    result = client.chat("你好", temperature=0, max_tokens=32)

    assert calls == [(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": "Bearer test-key", "Content-Type": "application/json"},
        {"model": "gpt-4.1", "messages": [{"role": "user", "content": "你好"}],
         "temperature": 0, "max_completion_tokens": 32},
    )]
    assert result["response_raw"] == "您好"
    assert result["finish_reason"] == "stop"
    assert client.chat("你好", temperature=0, max_tokens=32) == result
    assert len(calls) == 1


def test_agent_build_uses_openai_for_decisions_and_answers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from assistant.loop import TCMAgent

    agent, _ = TCMAgent.build()
    assert agent.reasoner.client.provider == "openai"
    assert agent.reasoner.client.model == "gpt-4.1"
    assert agent.reasoner.answer_client is agent.reasoner.client
    assert agent.adapter.embedding_provider == "openai"


def test_openai_embeddings_use_same_key_and_order_results(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]}

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        return Response()

    monkeypatch.setattr("core.llm.requests.post", fake_post)
    client = LLMClient(tmp_path, provider="openai")
    assert client.embed(["柴胡", "桂枝"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert calls == [(
        "https://api.openai.com/v1/embeddings",
        {"Authorization": "Bearer test-key", "Content-Type": "application/json"},
        {"model": "text-embedding-3-small", "input": ["柴胡", "桂枝"]},
    )]
