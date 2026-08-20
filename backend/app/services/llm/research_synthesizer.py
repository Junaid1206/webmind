import json
from dataclasses import dataclass, field
from typing import Any

from backend.app.services.llm.provider import LLMProvider, LLMResponse


@dataclass
class ResearchContext:
    request_url: str | None = None
    query: str | None = None
    quality_score: float | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_url": self.request_url,
            "query": self.query,
            "quality_score": self.quality_score,
            "sources": self.sources,
            "evidence": [
                {"evidence_index": index, **item}
                for index, item in enumerate(self.evidence)
            ],
            "claims": self.claims,
            "entities": self.entities,
            "relationships": self.relationships,
        }


@dataclass
class ResearchSynthesis:
    report: str
    summary: str
    title: str
    key_findings: list[str]
    confidence: float
    limitations: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)

    @classmethod
    def from_provider_output(cls, content: str) -> "ResearchSynthesis":
        text = content.strip()
        if not text:
            raise ValueError("LLM synthesis output is empty.")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM synthesis output is not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("LLM synthesis output is not a JSON object.")

        report = payload.get("report")
        summary = payload.get("summary")
        title = payload.get("title")
        findings = payload.get("key_findings")
        limitations = payload.get("limitations")
        evidence_refs = payload.get("evidence_refs")
        claims = payload.get("claims")
        confidence = payload.get("confidence")

        if not isinstance(report, str) or not report.strip():
            raise ValueError("LLM synthesis is missing a valid report.")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("LLM synthesis is missing a valid summary.")
        if not isinstance(title, str) or not title.strip():
            title = report
        if not isinstance(findings, list):
            findings = []
        if not isinstance(limitations, list):
            limitations = []
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        if not isinstance(claims, list):
            claims = []
        if not isinstance(confidence, (int, float)):
            confidence = 0.0

        return cls(
            report=report.strip(),
            summary=summary.strip(),
            title=title.strip(),
            key_findings=[str(item).strip() for item in findings if str(item).strip()],
            confidence=float(confidence),
            limitations=[str(item).strip() for item in limitations if str(item).strip()],
            evidence_refs=[str(item).strip() for item in evidence_refs if str(item).strip()],
            claims=[str(item).strip() for item in claims if str(item).strip()],
        )


class ResearchSynthesizer:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def synthesize(self, context: ResearchContext) -> ResearchSynthesis:
        response = await self.provider.generate(context.as_dict())
        return ResearchSynthesis.from_provider_output(response.content)
