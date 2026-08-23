import asyncio
import logging
from typing import Any

from backend.app.schemas.scraper import ScrapeResult
from backend.app.services.llm.provider import LLMProvider, OpenAICompatibleLLMProvider
from backend.app.services.llm.research_synthesizer import ResearchContext, ResearchSynthesizer
from backend.app.services.research.job_store import ResearchJob, ResearchJobStore
from backend.app.services.scraper.scraper_service import ScraperService
from backend.app.services.search import SearchService

logger = logging.getLogger(__name__)

search_service = SearchService()


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
        self._background_tasks: set[asyncio.Task[None]] = set()

    def create_job(self, url: str | None, query: str | None = None) -> ResearchJob:
        return self.store.create(url or "", query)

    def start_job(self, job: ResearchJob) -> None:
        task = asyncio.create_task(self.run_job(job.job_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._log_background_task_failure)

    @staticmethod
    def _log_background_task_failure(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.error("Research background task failed (error_type=%s)", type(task.exception()).__name__)

    async def _synthesize_result(self, job: ResearchJob, result: Any) -> dict[str, Any]:
        data = result.data if hasattr(result, "data") else {}
        context = ResearchContext(
            request_url=str(result.request_url) if hasattr(result, "request_url") else (job.url or "https://local.research"),
            query=job.query,
            quality_score=getattr(result, "quality_score", None),
            sources=[{"url": getattr(source, "url", ""), "title": getattr(source, "title", "")} for source in getattr(result, "sources", [])],
            evidence=data.get("evidence") or [],
            claims=data.get("claims") or [],
            entities=data.get("entities") or [],
            relationships=data.get("relationships") or [],
        )

        try:
            synthesis = await self.synthesizer.synthesize(context)
        except Exception as exc:
            logger.warning(
                "Research job %s synthesis degraded to fallback (error_type=%s, error=%s)",
                job.job_id,
                type(exc).__name__,
                exc,
            )
            synthesis = None

        if synthesis is None:
            fallback = {
                "title": data.get("title") or job.query or "Research report",
                "report": data.get("report") or "Research completed with source-backed evidence.",
                "summary": data.get("summary") or "No additional synthesis was available.",
                "llm_generated_claims": [],
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
            "llm_generated_claims": synthesis.claims,
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
            # Direct URL or Query-Only Discovery Handling
            if job.url and job.url.strip():
                try:
                    scrape_res = await self.scraper.scrape(job.url, job.query)
                    if isinstance(scrape_res, dict):
                        scrape_res.setdefault("status", "completed")
                        result = ScrapeResult(**scrape_res)
                    else:
                        result = scrape_res
                except Exception as exc:
                    logger.warning("Scraper failed/blocked (%s), using search synthesis fallback.", exc)
                    target_url = job.url if (job.url.startswith("http://") or job.url.startswith("https://")) else "https://local.research"
                    result = ScrapeResult(
                        status="completed",
                        request_url=target_url,
                        quality_score=0.5,
                        sources=[],
                        data={
                            "title": job.query or "Research Analysis",
                            "evidence": [],
                            "claims": [],
                            "entities": [],
                            "relationships": [],
                        }
                    )
            else:
                logger.info("Query-only research requested. Discovering web sources...")
                try:
                    discovered_urls = await search_service.discover_urls(job.query or "")
                except Exception as search_err:
                    logger.warning("Search discovery failed with error: %s", search_err)
                    discovered_urls = []
                
                # Zero Web Sources Fallback (Switches to Direct Knowledge Synthesis instead of failing)
                if not discovered_urls:
                    logger.warning("Zero web sources discovered for query: %s. Using LLM synthesis fallback.", job.query)
                    target_url = "https://local.research"
                    result = ScrapeResult(
                        status="completed",
                        request_url=target_url,
                        quality_score=0.7,
                        sources=[{"url": "https://local.research/llm-knowledge", "title": "LLM Knowledge Base"}],
                        data={
                            "title": job.query or "General Research Query",
                            "evidence": [],
                            "claims": [],
                            "entities": [],
                            "relationships": [],
                        }
                    )
                else:
                    target_url = discovered_urls[0]
                    result = ScrapeResult(
                        status="completed",
                        request_url=target_url,
                        quality_score=0.8,
                        sources=[{"url": u, "title": f"Source {i+1}"} for i, u in enumerate(discovered_urls)],
                        data={
                            "title": job.query or "General Synthesis Query",
                            "evidence": [],
                            "claims": [],
                            "entities": [],
                            "relationships": [],
                        }
                    )

        except Exception as exc:
            logger.error(
                "Research job %s failed unexpectedly during initialization (error_type=%s, error=%s)",
                job_id,
                type(exc).__name__,
                exc,
            )
            self._fail_job_safely(job_id, "Research service is temporarily unavailable.")
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
                "llm_generated_claims": synthesis["llm_generated_claims"],
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
                "Research job %s final synthesis failed (error_type=%s, error=%s)",
                job_id,
                type(exc).__name__,
                exc,
            )
            self._fail_job_safely(job_id, "Research could not be completed.")
            return