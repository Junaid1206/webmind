from backend.app.schemas.scraper import ScrapeResult, ScrapeSource
from backend.app.services.scraper.brightdata_client import BrightDataClient
from backend.app.services.scraper.intelligence_service import IntelligenceService


class ScraperService:
    def __init__(self, client: BrightDataClient, intelligence: IntelligenceService | None = None):
        self.client = client
        self.intelligence = intelligence or IntelligenceService()

    async def scrape(self, url: str, query: str | None = None) -> ScrapeResult:
        raw = await self.client.scrape(url=url, query=query)

        data, sources, quality_score = self.intelligence.enrich(raw, url)
        return ScrapeResult(
            request_url=url,
            status="completed",
            data=data,
            sources=[
                ScrapeSource(**source) for source in sources
            ],
            quality_score=quality_score,
        )
