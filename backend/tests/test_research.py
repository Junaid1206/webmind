import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app.api.research import get_research_service, get_research_store
from backend.app.main import app
from backend.app.schemas.scraper import ScrapeResult, ScrapeSource
from backend.app.services.research.job_store import InMemoryResearchJobStore
from backend.app.services.research.research_service import ResearchService


class FakeScraperService:
    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        return ScrapeResult(request_url=url, status="completed", data={"title": query or "Result"}, sources=[ScrapeSource(url=url)], quality_score=0.8)


@pytest.mark.asyncio
async def test_research_service_completes_a_job():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService())
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
    service = ResearchService(store, BlockingScraperService())
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
    service = ResearchService(store, FailingScraperService())
    job = service.create_job("https://example.com")
    await service.run_job(job.job_id)

    failed = store.get(job.job_id)
    assert failed is not None and failed.status == "failed"
    assert failed.error == "Research service is temporarily unavailable."
    assert "secret" not in failed.error


@pytest.mark.asyncio
async def test_research_service_runs_independent_jobs_concurrently():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService())
    first = service.create_job("https://example.com", "first")
    second = service.create_job("https://example.org", "second")

    await asyncio.gather(service.run_job(first.job_id), service.run_job(second.job_id))

    assert store.get(first.job_id).result.data["title"] == "first"
    assert store.get(second.job_id).result.data["title"] == "second"


@pytest.mark.asyncio
async def test_research_service_ignores_duplicate_starts_for_same_job():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService())
    job = service.create_job("https://example.com", "dup")

    await asyncio.gather(service.run_job(job.job_id), service.run_job(job.job_id))

    assert store.get(job.job_id).status == "completed"


def test_research_api_lifecycle_history_and_validation():
    store = InMemoryResearchJobStore()
    service = ResearchService(store, FakeScraperService())
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
