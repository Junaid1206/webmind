import json

import httpx
import pytest

from backend.app.services.scraper.brightdata_client import BrightDataClient


def configure_client(
    monkeypatch,
    *,
    api_key: str | None = "test-key",
    collector_id: str | None = "c_test",
) -> None:
    monkeypatch.setattr(
        "backend.app.services.scraper.brightdata_client.settings.brightdata_api_key",
        api_key,
    )
    monkeypatch.setattr(
        "backend.app.services.scraper.brightdata_client.settings.brightdata_dataset_id",
        collector_id,
    )


@pytest.mark.asyncio
async def test_scrape_requires_api_key(monkeypatch):
    configure_client(monkeypatch, api_key=None)

    with pytest.raises(RuntimeError, match="BRIGHTDATA_API_KEY is not configured"):
        await BrightDataClient().scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_requires_collector_id(monkeypatch):
    configure_client(monkeypatch, collector_id=None)

    with pytest.raises(RuntimeError, match="BRIGHTDATA_DATASET_ID is not configured"):
        await BrightDataClient().scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_uses_scraper_studio_trigger_and_dataset_contract(monkeypatch):
    configure_client(monkeypatch)
    responses = iter(
        [
            {"status": "building"},
            [{"title": "Example", "url": "https://example.com"}],
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.url.path == "/dca/trigger":
            assert request.url.params["collector"] == "c_test"
            assert request.url.params["queue_next"] == "1"
            assert json.loads(request.content) == [{"url": "https://example.com"}]
            return httpx.Response(200, json={"collection_id": "j_run"})
        assert request.url.path == "/dca/dataset"
        assert request.url.params["id"] == "j_run"
        return httpx.Response(200, json=next(responses))

    client = BrightDataClient(transport=httpx.MockTransport(handler))
    client._POLL_INTERVAL_SECONDS = 0

    result = await client.scrape("https://example.com", "example")

    assert result == {
        "records": [{"title": "Example", "url": "https://example.com"}]
    }


@pytest.mark.asyncio
async def test_scrape_converts_http_errors_without_exposing_response_body(monkeypatch):
    configure_client(monkeypatch)
    client = BrightDataClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, text="secret")
        )
    )

    with pytest.raises(
        RuntimeError, match="Unable to trigger collector via Bright Data"
    ) as exc_info:
        await client.scrape("https://example.com")

    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_scrape_rejects_invalid_json(monkeypatch):
    configure_client(monkeypatch)
    client = BrightDataClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not-json")
        )
    )

    with pytest.raises(RuntimeError, match="invalid JSON while triggering collector"):
        await client.scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_rejects_malformed_trigger_response(monkeypatch):
    configure_client(monkeypatch)
    client = BrightDataClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"snapshot_id": "s_wrong"})
        )
    )

    with pytest.raises(RuntimeError, match="did not return a collector run ID"):
        await client.scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_rejects_invalid_json_while_polling(monkeypatch):
    configure_client(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/dca/trigger":
            return httpx.Response(200, json={"collection_id": "j_run"})
        return httpx.Response(200, text="not-json")

    client = BrightDataClient(transport=httpx.MockTransport(handler))

    with pytest.raises(
        RuntimeError, match="invalid JSON while retrieving collector results"
    ):
        await client.scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_rejects_malformed_polling_response(monkeypatch):
    configure_client(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/dca/trigger":
            return httpx.Response(200, json={"collection_id": "j_run"})
        return httpx.Response(200, json="not-a-result")

    client = BrightDataClient(transport=httpx.MockTransport(handler))

    with pytest.raises(RuntimeError, match="unsupported collector result"):
        await client.scrape("https://example.com")


@pytest.mark.asyncio
async def test_scrape_times_out_when_collector_never_returns_a_dataset(monkeypatch):
    configure_client(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/dca/trigger":
            return httpx.Response(200, json={"collection_id": "j_run"})
        return httpx.Response(200, json={"status": "building"})

    client = BrightDataClient(transport=httpx.MockTransport(handler))
    client._MAX_POLL_ATTEMPTS = 1

    with pytest.raises(TimeoutError, match="Bright Data collector run timed out"):
        await client.scrape("https://example.com")
