from fastapi import FastAPI

app = FastAPI(
    title="WebMind API",
    version="0.1.0",
    description="Public-web research and intelligence API",
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "webmind-api",
        "version": "0.1.0",
    }