import logging
from typing import Any, Optional

from backend.app.schemas.scraper import ScrapeResult
from backend.app.services.scraper.intelligence_service import IntelligenceService

logger = logging.getLogger(__name__)


class ScraperService:
    def __init__(
        self,
        web_client: Any = None,
        fallback_client: Any = None,
    ) -> None:
        self.web_client = web_client
        self.fallback_client = fallback_client
        self.intelligence_service = IntelligenceService()

    async def scrape(self, url: str, query: Optional[str] = None) -> ScrapeResult:
        """
        Scrapes content from the target URL and guarantees a valid ScrapeResult return.

        Primary scraper (web_client) succeeds -> use its result.
        Primary scraper fails -> fallback_client is used if configured.
        Both fail -> RuntimeError propagates to the caller (API layer maps
        this to a 503, and the research pipeline treats it as a failed job).
        """
        logger.info("Starting scrape for URL: %s", url)

        raw: dict[str, Any] = {}

        if self.web_client and hasattr(self.web_client, "scrape"):
            try:
                res = await self.web_client.scrape(url, query)
                raw = res if isinstance(res, dict) else {}
            except Exception as exc:
                logger.warning("Primary web_client failed for %s: %s", url, exc)

                if self.fallback_client and hasattr(self.fallback_client, "scrape"):
                    logger.info("Falling back to secondary scraper for %s", url)
                    res = await self.fallback_client.scrape(url, query)
                    raw = res if isinstance(res, dict) else {}
                else:
                    raise

        has_record_collection = isinstance(raw.get("records"), list)
        data, sources, quality_score = self.intelligence_service.enrich(raw, url)

        # If the client explicitly returned a records collection but none of
        # those records yielded usable evidence, treat this as a failed
        # extraction rather than silently returning an empty success.
        if has_record_collection and not data.get("evidence"):
            raise RuntimeError(
                "CONTENT_EXTRACTION_FAILED: no usable content extracted from scraped records."
            )

        data.setdefault("title", query or "Web Scrape Analysis")
        data.setdefault("claims", [])
        data.setdefault("entities", [])
        data.setdefault("relationships", [])

        return ScrapeResult(
            status="completed",
            request_url=url,
            quality_score=quality_score,
            sources=sources,
            data=data,
        )