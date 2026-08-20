import asyncio
import logging
from typing import Any

from backend.app.services.llm.provider import LLMProvider, OpenAICompatibleLLMProvider
from backend.app.services.llm.research_synthesizer import ResearchContext, ResearchSynthesizer
from backend.app.services.research.job_store import ResearchJob, ResearchJobStore
from backend.app.services.scraper.scraper_service import ScraperService

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(
        self,
        store: ResearchJobStore,
        scraper: ScraperService,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.store = store
        self.scraper = scraper
        self.llm_provider = llm_provider or OpenAICompatibleLLMProvider()
        self.synthesizer = ResearchSynthesizer(self.llm_provider)

    def create_job(self, url: str, query: str | None = None) -> ResearchJob:
        return self.store.create(url, query)

    def start_job(self, job: ResearchJob) -> None:
        asyncio.create_task(self.run_job(job.job_id))

    async def _synthesize_result(self, job: ResearchJob, result: Any) -> dict[str, Any]:
        data = result.data if hasattr(result, "data") else {}
        context = ResearchContext(
            request_url=str(result.request_url) if hasattr(result, "request_url") else job.url,
            query=job.query,
            quality_score=getattr(result, "quality_score", None),
            sources=[{"url": source.url, "title": source.title} for source in getattr(result, "sources", [])],
            evidence=data.get("evidence") or [],
            claims=data.get("claims") or [],
            entities=data.get("entities") or [],
            relationships=data.get("relationships") or [],
        )

        try:
            synthesis = await self.synthesizer.synthesize(context)
        except Exception as exc:
            logger.warning(
                "Research job %s synthesis degraded to fallback (error_type=%s)",
                job.job_id,
                type(exc).__name__,
            )
            synthesis = None

        if synthesis is None:
            fallback = {
                "title": data.get("title") or job.query or "Research report",
                "report": data.get("report") or "Research completed with source-backed evidence.",
                "summary": data.get("summary") or "No additional synthesis was available.",
                "key_findings": [
                    str(item).strip()
                    for item in (data.get("claims") or [])
                    if isinstance(item, dict) and item.get("statement")
                ],
                "limitations": ["LLM synthesis unavailable; the source-backed evidence remains the primary basis."],
                "evidence_refs": [
                    str(item.get("source_url"))
                    for item in (data.get("evidence") or [])
                    if isinstance(item, dict) and item.get("source_url")
                ],
                "confidence": float(data.get("quality_score") or 0.0),
            }
            return fallback

        evidence_urls = {
            str(item.get("source_url"))
            for item in (data.get("evidence") or [])
            if isinstance(item, dict) and item.get("source_url")
        }
        synthesis_payload = {
            "title": synthesis.title,
            "report": synthesis.report,
            "summary": synthesis.summary,
            "key_findings": synthesis.key_findings,
            "limitations": synthesis.limitations,
            "evidence_refs": [ref for ref in synthesis.evidence_refs if ref in evidence_urls],
            "confidence": synthesis.confidence,
        }
        if not synthesis_payload["evidence_refs"]:
            synthesis_payload["evidence_refs"] = [
                str(item.get("source_url"))
                for item in (data.get("evidence") or [])
                if isinstance(item, dict) and item.get("source_url")
            ]
        return synthesis_payload

    def _fail_job_safely(self, job_id: str, message: str) -> None:
        try:
            self.store.store_error(job_id, message)
        except Exception as exc:
            logger.error(
                "Research job %s could not be marked failed (error_type=%s)",
                job_id,
                type(exc).__name__,
            )

    async def run_job(self, job_id: str) -> None:
        job = self.store.begin_job(job_id)
        if job is None:
            return
        try:
            result = await self.scraper.scrape(job.url, job.query)
        except (RuntimeError, TimeoutError):
            self._fail_job_safely(job_id, "Research service is temporarily unavailable.")
            return
        except Exception as exc:
            logger.error(
                "Research job %s failed unexpectedly (error_type=%s)",
                job_id,
                type(exc).__name__,
            )
            self._fail_job_safely(job_id, "Research could not be completed.")
            return

        try:
            stored = self.store.store_pending_result(job_id, result)
            if stored is None:
                return
            synthesis = await self._synthesize_result(stored, result)
            data = result.data if hasattr(result, "data") else {}
            data["report"] = synthesis["report"]
            data["title"] = synthesis["title"]
            data["summary"] = synthesis["summary"]
            data["key_findings"] = synthesis["key_findings"]
            data["limitations"] = synthesis["limitations"]
            data["evidence_refs"] = synthesis["evidence_refs"]
            data["confidence"] = synthesis["confidence"]
            data["structured_summary"] = {
                "report": synthesis["report"],
                "summary": synthesis["summary"],
                "key_findings": synthesis["key_findings"],
                "limitations": synthesis["limitations"],
                "evidence_refs": synthesis["evidence_refs"],
                "confidence": synthesis["confidence"],
            }
            if hasattr(result, "model_dump"):
                try:
                    self.store.store_pending_result(job_id, result)
                except Exception as exc:
                    logger.error(
                        "Research job %s could not persist synthesis payload (error_type=%s)",
                        job_id,
                        type(exc).__name__,
                    )
            self.store.store_llm_result(job_id, {
                "title": synthesis["title"],
                "report": synthesis["report"],
                "summary": synthesis["summary"],
                "key_findings": synthesis["key_findings"],
                "limitations": synthesis["limitations"],
                "evidence_refs": synthesis["evidence_refs"],
                "confidence": synthesis["confidence"],
            })
            self.store.update_status(job_id, "completed")
        except Exception as exc:
            logger.error(
                "Research job %s final synthesis failed (error_type=%s)",
                job_id,
                type(exc).__name__,
            )
            self._fail_job_safely(job_id, "Research could not be completed.")
            return
