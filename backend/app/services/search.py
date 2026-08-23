import logging
from typing import List
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class SearchService:
    async def discover_urls(self, query: str, max_results: int = 5) -> List[str]:
        """Discovers web URLs for query-only research requests."""
        try:
            async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
                res = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    timeout=10.0
                )
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    links = []
                    for a in soup.find_all("a", class_="result__url"):
                        href = a.get("href")
                        if href and href.startswith("http"):
                            links.append(href.strip())
                        if len(links) >= max_results:
                            break
                    if links:
                        return links
        except Exception as exc:
            logger.error("Search discovery failed: %s", exc)
        return []