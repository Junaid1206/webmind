"""
Standalone Gemini LLM connectivity check.

Run this directly (no server needed):

    python check_llm.py

It prints the active Gemini-compatible LLM config (masked)
and the exact error if the connection fails.
"""

import asyncio
import sys

from backend.app.core.config import settings
from backend.app.services.llm.provider import OpenAICompatibleLLMProvider


def mask(value: str | None) -> str:
    """Mask API keys while keeping enough information for debugging."""
    if not value:
        return "(not set)"

    if len(value) <= 8:
        return "*" * len(value)

    return value[:6] + "..." + value[-4:]


async def main() -> None:
    print("=" * 60)
    print("WebMind Gemini LLM config check")
    print("=" * 60)

    print(f"LLM_API_KEY : {mask(settings.llm_api_key)}")
    print(f"LLM_MODEL   : {settings.llm_model or '(not set)'}")
    print(
        f"LLM_BASE_URL: "
        f"{settings.llm_base_url or '(not set)'}"
    )
    print(
        f"APP API_KEY : "
        f"{mask(settings.webmind_api_key)} "
        f"(WebMind's own auth, unrelated to Gemini)"
    )

    print("-" * 60)

    # ---------------------------------------------------------
    # Validate configuration
    # ---------------------------------------------------------

    if not settings.llm_api_key:
        print("FAIL: LLM_API_KEY is not configured.")
        print()
        print("For Gemini, add this to your .env:")
        print()
        print("LLM_API_KEY=your_gemini_api_key")
        print(
            "LLM_BASE_URL="
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        print("LLM_MODEL=gemini-2.5-flash")
        sys.exit(1)

    if not settings.llm_base_url:
        print("WARNING: LLM_BASE_URL is not configured.")
        print()
        print("Expected Gemini OpenAI-compatible endpoint:")
        print(
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        print()

    if not settings.llm_model:
        print("WARNING: LLM_MODEL is not configured.")
        print()
        print("Expected model:")
        print("gemini-2.5-flash")
        print()

    # ---------------------------------------------------------
    # Detect obvious OpenAI configuration mistakes
    # ---------------------------------------------------------

    base_url = (settings.llm_base_url or "").lower()
    model = (settings.llm_model or "").lower()

    if "api.openai.com" in base_url:
        print("WARNING: Your LLM_BASE_URL still points to OpenAI.")
        print()
        print("You switched to Gemini, so use:")
        print(
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        print()

    if model.startswith("gpt-"):
        print("WARNING: Your LLM_MODEL still looks like an OpenAI model:")
        print(f"  {settings.llm_model}")
        print()
        print("For Gemini use something like:")
        print("  gemini-2.5-flash")
        print()

    # ---------------------------------------------------------
    # Show active provider
    # ---------------------------------------------------------

    print("Provider configuration:")
    print("  Provider : Google Gemini")
    print("  API mode : OpenAI-compatible")
    print(f"  Model    : {settings.llm_model}")
    print(f"  Base URL : {settings.llm_base_url}")
    print()

    # ---------------------------------------------------------
    # Send tiny test request
    # ---------------------------------------------------------

    provider = OpenAICompatibleLLMProvider()

    print("Sending a tiny test request to Gemini...")
    print("-" * 60)

    try:
        response = await provider.generate(
            {
                "request_url": "https://example.com",
                "query": "Say exactly: Gemini connection successful.",
                "sources": [],
                "evidence": [
                    {
                        "evidence_index": 0,
                        "source_url": "https://example.com",
                        "snippet": "Test snippet for Gemini connectivity.",
                    }
                ],
                "claims": [],
                "entities": [],
                "relationships": [],
            }
        )

        print("-" * 60)
        print("SUCCESS! Gemini responded.")
        print()
        print(f"Model: {response.model}")
        print()
        print("Content:")
        print(response.content[:500])
        print()
        print("=" * 60)

    except Exception as exc:
        print("-" * 60)
        print("FAILED. Gemini request failed.")
        print()
        print(f"Error type   : {type(exc).__name__}")
        print(f"Error message: {exc}")
        print()
        print("=" * 60)
        print("Gemini troubleshooting:")
        print()
        print("1. Check that LLM_API_KEY is a valid Google Gemini API key.")
        print()
        print("2. Check that LLM_BASE_URL is exactly:")
        print(
            "   https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        print()
        print("3. Check that LLM_MODEL is supported, for example:")
        print("   gemini-2.5-flash")
        print()
        print("4. Make sure the Gemini API is enabled for your Google project.")
        print()
        print("5. Make sure your API key has permission to use Gemini.")
        print()
        print("6. Do NOT use your WebMind API_KEY as LLM_API_KEY.")
        print()
        print("7. Do NOT use an OpenAI sk-... key for Gemini.")
        print()
        print("=" * 60)

        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())