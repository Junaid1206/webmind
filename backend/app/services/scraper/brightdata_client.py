import asyncio
import json
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class BrightDataClient:
    """Async client for a Bright Data Scraper Studio custom dataset."""

    _BASE_URL = "https://api.brightdata.com"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = settings.brightdata_api_key
        self.collector_id = (
            settings.brightdata_collector_id
            or settings.brightdata_dataset_id
        )
        self.transport = transport

        self.request_timeout_seconds = (
            settings.brightdata_request_timeout_seconds
        )
        self.poll_interval_seconds = (
            settings.brightdata_poll_interval_seconds
        )
        self.max_poll_attempts = (
            settings.brightdata_max_poll_attempts
        )

        self._REQUEST_TIMEOUT_SECONDS = self.request_timeout_seconds
        self._POLL_INTERVAL_SECONDS = self.poll_interval_seconds
        self._MAX_POLL_ATTEMPTS = self.max_poll_attempts

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
            raise RuntimeError(
                "BRIGHTDATA_DATASET_ID is not configured."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json, application/jsonl, text/plain",
        }

        timeout = httpx.Timeout(self._REQUEST_TIMEOUT_SECONDS)

        try:
            async with httpx.AsyncClient(
                base_url=self._BASE_URL,
                headers=headers,
                timeout=timeout,
                transport=self.transport,
            ) as client:
                collection_id = await self._trigger(client, url)

                logger.info(
                    "Bright Data collection started (collection_id=%s, url=%s)",
                    collection_id,
                    url,
                )

                return await self._poll_for_results(
                    client,
                    collection_id,
                )

        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "Bright Data request timed out."
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                "Unable to reach Bright Data."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "Bright Data service returned a temporary error."
            ) from exc

    @retry(
        retry=retry_if_exception_type(
            (
                httpx.TimeoutException,
                httpx.RequestError,
                httpx.HTTPStatusError,
            )
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(
            multiplier=0.2,
            min=0.2,
            max=2,
        ),
        reraise=True,
    )
    async def _trigger(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> str:
        payload: dict[str, str] = {
            "url": url,
        }

        response = await client.post(
            "/dca/trigger",
            params={
                "collector": self.collector_id,
                "queue_next": "1",
            },
            json=[payload],
        )

        self._raise_for_status(
            response,
            "trigger collector",
        )

        response_data = self._json(
            response,
            "triggering collector",
        )

        collection_id = (
            response_data.get("collection_id")
            if isinstance(response_data, dict)
            else None
        )

        if not isinstance(collection_id, str) or not collection_id:
            raise RuntimeError(
                "Bright Data did not return a collector run ID."
            )

        return collection_id

    async def _poll_for_results(
        self,
        client: httpx.AsyncClient,
        collection_id: str,
    ) -> dict[str, Any]:
        for attempt in range(self._MAX_POLL_ATTEMPTS):
            response = await self._poll_request(
                client,
                collection_id,
            )

            self._raise_for_status(
                response,
                "retrieve collector results",
            )

            # Bright Data can return application/jsonl.
            data = self._parse_dataset_response(
                response,
                collection_id,
            )

            # Empty JSONL body means the collection is still processing.
            if data is None:
                if attempt < self._MAX_POLL_ATTEMPTS - 1:
                    logger.info(
                        "Bright Data collection still processing "
                        "(collection_id=%s, attempt=%s/%s)",
                        collection_id,
                        attempt + 1,
                        self._MAX_POLL_ATTEMPTS,
                    )

                    await asyncio.sleep(
                        self._POLL_INTERVAL_SECONDS
                    )
                    continue

                raise TimeoutError(
                    "Bright Data collector run timed out."
                )

            if isinstance(data, list):
                return {
                    "records": data,
                }

            if isinstance(data, dict):
                status = str(
                    data.get("status", "")
                ).lower()

                if status in {
                    "failed",
                    "error",
                    "cancelled",
                    "canceled",
                }:
                    raise RuntimeError(
                        "Bright Data collector failed."
                    )

                # Some Bright Data responses may contain records
                # under a data/results/records key.
                for key in (
                    "records",
                    "data",
                    "results",
                    "items",
                ):
                    value = data.get(key)

                    if isinstance(value, list):
                        return {
                            "records": value,
                        }

                # A status-only response means the job is still running.
                if status in {
                    "",
                    "running",
                    "pending",
                    "processing",
                    "queued",
                    "in_progress",
                    "in-progress",
                }:
                    if attempt < self._MAX_POLL_ATTEMPTS - 1:
                        await asyncio.sleep(
                            self._POLL_INTERVAL_SECONDS
                        )
                        continue

                    raise TimeoutError(
                        "Bright Data collector run timed out."
                    )

                # If Bright Data returned a single record object,
                # preserve it rather than throwing it away.
                return {
                    "records": [data],
                }

            raise RuntimeError(
                "Bright Data returned an unsupported collector result."
            )

        raise TimeoutError(
            "Bright Data collector run timed out."
        )

    @retry(
        retry=retry_if_exception_type(
            (
                httpx.TimeoutException,
                httpx.RequestError,
                httpx.HTTPStatusError,
            )
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(
            multiplier=0.2,
            min=0.2,
            max=2,
        ),
        reraise=True,
    )
    async def _poll_request(
        self,
        client: httpx.AsyncClient,
        collection_id: str,
    ) -> httpx.Response:
        response = await client.get(
            "/dca/dataset",
            params={
                "id": collection_id,
            },
        )

        if response.status_code >= 500:
            response.raise_for_status()

        return response

    @staticmethod
    def _parse_dataset_response(
        response: httpx.Response,
        collection_id: str,
    ) -> Any:
        """
        Parse Bright Data dataset responses.

        Bright Data may return:
        - application/json
        - application/jsonl
        - text/plain containing JSONL
        - an empty body while the collection is still processing
        """

        body = response.text.strip()

        content_type = (
            response.headers.get("content-type", "")
            .split(";")[0]
            .strip()
            .lower()
        )

        logger.info(
            "Bright Data dataset response "
            "(collection_id=%s, status=%s, content_type=%s, body_length=%s)",
            collection_id,
            response.status_code,
            content_type,
            len(body),
        )

        # Empty 200 response is common while the dataset is not ready.
        if not body:
            return None

        # First try normal JSON.
        try:
            return response.json()
        except ValueError:
            pass

        # Handle JSONL.
        records: list[Any] = []

        for line_number, line in enumerate(
            body.splitlines(),
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                records.append(
                    json.loads(line)
                )
            except json.JSONDecodeError as exc:
                logger.error(
                    "Bright Data returned malformed JSONL "
                    "(collection_id=%s, line=%s, content_type=%s, body=%s)",
                    collection_id,
                    line_number,
                    content_type,
                    line[:1000],
                )

                raise RuntimeError(
                    "Bright Data returned malformed JSONL "
                    "while retrieving collector results."
                ) from exc

        if records:
            return records

        logger.error(
            "Bright Data returned an unsupported response "
            "(collection_id=%s, status=%s, content_type=%s, body=%s)",
            collection_id,
            response.status_code,
            content_type,
            body[:1000],
        )

        raise RuntimeError(
            "Bright Data returned an unsupported collector response."
        )

    @staticmethod
    def _json(
        response: httpx.Response,
        action: str,
    ) -> Any:
        try:
            return response.json()

        except ValueError as exc:
            logger.error(
                "Bright Data returned non-JSON response while %s "
                "(status=%s, content_type=%s, body=%s)",
                action,
                response.status_code,
                response.headers.get("content-type"),
                response.text[:1000],
            )

            raise RuntimeError(
                f"Bright Data returned invalid JSON while {action}."
            ) from exc

    @staticmethod
    def _raise_for_status(
        response: httpx.Response,
        action: str,
    ) -> None:
        try:
            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            if response.status_code >= 500:
                raise exc

            raise RuntimeError(
                f"Unable to {action} via Bright Data."
            ) from exc
