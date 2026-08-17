import json

import httpx
import pytest

from backend.app.models import Claim
from backend.app.services.error_injector import inject_errors
from backend.app.services.llm import OpenAICompatibleProvider, ProviderOutputError


def test_injector_preserves_linkage_and_changes_statement():
    claim = Claim(id="claim_001", statement="Revenue increased by 20%.", evidence="Revenue increased by 20%.", source_text="Revenue increased by 20%.", importance=5)
    error = inject_errors([claim])[0]
    assert error.id and error.claim_id == claim.id
    assert error.original_statement == claim.statement
    assert error.modified_statement != claim.statement


@pytest.mark.asyncio
async def test_real_provider_retries_malformed_json(monkeypatch):
    calls = 0
    valid = {"claims": [{"id": "c1", "statement": "A supported fact.", "evidence": "A supported fact.", "source_text": "A supported fact.", "importance": 3}]}
    async def handler(request):
        nonlocal calls; calls += 1
        content = "not-json" if calls == 1 else json.dumps(valid)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    monkeypatch.setenv("LLM_API_KEY", "test")
    provider = OpenAICompatibleProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    claims = await provider.extract_claims("A supported fact.")
    assert calls == 2 and claims[0].statement == "A supported fact."


@pytest.mark.asyncio
async def test_real_provider_fails_cleanly_after_retry(monkeypatch):
    async def handler(request): return httpx.Response(200, json={"choices": [{"message": {"content": "{"}}]})
    monkeypatch.setenv("LLM_API_KEY", "test")
    provider = OpenAICompatibleProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderOutputError): await provider.extract_claims("A fact.")
