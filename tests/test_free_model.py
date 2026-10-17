import asyncio
import json

import httpx

from app.agent import _llm_answer


def test_only_free_router_even_if_paid_model_environment_exists(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'never-use-this')
    monkeypatch.setenv('OPENAI_MODEL', 'paid-model')
    monkeypatch.setenv('OPENROUTER_MODEL', 'paid-model')
    calls = []
    def handler(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert str(request.url) == 'https://openrouter.ai/api/v1/chat/completions'
        assert payload['model'] == 'openrouter/free'
        assert payload['provider']['max_price'] == {'prompt': 0, 'completion': 0}
        assert 'models' not in payload
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Grounded answer'}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(_llm_answer('question', [], [])) == 'Grounded answer'
    assert len(calls) == 1


def test_free_limit_does_not_fall_back_to_paid_provider(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={'error': {'message': 'Free limit reached'}})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(_llm_answer('question', [], [])) is None
    assert len(calls) == 1


def test_openai_key_alone_never_causes_paid_call(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'never-use-this')
    assert asyncio.run(_llm_answer('question', [], [])) is None
