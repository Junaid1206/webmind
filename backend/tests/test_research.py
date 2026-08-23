import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app.api.research import get_research_service, get_research_store
from backend.app.main import app
from backend.app.schemas.scraper import ScrapeResult, ScrapeSource
from backend.app.services.research.job_store import InMemoryResearchJobStore, SqliteResearchJobStore
from backend.app.services.research.research_service import ResearchService
from backend.app.services.llm.provider import LLMResponse


class FakeScraperService:
    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        return ScrapeResult(request_url=url, status="completed", data={"title": query or "Result"}, sources=[ScrapeSource(url=url)], quality_score=0.8)


class FakeLLMProvider:
    async def generate(self, context):
        return LLMResponse(
            content='{"report":"Synthesized report","summary":"Synthesized summary","key_findings":["Finding"],"limitations":["Limitation"],"evidence_refs":["https://example.com","https://unknown.example"],"confidence":0.9}',
            model="fake",
            provider="fake",
        )


class CapturingLLMProvider:
    def __init__(self):
        self.context = None

    async def generate(self, context):
        self.context = context
        return LLMResponse(
            content='{"title":"Captured","report":"Report","summary":"Summary","confidence":0.8}',
            model="fake",
            provider="fake",
        )


class UnavailableLLMProvider:
    async def generate(self, context):
        raise RuntimeError("fake provider unavailable")


class EvidenceScraperService:
    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        return ScrapeResult(
            request_url=url,
            status="completed",
            data={
                "evidence": [{"source_url": url, "snippet": "Supported evidence."}],
                "claims": [{"statement": "Supported evidence.", "verification_status": "verified"}],
                "entities": [{"name": "Example", "type": "document"}],
                "relationships": [],
            },
            sources=[ScrapeSource(url=url, title="Example")],
            quality_score=0.8,
        )


class FailingPersistenceStore(InMemoryResearchJobStore):
    def __init__(self, failure: str):
        super().__init__()
        self.failure = failure

    def store_llm_result(self, job_id, synthesis):
        if self.failure == "llm":
            raise RuntimeError("persistence secret must not escape")
        return super().store_llm_result(job_id, synthesis)

    def update_status(self, job_id, status):
        if self.failure == "status":
            raise RuntimeError("status persistence secret must not escape")
        return super().update_status(job_id, status)


@pytest.mark.asyncio
async def test_research_service_completes_a_job():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService(), UnavailableLLMProvider())
    job = service.create_job("https://example.com", "example")

    assert job.status == "queued"
    await service.run_job(job.job_id)

    completed = store.get(job.job_id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.result is not None
    assert completed.result.data["title"] == "example"


@pytest.mark.asyncio
async def test_research_service_marks_a_job_running_before_completion():
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingScraperService:
        async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
            started.set()
            await release.wait()
            return ScrapeResult(request_url=url, status="completed")

    store = InMemoryResearchJobStore()
    service = ResearchService(store, BlockingScraperService(), UnavailableLLMProvider())
    job = service.create_job("https://example.com")
    task = asyncio.create_task(service.run_job(job.job_id))
    await started.wait()
    assert store.get(job.job_id).status == "running"
    release.set()
    await task


@pytest.mark.asyncio
async def test_research_service_records_a_safe_failure():
    class FailingScraperService:
        async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
            raise RuntimeError("api_key=secret-value")

    store = InMemoryResearchJobStore()
    service = ResearchService(store, FailingScraperService(), UnavailableLLMProvider())
    job = service.create_job("https://example.com")
    await service.run_job(job.job_id)

    failed = store.get(job.job_id)
    assert failed is not None and failed.status == "failed"
    assert failed.error == "Research service is temporarily unavailable."
    assert "secret" not in failed.error


@pytest.mark.asyncio
async def test_research_service_runs_independent_jobs_concurrently():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService(), UnavailableLLMProvider())
    first = service.create_job("https://example.com", "first")
    second = service.create_job("https://example.org", "second")

    await asyncio.gather(service.run_job(first.job_id), service.run_job(second.job_id))

    assert store.get(first.job_id).result.data["title"] == "first"
    assert store.get(second.job_id).result.data["title"] == "second"


@pytest.mark.asyncio
async def test_research_service_ignores_duplicate_starts_for_same_job():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService(), UnavailableLLMProvider())
    job = service.create_job("https://example.com", "dup")

    await asyncio.gather(service.run_job(job.job_id), service.run_job(job.job_id))

    assert store.get(job.job_id).status == "completed"


def test_research_api_lifecycle_history_and_validation():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService(), UnavailableLLMProvider())
    service.start_job = lambda job: None
    app.dependency_overrides[get_research_store] = lambda: store
    app.dependency_overrides[get_research_service] = lambda: service
    client = TestClient(app)

    invalid = client.post("/api/v1/research", json={"url": "not-a-url"})
    assert invalid.status_code == 422
    assert client.get("/api/v1/research?limit=0").status_code == 422
    assert client.get("/api/v1/research?offset=-1").status_code == 422

    created = client.post("/api/v1/research", json={"url": "https://example.com", "query": "first"})
    assert created.status_code == 202
    job = created.json()
    assert job["status"] == "queued"
    assert job["result"] is None

    asyncio.run(service.run_job(job["job_id"]))
    retrieved = client.get(f"/api/v1/research/{job['job_id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["status"] == "completed"
    assert retrieved.json()["result"]["data"]["title"] == "first"
    assert client.get("/api/v1/research/missing").status_code == 404

    second = store.create("https://example.org", "second")
    history = client.get("/api/v1/research?status=queued&limit=1&offset=0")
    assert history.status_code == 200
    assert history.json()["items"][0]["job_id"] == second.job_id
    assert history.json()["items"][0]["status"] == "queued"
    app.dependency_overrides.clear()


def test_research_history_is_newest_first_and_paginated():
    store = InMemoryResearchJobStore()
    first = store.create("https://first.example")
    second = store.create("https://second.example")
    third = store.create("https://third.example")

    assert [job.job_id for job in store.list(limit=2)] == [third.job_id, second.job_id]
    assert [job.job_id for job in store.list(limit=2, offset=1)] == [second.job_id, first.job_id]


@pytest.mark.asyncio
async def test_synthesis_filters_unknown_evidence_refs_and_preserves_deterministic_claims():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, EvidenceScraperService(), FakeLLMProvider())
    job = service.create_job("https://example.com", "evidence")
    await service.run_job(job.job_id)

    completed = store.get(job.job_id)
    assert completed is not None and completed.status == "completed"
    assert completed.evidence_refs == ["https://example.com"]
    assert completed.result is not None
    assert completed.result.data["claims"][0]["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_synthesis_context_contains_request_url_quality_and_evidence():
    provider = CapturingLLMProvider()
    store = InMemoryResearchJobStore()
    service = ResearchService(store, EvidenceScraperService(), provider)
    job = service.create_job("https://example.com", "context")

    await service.run_job(job.job_id)

    assert provider.context["request_url"] == "https://example.com/"
    assert provider.context["quality_score"] == 0.8
    assert provider.context["evidence"][0]["evidence_index"] == 0
    assert provider.context["claims"][0]["verification_status"] == "verified"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["llm", "status"])
async def test_unexpected_persistence_failures_mark_job_failed(failure):
    store = FailingPersistenceStore(failure)
    service = ResearchService(store, EvidenceScraperService(), FakeLLMProvider())
    job = service.create_job("https://example.com", "persistence failure")

    await service.run_job(job.job_id)

    failed = store.get(job.job_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "Research could not be completed."
    assert "secret" not in str(failed)


@pytest.mark.asyncio
async def test_provider_exception_degrades_to_source_backed_fallback():
    class FailingProvider:
        async def generate(self, context):
            raise RuntimeError("provider secret must not escape")

    store = InMemoryResearchJobStore()
    service = ResearchService(store, EvidenceScraperService(), FailingProvider())
    job = service.create_job("https://example.com", "fallback")
    await service.run_job(job.job_id)

    completed = store.get(job.job_id)
    assert completed is not None and completed.status == "completed"
    assert completed.limitations == ["LLM synthesis unavailable; the source-backed evidence remains the primary basis."]


def test_research_api_exposes_synthesis_and_safe_failure_fields():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, EvidenceScraperService(), FakeLLMProvider())
    app.dependency_overrides[get_research_store] = lambda: store
    app.dependency_overrides[get_research_service] = lambda: service
    client = TestClient(app)

    created = client.post("/api/v1/research", json={"url": "https://example.com", "query": "api"})
    job_id = created.json()["job_id"]
    asyncio.run(service.run_job(job_id))
    body = client.get(f"/api/v1/research/{job_id}").json()
    assert body["report"] == "Synthesized report"
    assert body["summary"] == "Synthesized summary"
    assert body["key_findings"] == ["Finding"]
    assert body["evidence_refs"] == ["https://example.com/"]
    assert body["claims"][0]["verification_status"] == "verified"
    assert body["entities"] == [{"name": "Example", "type": "document"}]
    app.dependency_overrides.clear()


def test_research_api_returns_safe_failed_job_error():
    class FailingScraper:
        async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
            raise RuntimeError("Authorization: Bearer secret-value")

    store = InMemoryResearchJobStore()
    service = ResearchService(store, FailingScraper())
    app.dependency_overrides[get_research_store] = lambda: store
    app.dependency_overrides[get_research_service] = lambda: service
    client = TestClient(app)
    created = client.post("/api/v1/research", json={"url": "https://example.com"})
    job_id = created.json()["job_id"]
    asyncio.run(service.run_job(job_id))
    body = client.get(f"/api/v1/research/{job_id}").json()
    assert body["status"] == "failed"
    assert body["error"] == "Research service is temporarily unavailable."
    assert "secret" not in str(body)
    assert client.get("/api/v1/research/missing").status_code == 404
    app.dependency_overrides.clear()


def test_research_api_reads_result_after_sqlite_store_recreation(tmp_path):
    database_path = tmp_path / "api-research.db"
    store = SqliteResearchJobStore(path=str(database_path))
    service = ResearchService(store, EvidenceScraperService(), FakeLLMProvider())
    app.dependency_overrides[get_research_store] = lambda: store
    app.dependency_overrides[get_research_service] = lambda: service
    client = TestClient(app)

    created = client.post("/api/v1/research", json={"url": "https://example.com", "query": "persist"})
    job_id = created.json()["job_id"]
    asyncio.run(service.run_job(job_id))

    recreated_store = SqliteResearchJobStore(path=str(database_path))
    app.dependency_overrides[get_research_store] = lambda: recreated_store
    body = client.get(f"/api/v1/research/{job_id}").json()
    assert body["status"] == "completed"
    assert body["report"] == "Synthesized report"
    assert body["result"]["data"]["evidence"][0]["snippet"] == "Supported evidence."
    app.dependency_overrides.clear()
