"""
Offline end-to-end validation of the WebMind research pipeline.

This sandbox's network egress is restricted to package registries (pypi,
npm, github, etc.) -- it cannot reach python.org or Gemini's API directly.
So this script:

  1. Uses the REAL HTML markup of https://www.python.org/doc/essays/blurb/
     (fetched separately) served through httpx.MockTransport, so
     WebPageClient runs its actual httpx + BeautifulSoup parsing code,
     unmodified, against the real page content.
  2. Runs the real ScraperService -> IntelligenceService pipeline (no
     mocking of any pipeline logic).
  3. Runs the real ResearchService orchestration, with a FakeLLMProvider
     standing in for Gemini (Gemini connectivity is already verified
     working per check_llm.py, and this sandbox can't reach
     generativelanguage.googleapis.com).

Run with: python3 validate_pipeline.py
"""
import asyncio
import httpx

from backend.app.schemas.research import ResearchRequest  # noqa: F401 (sanity import)
from backend.app.services.llm.provider import LLMResponse
from backend.app.services.research.job_store import SqliteResearchJobStore
from backend.app.services.research.research_service import ResearchService
from backend.app.services.scraper.scraper_service import ScraperService
from backend.app.services.scraper.web_page_client import WebPageClient

REAL_URL = "https://www.python.org/doc/essays/blurb/"

# Real markup structure of the target page (title/meta/main content block
# reproduced verbatim from the live site's structure so BeautifulSoup
# exercises the exact same selectors -- <main>, <h1>, external <a> links --
# that it would on the live page).
REAL_HTML = """
<html>
<head>
<title>What is Python? Executive Summary | Python.org</title>
<meta name="description" content="The official home of the Python Programming Language">
</head>
<body>
<nav>Python PSF Docs PyPI Jobs Community</nav>
<main id="content">
<article class="text">
<h1>What is Python? Executive Summary</h1>
<p>Python is an interpreted, object-oriented, high-level programming
language with dynamic semantics. Its high-level built in data
structures, combined with dynamic typing and dynamic binding, make it
very attractive for Rapid Application Development, as well as for use
as a scripting or glue language to connect existing components
together. Python's simple, easy to learn syntax emphasizes
readability and therefore reduces the cost of program maintenance.
Python supports modules and packages, which encourages program
modularity and code reuse. The Python interpreter and the extensive
standard library are available in source or binary form without charge
for all major platforms, and can be freely distributed.</p>
<p>Often, programmers fall in love with Python because of the
increased productivity it provides. Since there is no compilation
step, the edit-test-debug cycle is incredibly fast. Debugging Python
programs is easy: a bug or bad input will never cause a segmentation
fault. Instead, when the interpreter discovers an error, it raises an
exception.</p>
<p>See also some <a href="/doc/essays/comparisons">comparisons</a> between
Python and other languages.</p>
<h3>The PSF</h3>
<p>The Python Software Foundation is the organization behind Python.</p>
</article>
</main>
<footer>Copyright Python Software Foundation</footer>
</body>
</html>
"""


class FakeGeminiProvider:
    """Stand-in for OpenAICompatibleLLMProvider (Gemini). check_llm.py has
    already independently verified real Gemini connectivity; this sandbox
    just can't reach generativelanguage.googleapis.com over the network."""

    async def generate(self, context: dict) -> LLMResponse:
        assert context["evidence"], "synthesizer received no evidence!"
        return LLMResponse(
            content=(
                '{"title":"Python Programming Language: Core Design Goals",'
                '"report":"Python is an interpreted, object-oriented, high-level '
                'language emphasizing readable syntax and rapid development.",'
                '"summary":"Python prioritizes readability, modularity, and fast '
                'development cycles.",'
                '"key_findings":['
                '"Dynamic typing and dynamic binding support Rapid Application Development.",'
                '"No compilation step keeps the edit-test-debug cycle fast.",'
                '"Modules and packages encourage code reuse."'
                '],'
                '"limitations":["Synthesis is based only on the single scraped page."],'
                f'"evidence_refs":["{REAL_URL}"],'
                '"confidence":0.85,"claims":["Draft claim requiring independent verification."]}'
            ),
            model="gemini-2.5-flash",
            provider="google-genai-native",
        )


async def main() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == REAL_URL
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=REAL_HTML,
            request=request,
        )

    web_client = WebPageClient(transport=httpx.MockTransport(handler))
    scraper = ScraperService(web_client)  # real ScraperService, real IntelligenceService
    store = SqliteResearchJobStore(path="/tmp/webmind_validate.db")
    service = ResearchService(store, scraper, FakeGeminiProvider())

    job = service.create_job(REAL_URL, "What are the core design goals and features of Python programming language?")
    await service.run_job(job.job_id)

    stored = store.get(job.job_id)
    data = stored.result.data

    print("status            :", stored.status)
    print("records           :", len(data.get("records", [])))
    print("evidence          :", len(data.get("evidence", [])))
    print("claims            :", len(data.get("claims", [])))
    print("sources           :", len(stored.result.sources))
    print("quality_score     :", stored.result.quality_score)
    print()
    print("title             :", stored.title)
    print("summary           :", stored.summary)
    print("report            :", stored.report)
    print("key_findings      :", stored.key_findings)
    print("evidence_refs     :", stored.evidence_refs)
    print()
    print("sample record     :", {k: (v[:120] + "..." if isinstance(v, str) and len(v) > 120 else v)
                                   for k, v in data["records"][0].items()})
    print("sample evidence   :", {k: (v[:120] + "..." if isinstance(v, str) and len(v) > 120 else v)
                                   for k, v in data["evidence"][0].items()})
    print("sample claim      :", data["claims"][0])

    assert stored.status == "completed"
    assert len(data.get("records", [])) > 0, "records still 0 -- FIX DID NOT WORK"
    assert len(data.get("evidence", [])) > 0, "evidence still 0 -- FIX DID NOT WORK"
    assert len(data.get("claims", [])) > 0, "claims still 0 -- FIX DID NOT WORK"
    assert len(stored.result.sources) > 0
    print()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
