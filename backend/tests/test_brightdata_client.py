import pytest

from backend.app.services.scraper.brightdata_client import BrightDataClient


@pytest.mark.asyncio
async def test_scrape_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.scraper.brightdata_client.settings.brightdata_api_key",
        None,
    )
    monkeypatch.setattr(
        "backend.app.services.scraper.brightdata_client.settings.brightdata_zone",
        "test-zone",
    )

    client = BrightDataClient()

    with pytest.raises(
        RuntimeError,
        match="BRIGHTDATA_API_KEY is not configured",
    ):
        await client.scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_requires_zone(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.scraper.brightdata_client.settings.brightdata_api_key",
        "test-key",
    )
    monkeypatch.setattr(
        "backend.app.services.scraper.brightdata_client.settings.brightdata_zone",
        None,
    )

    client = BrightDataClient()

    with pytest.raises(
        RuntimeError,
        match="BRIGHTDATA_ZONE is not configured",
    ):
        await client.scrape("https://example.com")