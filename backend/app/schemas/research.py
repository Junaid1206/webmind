from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from backend.app.schemas.scraper import ScrapeResult


ResearchJobStatus = Literal["queued", "running", "completed", "failed"]


class ResearchRequest(BaseModel):
    url: HttpUrl
    query: str | None = Field(default=None, max_length=1000)


class ResearchJobResponse(BaseModel):
    job_id: str
    status: ResearchJobStatus
    created_at: datetime
    updated_at: datetime
    url: HttpUrl
    query: str | None = None
    result: ScrapeResult | None = None
    error: str | None = None


class ResearchHistoryResponse(BaseModel):
    items: list[ResearchJobResponse]
    limit: int
    offset: int
