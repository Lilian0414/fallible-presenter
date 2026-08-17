import json

import httpx
import pytest

from backend.app.models import Claim
from backend.app.services.error_injector import inject_errors
from backend.app.services.llm import OpenAICompatibleProvider, ProviderOutputError


def test_injector_preserves_linkage_and_changes_statement():
    claim = Claim(
        id="claim_001",
        statement="Revenue increased by 20%.",
        evidence="Revenue increased by 20%.",
        source_text="Revenue increased by 20%.",
        importance=5,
    )
    error = inject_errors([claim])[0]
    assert error.id and error.claim_id == claim.id
    assert error.original_statement == claim.statement
    assert error.modified_statement != claim.statement


@pytest.mark.asyncio
async def test_real_provider_uses_strict_schema_and_server_owned_fields(monkeypatch):
    source = "A supported fact."

    async def handler(request):
        request_body = json.loads(request.content)
        response_format = request_body["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        content = json.dumps(
            {
                "claims": [
                    {
                        "statement": source,
                        "evidence": source,
                        "importance": 3,
                    }
                ]
            }
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    monkeypatch.setenv("LLM_API_KEY", "test")
    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    claims = await provider.extract_claims(source)
    assert claims[0].id == "claim_001"
    assert claims[0].source_text == source


@pytest.mark.asyncio
async def test_real_provider_retries_malformed_json(monkeypatch):
    calls = 0
    valid = {
        "claims": [
            {
                "statement": "A supported fact.",
                "evidence": "A supported fact.",
                "importance": 3,
            }
        ]
    }

    async def handler(request):
        nonlocal calls
        calls += 1
        content = "not-json" if calls == 1 else json.dumps(valid)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    monkeypatch.setenv("LLM_API_KEY", "test")
    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    claims = await provider.extract_claims("A supported fact.")
    assert calls == 2
    assert claims[0].statement == "A supported fact."


@pytest.mark.asyncio
async def test_real_provider_falls_back_when_schema_is_unsupported(monkeypatch):
    formats = []

    async def handler(request):
        request_body = json.loads(request.content)
        formats.append(request_body["response_format"]["type"])
        if len(formats) == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "response_format json_schema is not supported"}},
            )
        content = json.dumps(
            {
                "claims": [
                    {
                        "statement": "A supported fact.",
                        "evidence": "A supported fact.",
                        "importance": 3,
                    }
                ]
            }
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    monkeypatch.setenv("LLM_API_KEY", "test")
    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await provider.extract_claims("A supported fact.")
    assert formats == ["json_schema", "json_object"]


@pytest.mark.asyncio
async def test_real_provider_fails_cleanly_after_retry(monkeypatch):
    async def handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{"}}]}
        )

    monkeypatch.setenv("LLM_API_KEY", "test")
    provider = OpenAICompatibleProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ProviderOutputError):
        await provider.extract_claims("A fact.")
