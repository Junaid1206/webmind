from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api.scraper import get_scraper_service
from backend.app.schemas.scraper import ScrapeResult, ScrapeSource


class FakeScraperService:
    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        return ScrapeResult(
            request_url=url,
            status="completed",
            data={
                "title": "Web scraping",
                "description": "Method of extracting data from websites",
            },
            sources=[ScrapeSource(url=url)],
            quality_score=0.8,
        )


def override_get_scraper_service():
    return FakeScraperService()


def test_scrape_endpoint():
    app.dependency_overrides[get_scraper_service] = override_get_scraper_service

    client = TestClient(app)

    response = client.post(
        "/api/v1/scrape",
        json={
            "url": "https://en.wikipedia.org/wiki/Web_scraping",
            "query": "web scraping",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "completed"
    assert body["data"]["title"] == "Web scraping"
    assert body["quality_score"] == 0.8

    app.dependency_overrides.clear()