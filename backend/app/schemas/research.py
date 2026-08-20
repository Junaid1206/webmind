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
    title: str | None = None
    report: str | None = None
    summary: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None
    claims: list[dict] = Field(default_factory=list)
    entities: list[dict] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)


class ResearchHistoryResponse(BaseModel):
    items: list[ResearchJobResponse]
    limit: int
    offset: int
