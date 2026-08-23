from contextlib import asynccontextmanager
from collections import defaultdict, deque
from time import monotonic
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi import Request, Response

from backend.app.api.scraper import router as scraper_router
from backend.app.api.research import router as research_router
from backend.app.core.config import settings
from backend.app.services.research.job_store import SqliteResearchJobStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.research_store = SqliteResearchJobStore()
    application.state.rate_limit_buckets = defaultdict(deque)
    if not settings.llm_api_key:
        logger.warning(
            "LLM_API_KEY is not configured. Research jobs will still complete using "
            "source-backed evidence, but AI synthesis (report/summary/claims) will be "
            "degraded/skipped. Set LLM_API_KEY in .env to enable full synthesis."
        )
    if settings.webmind_api_key:
        logger.warning(
            "WEBMIND_API_KEY is configured, so all /api/v1/* requests now require an "
            "X-API-Key or Authorization: Bearer header. The bundled frontend does not "
            "send this header by default -- make sure that's intentional."
        )
    yield

app = FastAPI(
    title="WebMind API",
    version="0.1.0",
    description="Public-web research and intelligence API",
    lifespan=lifespan,
)


@app.middleware("http")
async def paid_call_rate_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path in {"/api/v1/research", "/api/v1/scrape"}:
        now = monotonic()
        buckets = getattr(request.app.state, "rate_limit_buckets", None)
        if buckets is None:
            buckets = request.app.state.rate_limit_buckets = defaultdict(deque)
        bucket = buckets[request.client.host if request.client else "unknown"]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit_per_minute:
            return Response("Rate limit exceeded.", status_code=429)
        bucket.append(now)
    return await call_next(request)

app.include_router(scraper_router)
app.include_router(research_router)


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    """Serve the lightweight research dashboard."""
    return FileResponse(Path(__file__).with_name("static") / "index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "webmind-api",
        "version": "0.1.0",
    }
