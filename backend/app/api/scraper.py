import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.security import require_api_key

logger = logging.getLogger(__name__)
from backend.app.schemas.scraper import ScrapeRequest, ScrapeResult
from backend.app.services.scraper.scraper_service import ScraperService
from backend.app.services.scraper.web_page_client import WebPageClient
from backend.app.services.scraper.brightdata_client import BrightDataClient

router = APIRouter(prefix="/api/v1/scrape", tags=["scraper"], dependencies=[Depends(require_api_key)])


def get_scraper_service() -> ScraperService:
    return ScraperService(WebPageClient(), fallback_client=BrightDataClient())


@router.post("", response_model=ScrapeResult)
async def scrape(
    request: ScrapeRequest,
    service: ScraperService = Depends(get_scraper_service),
) -> ScrapeResult:
    try:
        return await service.scrape(url=str(request.url), query=request.query)
    except (RuntimeError, TimeoutError) as exc:
        logger.error("Scrape request failed (error_type=%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scraping service is temporarily unavailable.",
        ) from exc

