from backend.app.schemas.scraper import ScrapeResult
from backend.app.services.research.job_store import SqliteResearchJobStore


def test_sqlite_store_recreation_restores_job_result_and_history(tmp_path):
    database_path = tmp_path / "research-test.db"
    first = SqliteResearchJobStore(path=str(database_path))
    job = first.create("https://example.com", "persisted query")
    first.begin_job(job.job_id)
    first.store_result(
        job.job_id,
        ScrapeResult(
            request_url="https://example.com",
            status="completed",
            data={"evidence": [{"source_url": "https://example.com", "snippet": "saved"}]},
        ),
    )
    first.store_llm_result(job.job_id, {
        "report": "Saved report",
        "summary": "Saved summary",
        "key_findings": ["Saved finding"],
        "limitations": [],
        "evidence_refs": ["https://example.com"],
        "confidence": 0.9,
    })

    second = SqliteResearchJobStore(path=str(database_path))
    restored = second.get(job.job_id)
    history = second.list(limit=10)
    assert restored is not None
    assert restored.status == "completed"
    assert restored.result is not None
    assert restored.result.data["evidence"][0]["snippet"] == "saved"
    assert restored.report == "Saved report"
    assert restored.summary == "Saved summary"
    assert restored.confidence == 0.9
    assert [item.job_id for item in history] == [job.job_id]


def test_sqlite_store_creates_nested_database_directory(tmp_path):
    database_path = tmp_path / "nested" / "research.db"
    store = SqliteResearchJobStore(path=str(database_path))

    job = store.create("https://example.com")

    assert database_path.exists()
    assert store.get(job.job_id) is not None