from fastapi import FastAPI

from backend.app.api.scraper import router as scraper_router

app = FastAPI(
    title="WebMind API",
    version="0.1.0",
    description="Public-web research and intelligence API",
)

app.include_router(scraper_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "webmind-api",
        "version": "0.1.0",
    }