from typing import Any

from backend.app.core.config import settings


class BrightDataClient:
    """
    Client boundary for Bright Data scraper integration.

    The API call will be added once the Bright Data API
    credentials and endpoint are configured.
    """

    def __init__(self) -> None:
        self.api_key = settings.brightdata_api_key
        self.zone = settings.brightdata_zone

    async def scrape(
        self,
        url: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "BRIGHTDATA_API_KEY is not configured."
            )

        if not self.zone:
            raise RuntimeError(
                "BRIGHTDATA_ZONE is not configured."
            )

        raise NotImplementedError(
            "Bright Data Scraper Studio API integration is not implemented yet."
        )