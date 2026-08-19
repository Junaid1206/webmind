from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.schemas.scraper import ScrapeRequest, ScrapeResult
from backend.app.services.scraper.brightdata_client import BrightDataClient
from backend.app.services.scraper.scraper_service import ScraperService

router = APIRouter(prefix="/api/v1/scrape", tags=["scraper"])


def get_scraper_service() -> ScraperService:
    return ScraperService(BrightDataClient())


@router.post("", response_model=ScrapeResult)
async def scrape(
    request: ScrapeRequest,
    service: ScraperService = Depends(get_scraper_service),
) -> ScrapeResult:
    try:
        return await service.scrape(url=str(request.url), query=request.query)
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scraping service is temporarily unavailable.",
        ) from exc
