import pytest

from backend.app.schemas.scraper import ScrapeResult
from backend.app.services.scraper.scraper_service import ScraperService


class FakeWebPageClient:
    async def scrape(self, url: str, query: str | None = None) -> dict:
        return {
            "title": "Web scraping",
            "description": "Method of extracting data from websites",
            "content": "Example scraped content",
            "source_domain": "en.wikipedia.org",
        }


@pytest.mark.asyncio
async def test_scraper_service_returns_scrape_result():
    service = ScraperService(FakeWebPageClient())

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


@pytest.mark.asyncio
async def test_scraper_service_attaches_evidence_and_quality_for_collector_records():
    class CollectorClient:
        async def scrape(self, url: str, query: str | None = None) -> dict:
            return {"records": [{"url": url, "title": "Example", "content": "Supported fact."}]}

    result = await ScraperService(CollectorClient()).scrape("https://example.com")

    assert result.data["evidence"] == [{"source_url": "https://example.com", "snippet": "Supported fact."}]
    assert result.data["entities"] == [{"name": "Example", "type": "document"}]
    assert result.data["relationships"] == [{
        "subject": "Example",
        "predicate": "sourced_from",
        "object": "https://example.com",
    }]
    assert result.quality_score == 0.9

@pytest.mark.asyncio
async def test_scraper_service_rejects_empty_extraction():
    class EmptyClient:
        async def scrape(self, url: str, query: str | None = None) -> dict:
            return {"records": [{"url": url, "title": "No content"}]}

    with pytest.raises(RuntimeError, match="CONTENT_EXTRACTION_FAILED"):
        await ScraperService(EmptyClient()).scrape("https://example.com")
