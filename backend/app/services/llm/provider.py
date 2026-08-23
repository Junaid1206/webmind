import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str


class LLMProvider:
    """Base Provider boundary for synthesis of evidence-backed research."""

    async def generate(self, context: dict[str, Any]) -> LLMResponse:
        raise NotImplementedError


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 45.0,
        max_retries: int = 3,
        client: Any = None,
    ) -> None:
        # Priority to clean API Key without placeholders
        raw_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or ""
        ).strip()

        # Sanitize placeholder values if accidentally passed
        if "...aapki_real_key" in raw_key or "your_actual_key" in raw_key:
            raw_key = ""

        self.api_key = raw_key
        self.model = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

        if client:
            self.client = client
        else:
            self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    async def generate(self, context: dict[str, Any]) -> LLMResponse:
        if not self.api_key or not self.client:
            raise RuntimeError("GEMINI_API_KEY is missing or invalid in environment.")

        prompt = self._build_prompt(context)

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        )

        content = response.text
        if not content:
            raise RuntimeError("Empty response from Gemini LLM.")

        return LLMResponse(
            content=content.strip(),
            model=self.model,
            provider="google-genai-native"
        )

    @staticmethod
    def _normalize_json(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, BaseModel):
            return OpenAICompatibleLLMProvider._normalize_json(value.model_dump(mode="json"))
        if isinstance(value, dict):
            return {str(key): OpenAICompatibleLLMProvider._normalize_json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [OpenAICompatibleLLMProvider._normalize_json(item) for item in value]
        return str(value)

    @classmethod
    def _build_prompt(cls, context: dict[str, Any]) -> str:
        normalized_context = cls._normalize_json(context)
        query = normalized_context.get("query") or "general research"
        source_info = normalized_context.get("sources") or []
        evidence = normalized_context.get("evidence") or []
        claims = normalized_context.get("claims") or []

        normalized = json.dumps(
            {
                "query": query,
                "sources": source_info,
                "evidence": evidence,
                "claims": claims,
            },
            indent=2,
            ensure_ascii=True,
        )
        return (
            "You are an expert AI research analyst.\n"
            f"Research Question: {query}\n\n"
            f"Context Data:\n{normalized}\n\n"
            "Instructions:\n"
            "1. Synthesize a detailed report answering the Research Question.\n"
            "2. If Context Data is empty or lacks sources, use your general LLM world knowledge to provide an insightful, technical, and accurate research report.\n"
            "3. Return ONLY a valid JSON object with these exact keys:\n"
            "- title: string\n"
            "- report: 2-4 comprehensive paragraphs\n"
            "- summary: 1-2 sentence executive summary\n"
            "- key_findings: array of strings (minimum 3-5 findings)\n"
            "- limitations: array of strings\n"
            "- confidence: float between 0.7 and 1.0\n"
            "- evidence_refs: array of source URLs or references\n"
            "- claims: array of strings\n"
        )