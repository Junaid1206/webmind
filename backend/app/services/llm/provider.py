import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from backend.app.core.config import settings


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str


class LLMProvider:
    """Provider boundary for synthesis of evidence-backed research."""

    async def generate(self, context: dict[str, Any]) -> LLMResponse:
        raise NotImplementedError


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model or "gpt-4o-mini"
        self.base_url = (base_url or settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        self._client = client

    async def generate(self, context: dict[str, Any]) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You synthesize only the provided research context. "
                        "Use only source-backed information and never invent URLs or citations. "
                        "If evidence is missing or uncertain, clearly say so."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(context),
                },
            ],
            "temperature": 0.1,
        }

        try:
            async with self._client or httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 401:
                    raise RuntimeError("LLM provider authentication failed.")
                if response.status_code >= 400:
                    raise RuntimeError("LLM provider request failed.")
                try:
                    body = response.json()
                except ValueError as exc:
                    raise RuntimeError("LLM provider returned malformed JSON.") from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("LLM provider request timed out.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Unable to reach LLM provider.") from exc

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM provider returned no completion choices.")

        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM provider returned an empty response.")

        return LLMResponse(content=content.strip(), model=self.model, provider="openai-compatible")

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
        if hasattr(value, "unicode_string"):
            return str(value.unicode_string())
        return str(value)

    @classmethod
    def _build_prompt(cls, context: dict[str, Any]) -> str:
        normalized_context = cls._normalize_json(context)
        query = normalized_context.get("query") or "general research"
        source_info = normalized_context.get("sources") or []
        evidence = normalized_context.get("evidence") or []
        claims = normalized_context.get("claims") or []
        entities = normalized_context.get("entities") or []
        relationships = normalized_context.get("relationships") or []
        normalized = json.dumps(
            {
                "request_url": normalized_context.get("request_url"),
                "query": query,
                "quality_score": normalized_context.get("quality_score"),
                "sources": source_info,
                "evidence": evidence,
                "verified_claims": [claim for claim in claims if claim.get("verification_status") == "verified"],
                "entities": entities,
                "relationships": relationships,
            },
            indent=2,
            ensure_ascii=True,
        )
        return (
            "Use only the following evidence-grounded research context. "
            "Do not invent citations, urls, or claims.\n\n"
            f"{normalized}\n\n"
            "Return JSON with keys: report, summary, key_findings, limitations, confidence, evidence_refs, claims. "
            "Each item in evidence_refs should point to a provided source URL or evidence item, never made-up URLs. "
            "Only cite sources that are already present in the context."
        )
