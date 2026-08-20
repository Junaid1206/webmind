import asyncio

from fastapi.testclient import TestClient

from backend.app.api.research import get_research_service, get_research_store
from backend.app.main import app
from backend.app.services.llm.provider import LLMResponse
from backend.app.services.research.job_store import SqliteResearchJobStore
from backend.app.services.research.research_service import ResearchService
from backend.app.services.scraper.scraper_service import ScraperService


class FakeBrightDataClient:
    async def scrape(self, url: str, query: str | None = None) -> dict:
        return {
            "records": [
                {
                    "url": url,
                    "title": "Web scraping",
                    "content": "Web scraping extracts information from websites.",
                }
            ]
        }


class FakeLLMProvider:
    async def generate(self, context: dict) -> LLMResponse:
        assert context["evidence"][0]["evidence_index"] == 0
        assert context["claims"][0]["verification_status"] == "verified"
        return LLMResponse(
            content=(
                '{"title":"Web scraping report","report":"A source-backed report.",'
                '"summary":"Web scraping extracts website information.",'
                '"key_findings":["It extracts website information."],'
                '"limitations":["Coverage depends on the collected page."],'
                '"evidence_refs":["https://example.com/","https://unknown.example/"],'
                '"confidence":0.9,"claims":["This generated claim is not authoritative."]}'
            ),
            model="fake-model",
            provider="fake-provider",
        )


def test_realistic_research_pipeline_persists_complete_result(tmp_path):
    store = SqliteResearchJobStore(path=str(tmp_path / "e2e" / "research.db"))
    scraper = ScraperService(FakeBrightDataClient())
    service = ResearchService(store, scraper, FakeLLMProvider())
    service.start_job = lambda job: None
    app.dependency_overrides[get_research_store] = lambda: store
    app.dependency_overrides[get_research_service] = lambda: service
    client = TestClient(app)

    try:
        created = client.post(
            "/api/v1/research",
            json={"url": "https://example.com", "query": "What is web scraping?"},
        )
        assert created.status_code == 202
        job_id = created.json()["job_id"]
        assert created.json()["status"] == "queued"

        asyncio.run(service.run_job(job_id))
        response = client.get(f"/api/v1/research/{job_id}")
        body = response.json()
        result = body["result"]
        data = result["data"]
        claims = body["claims"]
        evidence = data["evidence"]

        assert body["status"] == "completed"
        assert body["query"] == "What is web scraping?"
        assert body["title"] == "Web scraping report"
        assert body["report"] == "A source-backed report."
        assert body["summary"] == "Web scraping extracts website information."
        assert body["sources"]
        assert evidence
        assert claims
        assert all(0 <= claim["evidence_index"] < len(evidence) for claim in claims)
        assert all(claim["verification_status"] in {"verified", "unverified"} for claim in claims)
        assert all(claim["verification_status"] == "verified" for claim in claims)
        assert body["entities"]
        assert body["relationships"]
        assert body["confidence"] == 0.9
        assert body["evidence_refs"] == ["https://example.com/"]
        assert "Authorization" not in response.text
        assert "api_key" not in response.text

        recreated = SqliteResearchJobStore(path=str(tmp_path / "e2e" / "research.db"))
        app.dependency_overrides[get_research_store] = lambda: recreated
        restored = client.get(f"/api/v1/research/{job_id}").json()
        history = client.get("/api/v1/research?limit=20").json()
        assert restored["status"] == "completed"
        assert restored["report"] == "A source-backed report."
        assert restored["result"]["data"]["claims"]
        assert any(item["job_id"] == job_id for item in history["items"])
    finally:
        app.dependency_overrides.clear()