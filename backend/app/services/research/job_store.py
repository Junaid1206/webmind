from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Protocol
from uuid import uuid4

from backend.app.schemas.research import ResearchJobStatus
from backend.app.schemas.scraper import ScrapeResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ResearchJob:
    job_id: str
    status: ResearchJobStatus
    created_at: datetime
    updated_at: datetime
    url: str
    query: str | None = None
    result: ScrapeResult | None = None
    error: str | None = None
    created_index: int = 0


class ResearchJobStore(Protocol):
    def create(self, url: str, query: str | None = None) -> ResearchJob: ...
    def get(self, job_id: str) -> ResearchJob | None: ...
    def begin_job(self, job_id: str) -> ResearchJob | None: ...
    def update_status(self, job_id: str, status: ResearchJobStatus) -> ResearchJob | None: ...
    def store_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None: ...
    def store_error(self, job_id: str, error: str) -> ResearchJob | None: ...
    def list(self, status: ResearchJobStatus | None = None, limit: int = 20, offset: int = 0) -> list[ResearchJob]: ...


class InMemoryResearchJobStore:
    """Thread-safe MVP store; replaceable with a persistent repository later."""

    def __init__(self) -> None:
        self._jobs: dict[str, ResearchJob] = {}
        self._lock = Lock()
        self._next_index = 0

    def create(self, url: str, query: str | None = None) -> ResearchJob:
        now = utc_now()
        self._next_index += 1
        job = ResearchJob(
            job_id=str(uuid4()), status="queued", created_at=now, updated_at=now,
            url=url, query=query, created_index=self._next_index,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> ResearchJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def begin_job(self, job_id: str) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"running", "completed", "failed"}:
                return None
            job.status = "running"
            job.updated_at = utc_now()
            return job

    def update_status(self, job_id: str, status: ResearchJobStatus) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if status == "running" and job.status in {"running", "completed", "failed"}:
                return job
            if status in {"completed", "failed"} and job.status in {"completed", "failed"}:
                return job
            job.status = status
            job.updated_at = utc_now()
            return job

    def store_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.status in {"completed", "failed"}:
                    return job
                job.result = result
                job.error = None
                job.status = "completed"
                job.updated_at = utc_now()
            return job

    def store_error(self, job_id: str, error: str) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.status in {"completed", "failed"}:
                    return job
                job.error = error
                job.status = "failed"
                job.updated_at = utc_now()
            return job

    def list(self, status: ResearchJobStatus | None = None, limit: int = 20, offset: int = 0) -> list[ResearchJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [job for job in jobs if job.status == status]
        jobs.sort(key=lambda job: (job.created_at, job.created_index), reverse=True)
        return jobs[offset : offset + limit]
