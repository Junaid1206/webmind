from typing import Any


class BrightDataClient:
    """
    Boundary for the Bright Data custom scraper.

    The real Scraper Studio integration will be implemented here.
    """

    async def scrape(self, url: str, query: str | None = None) -> dict[str, Any]:
        raise NotImplementedError(
            "Bright Data Scraper Studio integration is not configured yet."
        )
