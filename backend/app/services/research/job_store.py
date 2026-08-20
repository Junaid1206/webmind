import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

from backend.app.core.config import settings
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
    report: str | None = None
    title: str | None = None
    summary: str | None = None
    key_findings: list[str] | None = None
    limitations: list[str] | None = None
    evidence_refs: list[str] | None = None
    confidence: float | None = None


class ResearchJobStore(Protocol):
    def create(self, url: str, query: str | None = None) -> ResearchJob: ...
    def get(self, job_id: str) -> ResearchJob | None: ...
    def begin_job(self, job_id: str) -> ResearchJob | None: ...
    def update_status(self, job_id: str, status: ResearchJobStatus) -> ResearchJob | None: ...
    def store_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None: ...
    def store_pending_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None: ...
    def store_error(self, job_id: str, error: str) -> ResearchJob | None: ...
    def list(self, status: ResearchJobStatus | None = None, limit: int = 20, offset: int = 0) -> list[ResearchJob]: ...


class InMemoryResearchJobStore:
    """Thread-safe MVP store used in tests and local execution."""

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

    def store_pending_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.status == "running":
                job.result = result
                job.error = None
                job.updated_at = utc_now()
            return job

    def store_error(self, job_id: str, error: str) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if job.status == "failed":
                    job.error = error
                    job.updated_at = utc_now()
                    return job
                job.error = error
                job.status = "failed"
                job.updated_at = utc_now()
            return job

    def store_llm_result(self, job_id: str, synthesis: dict[str, Any]) -> ResearchJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.report = synthesis.get("report")
            job.title = synthesis.get("title")
            job.summary = synthesis.get("summary")
            job.key_findings = synthesis.get("key_findings") or []
            job.limitations = synthesis.get("limitations") or []
            job.evidence_refs = synthesis.get("evidence_refs") or []
            job.confidence = synthesis.get("confidence")
            job.updated_at = utc_now()
            return job

    def list(self, status: ResearchJobStatus | None = None, limit: int = 20, offset: int = 0) -> list[ResearchJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [job for job in jobs if job.status == status]
        jobs.sort(key=lambda job: (job.created_at, job.created_index), reverse=True)
        return jobs[offset : offset + limit]


class SqliteResearchJobStore:
    """SQLite-backed research job persistence for the local MVP."""

    def __init__(self, database_url: str | None = None, *, path: str | None = None) -> None:
        if path is not None:
            self.db_path = path
        else:
            self.db_path = self._resolve_db_path(database_url or settings.database_url)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize_database()

    @staticmethod
    def _resolve_db_path(database_url: str | None) -> str:
        if not database_url:
            return str(Path.cwd() / "webmind.db")
        if database_url.startswith("sqlite://"):
            parsed = urlparse(database_url)
            if parsed.path and parsed.path != ":memory:":
                raw_path = parsed.path
                if raw_path.startswith("/./"):
                    raw_path = raw_path[3:]
                elif raw_path.startswith("/") and len(raw_path) > 2 and raw_path[1].isalpha() and raw_path[2] == ":":
                    raw_path = raw_path[1:]
                resolved = Path(raw_path)
                if not resolved.is_absolute():
                    resolved = (Path.cwd() / resolved).resolve()
                return str(resolved)
        return str(Path.cwd() / "webmind.db")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_database(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_jobs (
                    job_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    query TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    result_json TEXT,
                    report TEXT,
                    title TEXT,
                    summary TEXT,
                    key_findings TEXT,
                    limitations TEXT,
                    evidence_refs TEXT,
                    confidence REAL,
                    created_index INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(research_jobs)")}
            if "title" not in columns:
                conn.execute("ALTER TABLE research_jobs ADD COLUMN title TEXT")

    def create(self, url: str, query: str | None = None) -> ResearchJob:
        now = utc_now()
        job_id = str(uuid4())
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(created_index), 0) FROM research_jobs"
                )
                max_index = cursor.fetchone()[0] or 0
                index = max_index + 1
                conn.execute(
                    """
                    INSERT INTO research_jobs (
                        job_id, url, query, status, created_at, updated_at,
                        error, result_json, report, summary, key_findings,
                        limitations, evidence_refs, confidence, created_index
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)
                    """,
                    (
                        job_id,
                        url,
                        query,
                        "queued",
                        now.isoformat(),
                        now.isoformat(),
                        index,
                    ),
                )
        return self.get(job_id) or ResearchJob(
            job_id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
            url=url,
            query=query,
            created_index=index,
        )

    def get(self, job_id: str) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._hydrate_job(row)

    @staticmethod
    def _hydrate_job(row: sqlite3.Row) -> ResearchJob:
        result_json = row["result_json"]
        result = None
        if result_json:
            try:
                result = ScrapeResult.model_validate(json.loads(result_json))
            except Exception:
                result = None
        key_findings = json.loads(row["key_findings"]) if row["key_findings"] else []
        limitations = json.loads(row["limitations"]) if row["limitations"] else []
        evidence_refs = json.loads(row["evidence_refs"]) if row["evidence_refs"] else []
        return ResearchJob(
            job_id=row["job_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            url=row["url"],
            query=row["query"],
            result=result,
            error=row["error"],
            created_index=row["created_index"],
            report=row["report"],
            title=row["title"],
            summary=row["summary"],
            key_findings=key_findings,
            limitations=limitations,
            evidence_refs=evidence_refs,
            confidence=row["confidence"],
        )

    def begin_job(self, job_id: str) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None or row["status"] in {"running", "completed", "failed"}:
                    return None if row is None else self._hydrate_job(row)
                new_status = "running"
                updated_at = utc_now().isoformat()
                conn.execute(
                    "UPDATE research_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                    (new_status, updated_at, job_id),
                )
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._hydrate_job(row) if row is not None else None

    def update_status(self, job_id: str, status: ResearchJobStatus) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    return None
                if status == "running" and row["status"] in {"running", "completed", "failed"}:
                    return self._hydrate_job(row)
                if status in {"completed", "failed"} and row["status"] in {"completed", "failed"}:
                    return self._hydrate_job(row)
                updated_at = utc_now().isoformat()
                conn.execute(
                    "UPDATE research_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                    (status, updated_at, job_id),
                )
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._hydrate_job(row) if row is not None else None

    def store_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    return None
                if row["status"] in {"completed", "failed"}:
                    return self._hydrate_job(row)
                updated_at = utc_now().isoformat()
                conn.execute(
                    """
                    UPDATE research_jobs
                    SET result_json = ?, status = 'completed', error = NULL, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (json.dumps(result.model_dump(mode="json")), updated_at, job_id),
                )
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._hydrate_job(row) if row is not None else None

    def store_pending_result(self, job_id: str, result: ScrapeResult) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    return None
                if row["status"] != "running":
                    return self._hydrate_job(row)
                updated_at = utc_now().isoformat()
                conn.execute(
                    "UPDATE research_jobs SET result_json = ?, error = NULL, updated_at = ? WHERE job_id = ?",
                    (json.dumps(result.model_dump(mode="json")), updated_at, job_id),
                )
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._hydrate_job(row) if row is not None else None

    def store_error(self, job_id: str, error: str) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    return None
                updated_at = utc_now().isoformat()
                conn.execute(
                    "UPDATE research_jobs SET error = ?, status = 'failed', updated_at = ? WHERE job_id = ?",
                    (error, updated_at, job_id),
                )
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._hydrate_job(row) if row is not None else None

    def store_llm_result(self, job_id: str, synthesis: dict[str, Any]) -> ResearchJob | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
                if row is None:
                    return None
                updated_at = utc_now().isoformat()
                conn.execute(
                    """
                    UPDATE research_jobs
                    SET report = ?, title = ?, summary = ?, key_findings = ?, limitations = ?,
                        evidence_refs = ?, confidence = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        synthesis.get("report"),
                        synthesis.get("title"),
                        synthesis.get("summary"),
                        json.dumps(synthesis.get("key_findings") or []),
                        json.dumps(synthesis.get("limitations") or []),
                        json.dumps(synthesis.get("evidence_refs") or []),
                        synthesis.get("confidence"),
                        updated_at,
                        job_id,
                    ),
                )
                row = conn.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._hydrate_job(row) if row is not None else None

    def list(self, status: ResearchJobStatus | None = None, limit: int = 20, offset: int = 0) -> list[ResearchJob]:
        with self._lock:
            with self._connect() as conn:
                if status is None:
                    rows = conn.execute(
                        "SELECT * FROM research_jobs ORDER BY created_at DESC, created_index DESC LIMIT ? OFFSET ?",
                        (limit, offset),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM research_jobs WHERE status = ? ORDER BY created_at DESC, created_index DESC LIMIT ? OFFSET ?",
                        (status, limit, offset),
                    ).fetchall()
        return [self._hydrate_job(row) for row in rows]
