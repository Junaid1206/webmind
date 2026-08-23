# webmind
WebMind - evidence-backed public web intelligence

## Generic public-web fetching

WebMind now uses a generic HTML fetcher for `/api/v1/scrape` and `/api/v1/research` instead of the site-specific Bright Data collector. The fetcher extracts the page title, description, headings, links, and readable body text from arbitrary public HTML pages.

Install/update dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Run:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Test with any public HTML URL, for example:

```json
{
  "url": "https://docs.python.org/3/tutorial/",
  "query": "what is this page about"
}
```

If a page returns no usable text, the job is now failed with `CONTENT_EXTRACTION_FAILED` instead of being incorrectly marked `completed` with empty evidence.

### Important limitation

This first generic fetcher handles normal server-rendered HTML. JavaScript-heavy pages that render their content only after browser execution may still require a browser renderer such as Playwright. Anti-bot, login-only, paywalled, or otherwise restricted pages cannot be guaranteed to be fetchable.


## Final Windows setup

1. Create the virtual environment: `py -m venv .venv`
2. Install dependencies: `.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
3. Copy `.env.example` to `.env` and add `BRIGHTDATA_API_KEY` (optional fallback) and `LLM_API_KEY`.
4. Keep `WEBMIND_API_KEY` empty for the bundled dashboard; this avoids the 401 caused by accidentally using the LLM key as app authentication.
5. Start from the project root: `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`
6. Open `http://127.0.0.1:8000`.

The LLM layer uses the OpenAI-compatible chat completions API, defaults to `gpt-4o-mini`, retries transient failures, validates structured JSON synthesis, and falls back to source-backed output if synthesis is unavailable.
