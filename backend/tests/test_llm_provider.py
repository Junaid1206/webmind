import json

import httpx
import pytest

from backend.app.services.llm.provider import OpenAICompatibleLLMProvider
from backend.app.services.llm.research_synthesizer import ResearchContext, ResearchSynthesizer


def provider_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_provider_success_and_synthesis_parsing():
    async def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        prompt = payload["messages"][1]["content"]
        assert '"request_url": "https://example.com/"' in prompt
        assert '"quality_score": 0.8' in prompt
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"report":"Report","summary":"Summary","confidence":0.8}'}}]})

    provider = OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(handler))
    synthesis = await ResearchSynthesizer(
        provider,
    ).synthesize(
        ResearchContext(query="test", request_url="https://example.com/", quality_score=0.8),
    )
    assert synthesis.report == "Report"
    assert synthesis.summary == "Summary"


@pytest.mark.asyncio
async def test_provider_requires_credentials(monkeypatch):
    monkeypatch.setattr("backend.app.services.llm.provider.settings.llm_api_key", None)
    provider = OpenAICompatibleLLMProvider()

    with pytest.raises(RuntimeError, match="LLM_API_KEY is not configured"):
        await provider.generate({})


@pytest.mark.asyncio
async def test_provider_timeout_is_safe():
    async def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(handler))
    with pytest.raises(RuntimeError, match="timed out"):
        await provider.generate({})


@pytest.mark.asyncio
async def test_provider_http_error_is_safe():
    async def handler(request):
        return httpx.Response(503)

    provider = OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(handler))
    with pytest.raises(RuntimeError, match="request failed"):
        await provider.generate({})


@pytest.mark.asyncio
async def test_provider_model_error_does_not_expose_provider_body():
    async def handler(request):
        return httpx.Response(400, text='{"error":"model_not_supported secret-token"}')

    provider = OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(handler))
    with pytest.raises(RuntimeError, match="request failed") as exc_info:
        await provider.generate({})
    assert "secret-token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_provider_malformed_and_empty_responses_are_rejected():
    async def malformed(request):
        return httpx.Response(200, text="not-json")

    async def empty(request):
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(RuntimeError, match="malformed JSON"):
        await OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(malformed)).generate({})
    with pytest.raises(RuntimeError, match="no completion choices"):
        await OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(empty)).generate({})


@pytest.mark.asyncio
async def test_invalid_synthesis_output_is_rejected():
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    provider = OpenAICompatibleLLMProvider(api_key="test-key", client=provider_client(handler))
    with pytest.raises(ValueError, match="missing a valid report"):
        await ResearchSynthesizer(provider).synthesize(ResearchContext())