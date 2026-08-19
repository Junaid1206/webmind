import pytest

from backend.app.schemas.scraper import ScrapeResult
from backend.app.services.scraper.scraper_service import ScraperService


class FakeBrightDataClient:
    async def scrape(self, url: str, query: str | None = None) -> dict:
        return {
            "title": "Web scraping",
            "description": "Method of extracting data from websites",
            "content": "Example scraped content",
            "source_domain": "en.wikipedia.org",
        }


@pytest.mark.asyncio
async def test_scraper_service_returns_scrape_result():
    service = ScraperService(FakeBrightDataClient())

    result = await service.scrape(
        url="https://en.wikipedia.org/wiki/Web_scraping",
        query="web scraping",
    )

    assert isinstance(result, ScrapeResult)
    assert result.status == "completed"
    assert str(result.request_url) == "https://en.wikipedia.org/wiki/Web_scraping"
    assert result.data["title"] == "Web scraping"
    assert str(result.sources[0].url) == "https://en.wikipedia.org/wiki/Web_scraping"
    assert result.quality_score == 0.0