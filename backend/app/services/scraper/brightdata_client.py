import asyncio
from typing import Any

import httpx

from backend.app.core.config import settings


class BrightDataClient:
    """Async client for a Bright Data Scraper Studio custom dataset."""

    _BASE_URL = "https://api.brightdata.com"
    _REQUEST_TIMEOUT_SECONDS = 30.0
    _POLL_INTERVAL_SECONDS = 5.0
    _MAX_POLL_ATTEMPTS = 60

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = settings.brightdata_api_key
        self.collector_id = settings.brightdata_dataset_id
        self.transport = transport

    async def scrape(
        self,
        url: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "BRIGHTDATA_API_KEY is not configured."
            )

        if not self.collector_id:
            raise RuntimeError("BRIGHTDATA_DATASET_ID is not configured.")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        timeout = httpx.Timeout(self._REQUEST_TIMEOUT_SECONDS)
        try:
            async with httpx.AsyncClient(
                base_url=self._BASE_URL,
                headers=headers,
                timeout=timeout,
                transport=self.transport,
            ) as client:
                collection_id = await self._trigger(client, url)
                return await self._poll_for_results(client, collection_id)
        except httpx.TimeoutException as exc:
            raise RuntimeError("Bright Data request timed out.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Unable to reach Bright Data.") from exc

    async def _trigger(self, client: httpx.AsyncClient, url: str) -> str:
        payload: dict[str, str] = {"url": url}
        response = await client.post(
            "/dca/trigger",
            params={"collector": self.collector_id, "queue_next": "1"},
            json=[payload],
        )
        self._raise_for_status(response, "trigger collector")
        response_data = self._json(response, "triggering collector")
        collection_id = response_data.get("collection_id") if isinstance(response_data, dict) else None
        if not isinstance(collection_id, str) or not collection_id:
            raise RuntimeError("Bright Data did not return a collector run ID.")
        return collection_id

    async def _poll_for_results(
        self, client: httpx.AsyncClient, collection_id: str
    ) -> dict[str, Any]:
        for attempt in range(self._MAX_POLL_ATTEMPTS):
            response = await client.get("/dca/dataset", params={"id": collection_id})
            self._raise_for_status(response, "retrieve collector results")
            data = self._json(response, "retrieving collector results")
            if isinstance(data, list):
                return {"records": data}
            if not isinstance(data, dict):
                raise RuntimeError("Bright Data returned an unsupported collector result.")
            if str(data.get("status", "")).lower() in {"failed", "error", "cancelled", "canceled"}:
                raise RuntimeError("Bright Data collector failed.")
            if attempt < self._MAX_POLL_ATTEMPTS - 1:
                await asyncio.sleep(self._POLL_INTERVAL_SECONDS)
        raise TimeoutError("Bright Data collector run timed out.")

    @staticmethod
    def _json(response: httpx.Response, action: str) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Bright Data returned invalid JSON while {action}.") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Unable to {action} via Bright Data.") from exc
