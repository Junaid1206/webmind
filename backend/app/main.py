from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from backend.app.api.scraper import router as scraper_router
from backend.app.api.research import router as research_router

app = FastAPI(
    title="WebMind API",
    version="0.1.0",
    description="Public-web research and intelligence API",
)

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
