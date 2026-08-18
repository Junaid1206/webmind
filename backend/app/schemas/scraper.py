from typing import Any
from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl
    query: str | None = None


class ScrapeSource(BaseModel):
    url: HttpUrl
    title: str | None = None


class ScrapeResult(BaseModel):
    request_url: HttpUrl
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[ScrapeSource] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)