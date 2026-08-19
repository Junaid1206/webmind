"""Evidence-preserving normalization for public-web scraper output."""

from typing import Any
from urllib.parse import urlparse


class IntelligenceService:
    """Build a compact, source-backed research payload from scraper records."""

    def enrich(
        self, raw: dict[str, Any], request_url: str
    ) -> tuple[dict[str, Any], list[dict[str, str | None]], float]:
        has_record_collection = isinstance(raw.get("records"), list)
        records = raw.get("records") if has_record_collection else [raw]
        normalized_records = [record for record in records if isinstance(record, dict)]
        sources = self._sources(normalized_records, request_url)
        evidence = self._evidence(normalized_records, request_url)
        claims = self._claims(evidence)
        entities = self._entities(normalized_records)
        relationships = self._relationships(normalized_records, request_url)
        data = dict(raw)
        data.update(
            {
                "records": normalized_records,
                "evidence": evidence,
                "claims": claims,
                "entities": entities,
                "relationships": relationships,
            }
        )
        quality_score = self._quality_score(normalized_records, evidence, sources)
        return data, sources, quality_score if has_record_collection else 0.0

    @staticmethod
    def _sources(
        records: list[dict[str, Any]], request_url: str
    ) -> list[dict[str, str | None]]:
        sources: list[dict[str, str | None]] = []
        seen: set[str] = set()
        for record in records:
            url = record.get("url") or record.get("source_url") or request_url
            if (
                not isinstance(url, str)
                or not url.startswith(("http://", "https://"))
                or url in seen
            ):
                continue
            seen.add(url)
            title = record.get("title")
            sources.append({"url": url, "title": title if isinstance(title, str) else None})
        return sources or [{"url": request_url, "title": None}]

    @staticmethod
    def _evidence(
        records: list[dict[str, Any]], request_url: str
    ) -> list[dict[str, str]]:
        evidence: list[dict[str, str]] = []
        for record in records:
            text = next(
                (
                    record.get(key)
                    for key in ("content", "description", "text")
                    if isinstance(record.get(key), str)
                ),
                None,
            )
            if text:
                evidence.append(
                    {
                        "source_url": str(
                            record.get("url") or record.get("source_url") or request_url
                        ),
                        "snippet": text[:500],
                    }
                )
        return evidence

    @classmethod
    def _claims(cls, evidence: list[dict[str, str]]) -> list[dict[str, str | int]]:
        """Create claims only from text already retained as source evidence."""
        claims: list[dict[str, str | int]] = []
        for evidence_index, item in enumerate(evidence):
            claim = {
                "id": f"claim-{evidence_index + 1}",
                "statement": item["snippet"],
                "source_url": item["source_url"],
                "evidence_index": evidence_index,
            }
            claim["verification_status"] = cls._verification_status(claim, item)
            claims.append(claim)
        return claims

    @staticmethod
    def _verification_status(
        claim: dict[str, str | int], evidence: dict[str, str] | None
    ) -> str:
        if (
            evidence
            and claim.get("source_url") == evidence.get("source_url")
            and claim.get("statement") == evidence.get("snippet")
        ):
            return "verified"
        return "unverified"

    @staticmethod
    def _entities(records: list[dict[str, Any]]) -> list[dict[str, str]]:
        entities: list[dict[str, str]] = []
        for record in records:
            title = record.get("title")
            if isinstance(title, str) and title.strip():
                entities.append({"name": title.strip(), "type": "document"})
        return entities

    @staticmethod
    def _relationships(
        records: list[dict[str, Any]], request_url: str
    ) -> list[dict[str, str]]:
        """Represent only the explicit provenance of title-derived entities."""
        relationships: list[dict[str, str]] = []
        for record in records:
            title = record.get("title")
            source_url = record.get("url") or record.get("source_url") or request_url
            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(source_url, str)
                or not source_url.startswith(("http://", "https://"))
            ):
                continue
            relationships.append(
                {
                    "subject": title.strip(),
                    "predicate": "sourced_from",
                    "object": source_url,
                }
            )
        return relationships

    @staticmethod
    def _quality_score(
        records: list[dict[str, Any]],
        evidence: list[dict[str, str]],
        sources: list[dict[str, str | None]],
    ) -> float:
        if not records:
            return 0.0
        score = 0.4 + (0.3 if evidence else 0.0) + (0.2 if sources else 0.0)
        domains = {urlparse(str(source["url"])).netloc for source in sources}
        return round(min(1.0, score + (0.1 if len(domains) > 1 else 0.0)), 2)
