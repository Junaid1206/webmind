"""Generic public-web HTML fetcher."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


class WebPageClient:
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.max_attempts = max(1, max_attempts)

    async def scrape(self, url: str, query: str | None = None) -> dict[str, Any]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

        timeout = httpx.Timeout(self.timeout_seconds)
        last_error: Exception | None = None

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=10,
            headers=headers,
            transport=self.transport,
            trust_env=True,
        ) as client:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = await client.get(url)
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_attempts:
                        retry_after = response.headers.get("retry-after")
                        try:
                            delay = min(float(retry_after), 5.0) if retry_after else 0.5 * attempt
                        except ValueError:
                            delay = 0.5 * attempt
                        await asyncio.sleep(delay)
                        continue
                    response.raise_for_status()
                    break
                except httpx.TimeoutException as exc:
                    last_error = exc
                    if attempt < self.max_attempts:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise RuntimeError("Target website request timed out.") from exc
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    raise RuntimeError(
                        f"Target website returned HTTP {status_code}."
                    ) from exc
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt < self.max_attempts:
                        await asyncio.sleep(0.5 * attempt)
                        continue
                    raise RuntimeError("Unable to reach target website.") from exc
            else:
                raise RuntimeError("Unable to fetch target website.") from last_error

        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "xhtml" not in content_type:
            raise RuntimeError(
                f"Unsupported target content type: {content_type or 'unknown'}."
            )

        html = response.text
        if not html.strip():
            raise RuntimeError("Target website returned an empty HTML response.")

        record = self._parse_html(html, str(response.url), query)
        if len(record["content"].strip()) < 40:
            raise RuntimeError("CONTENT_EXTRACTION_FAILED: target page has no usable text.")

        return {"records": [record]}

    @staticmethod
    def _parse_html(html: str, final_url: str, query: str | None) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "template", "svg"]):
            tag.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else None

        description = None
        meta_description = soup.find(
            "meta",
            attrs={
                "name": lambda value: isinstance(value, str)
                and value.lower() == "description"
            },
        )
        if meta_description:
            description = meta_description.get("content")

        # Prefer semantic content containers, but fall back to the complete
        # body. Some sites (including standards/documentation sites) put useful
        # text directly in sections/divs rather than <main>/<article>.
        root = soup.find("article") or soup.find("main") or soup.body or soup
        for tag in root.find_all(["nav", "header", "footer", "aside"]):
            tag.decompose()

        headings = [
            heading.get_text(" ", strip=True)
            for heading in root.find_all(["h1", "h2", "h3"])
            if heading.get_text(" ", strip=True)
        ]

        external_links: list[str] = []
        seen_links: set[str] = set()
        for anchor in root.find_all("a", href=True):
            href = urljoin(final_url, str(anchor.get("href")))
            if not href.startswith(("http://", "https://")) or href in seen_links:
                continue
            seen_links.add(href)
            external_links.append(href)
            if len(external_links) >= 100:
                break

        text = root.get_text(" ", strip=True)
        text = " ".join(text.split())

        # If semantic-container extraction is suspiciously small, use body text
        # before declaring the page unusable.
        if len(text) < 200 and soup.body is not None:
            body_text = " ".join(soup.body.get_text(" ", strip=True).split())
            if len(body_text) > len(text):
                text = body_text

        content = text[:20_000]

        record: dict[str, Any] = {
            "url": final_url,
            "title": title or final_url,
            "description": description or "",
            "content": content,
            "headings": headings[:100],
            "external_links": external_links,
        }
        if query:
            record["query"] = query
        return record
