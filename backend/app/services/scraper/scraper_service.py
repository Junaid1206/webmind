from backend.app.schemas.scraper import ScrapeResult, ScrapeSource
from backend.app.services.scraper.brightdata_client import BrightDataClient


class ScraperService:
    def __init__(self, client: BrightDataClient):
        self.client = client

    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        raw = await self.client.scrape(url=url, query=query)

        return ScrapeResult(
            request_url=url,
            status="completed",
            data=raw,
            sources=[
                ScrapeSource(url=url)
            ],
            quality_score=0.0,
        )