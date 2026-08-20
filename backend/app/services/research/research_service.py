import asyncio
import logging

from backend.app.services.research.job_store import ResearchJob, ResearchJobStore
from backend.app.services.scraper.scraper_service import ScraperService

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(self, store: ResearchJobStore, scraper: ScraperService) -> None:
        self.store = store
        self.scraper = scraper

    def create_job(self, url: str, query: str | None = None) -> ResearchJob:
        return self.store.create(url, query)

    def start_job(self, job: ResearchJob) -> None:
        asyncio.create_task(self.run_job(job.job_id))

    async def run_job(self, job_id: str) -> None:
        job = self.store.begin_job(job_id)
        if job is None:
            return
        try:
            result = await self.scraper.scrape(job.url, job.query)
        except (RuntimeError, TimeoutError):
            self.store.store_error(job_id, "Research service is temporarily unavailable.")
        except Exception:
            logger.exception("Research job %s failed unexpectedly", job_id)
            self.store.store_error(job_id, "Research could not be completed.")
        else:
            self.store.store_result(job_id, result)
