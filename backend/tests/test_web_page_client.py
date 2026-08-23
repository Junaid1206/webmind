import httpx
import pytest

from backend.app.services.scraper.web_page_client import WebPageClient


@pytest.mark.asyncio
async def test_generic_html_page_is_parsed_into_research_record():
    html = """
    <html>
      <head>
        <title>Example Docs</title>
        <meta name="description" content="A documentation page.">
      </head>
      <body>
        <nav>Ignore navigation</nav>
        <main>
          <h1>Example Docs</h1>
          <h2>Introduction</h2>
          <p>This is enough useful content to verify the generic webpage parser works correctly.</p>
          <a href="/about">About</a>
        </main>
        <script>ignore me</script>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html,
            request=request,
        )

    client = WebPageClient(transport=httpx.MockTransport(handler))
    result = await client.scrape("https://example.test/docs", "what is this page about")
    record = result["records"][0]

    assert record["title"] == "Example Docs"
    assert record["description"] == "A documentation page."
    assert "This is enough useful content" in record["content"]
    assert record["headings"] == ["Example Docs", "Introduction"]
    assert record["external_links"] == ["https://example.test/about"]
    assert record["query"] == "what is this page about"


@pytest.mark.asyncio
async def test_generic_html_page_rejects_empty_text():
    html = "<html><head><title>Empty</title></head><body><script>x</script></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=html,
            request=request,
        )

    client = WebPageClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="CONTENT_EXTRACTION_FAILED"):
        await client.scrape("https://example.test/empty")
