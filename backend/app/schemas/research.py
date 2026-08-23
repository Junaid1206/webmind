from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from backend.app.schemas.scraper import ScrapeResult


ResearchJobStatus = Literal["queued", "running", "completed", "failed"]


class ResearchRequest(BaseModel):
    # Query must be mandatory and URL should be optional
    query: str = Field(min_length=1, max_length=1000)
    url: HttpUrl | str | None = Field(default=None)


class ResearchJobResponse(BaseModel):
    job_id: str
    status: ResearchJobStatus
    created_at: datetime
    updated_at: datetime
    # URL can be None when user runs research without a link
    url: HttpUrl | str | None = None
    query: str | None = None
    result: ScrapeResult | None = None
    error: str | None = None
    title: str | None = None
    report: str | None = None
    summary: str | None = None
    llm_generated_claims: list[str] = Field(default_factory=list)
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