import pytest
from fastapi.testclient import TestClient

from backend.app.api.research import get_research_service, get_research_store
from backend.app.core.config import settings
from backend.app.main import app
from backend.app.schemas.scraper import ScrapeResult, ScrapeSource
from backend.app.services.research.job_store import InMemoryResearchJobStore
from backend.app.services.research.research_service import ResearchService
from backend.app.services.llm.provider import LLMResponse


class FakeScraperService:
    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        return ScrapeResult(
            request_url=url,
            status="completed",
            data={"title": query or "Result"},
            sources=[ScrapeSource(url=url)],
            quality_score=0.8,
        )


class FakeLLMProvider:
    async def generate(self, context):
        return LLMResponse(
            content='{"report":"r","summary":"s","key_findings":[],"limitations":[],"evidence_refs":[],"confidence":0.5}',
            model="fake",
            provider="fake",
        )


@pytest.fixture
def client():
    store = InMemoryResearchJobStore()
    app.dependency_overrides[get_research_store] = lambda: store
    app.dependency_overrides[get_research_service] = lambda: ResearchService(
        store, FakeScraperService(), llm_provider=FakeLLMProvider()
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_no_app_api_key_configured_allows_unauthenticated_access(client, monkeypatch):
    """Local-dev default: settings.webmind_api_key unset -> no auth required."""
    monkeypatch.setattr(settings, "api_key", None)
    response = client.get("/api/v1/research?limit=5")
    assert response.status_code == 200


def test_missing_api_key_returns_401_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-app-key")
    response = client.get("/api/v1/research?limit=5")
    assert response.status_code == 401
    assert response.json()["detail"] == "API key required."


def test_invalid_api_key_returns_401(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-app-key")
    response = client.get(
        "/api/v1/research?limit=5",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key."


def test_valid_x_api_key_header_is_accepted(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-app-key")
    response = client.get(
        "/api/v1/research?limit=5",
        headers={"X-API-Key": "expected-app-key"},
    )
    assert response.status_code == 200


def test_valid_bearer_token_is_accepted(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-app-key")
    response = client.get(
        "/api/v1/research?limit=5",
        headers={"Authorization": "Bearer expected-app-key"},
    )
    assert response.status_code == 200


def test_post_research_requires_app_api_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-app-key")
    response = client.post(
        "/api/v1/research",
        json={"url": "https://example.com", "query": "test"},
    )
    assert response.status_code == 401


def test_post_research_succeeds_with_valid_app_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-app-key")
    response = client.post(
        "/api/v1/research",
        json={"url": "https://example.com", "query": "test"},
        headers={"X-API-Key": "expected-app-key"},
    )
    assert response.status_code == 202


def test_app_api_key_and_llm_api_key_are_independent_settings(monkeypatch):
    """Regression test for the misconfiguration where a single `.env` value
    named `API_KEY` was mistakenly used both as the WebMind app auth key
    (settings.webmind_api_key) and assumed to also be the LLM provider key. They
    must remain two distinct settings fields."""
    monkeypatch.setattr(settings, "api_key", "webmind-app-secret")
    monkeypatch.setattr(settings, "llm_api_key", "sk-llm-secret")
    assert settings.webmind_api_key != settings.llm_api_key
    assert settings.webmind_api_key == "webmind-app-secret"
    assert settings.llm_api_key == "sk-llm-secret"
