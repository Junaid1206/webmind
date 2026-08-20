from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.scraper import get_scraper_service
from backend.app.schemas.research import (
    ResearchHistoryResponse,
    ResearchJobResponse,
    ResearchJobStatus,
    ResearchRequest,
)
from backend.app.services.research.job_store import InMemoryResearchJobStore, ResearchJob, SqliteResearchJobStore
from backend.app.services.research.research_service import ResearchService
from backend.app.services.scraper.scraper_service import ScraperService

router = APIRouter(prefix="/api/v1/research", tags=["research"])
_store = SqliteResearchJobStore()


def get_research_store() -> SqliteResearchJobStore:
    return _store


def get_research_service(
    store: Annotated[SqliteResearchJobStore, Depends(get_research_store)],
    scraper: Annotated[ScraperService, Depends(get_scraper_service)],
) -> ResearchService:
    return ResearchService(store, scraper)


def serialize_job(job: ResearchJob) -> ResearchJobResponse:
    data = job.result.data if job.result is not None else {}
    return ResearchJobResponse(
        job_id=job.job_id, status=job.status, created_at=job.created_at,
        updated_at=job.updated_at, url=job.url, query=job.query,
        result=job.result, error=job.error,
        title=job.title,
        report=job.report,
        summary=job.summary,
        key_findings=job.key_findings or [],
        limitations=job.limitations or [],
        evidence_refs=job.evidence_refs or [],
        confidence=job.confidence,
        claims=data.get("claims") or [],
        entities=data.get("entities") or [],
        relationships=data.get("relationships") or [],
        sources=[source.model_dump(mode="json") for source in (job.result.sources if job.result else [])],
    )


def find_job(job_id: str, store: SqliteResearchJobStore) -> ResearchJob:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research job not found.")
    return job


@router.post("", response_model=ResearchJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_research_job(
    request: ResearchRequest,
    service: Annotated[ResearchService, Depends(get_research_service)],
) -> ResearchJobResponse:
    job = service.create_job(str(request.url), request.query)
    service.start_job(job)
    return serialize_job(job)


@router.get("", response_model=ResearchHistoryResponse)
async def list_research_jobs(
    store: Annotated[SqliteResearchJobStore, Depends(get_research_store)],
    job_status: Annotated[ResearchJobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ResearchHistoryResponse:
    jobs = store.list(status=job_status, limit=limit, offset=offset)
    return ResearchHistoryResponse(items=[serialize_job(job) for job in jobs], limit=limit, offset=offset)


@router.get("/{job_id}", response_model=ResearchJobResponse)
async def get_research_job(
    job_id: str,
    store: Annotated[SqliteResearchJobStore, Depends(get_research_store)],
) -> ResearchJobResponse:
    return serialize_job(find_job(job_id, store))
