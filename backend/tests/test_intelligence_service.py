from backend.app.services.scraper.intelligence_service import IntelligenceService


def test_single_source_claim_is_unverified():
    data, _, _ = IntelligenceService().enrich(
        {
            "records": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "description": "A supported scraped fact.",
                }
            ]
        },
        "https://example.com",
    )

    assert data["claims"] == [
        {
            "id": "claim-1",
            "statement": "A supported scraped fact.",
            "source_url": "https://example.com",
            "evidence_index": 0,
            "verification_status": "unverified",
        }
    ]
    assert data["claims"][0]["statement"] == data["evidence"][0]["snippet"]


def test_claim_is_verified_when_distinct_sources_corroborate_it():
    data, _, _ = IntelligenceService().enrich(
        {"records": [
            {"url": "https://one.example", "content": "A shared supported fact."},
            {"url": "https://two.example", "content": "A shared supported fact."},
        ]},
        "https://one.example",
    )
    assert [claim["verification_status"] for claim in data["claims"]] == ["verified", "verified"]


def test_claim_is_unverified_when_its_evidence_does_not_match():
    status = IntelligenceService._verification_status(
        {
            "statement": "Unsupported claim",
            "source_url": "https://example.com",
            "evidence_index": 0,
        },
        {"snippet": "Different supporting text", "source_url": "https://example.com"},
    )

    assert status == "unverified"


def test_empty_or_malformed_records_produce_no_claims_or_evidence():
    service = IntelligenceService()

    empty_data, _, empty_score = service.enrich({"records": []}, "https://example.com")
    malformed_data, _, malformed_score = service.enrich(
        {"records": [None, "not-a-record", 1]}, "https://example.com"
    )

    assert empty_data["claims"] == empty_data["evidence"] == []
    assert malformed_data["claims"] == malformed_data["evidence"] == []
    assert empty_score == malformed_score == 0.0


def test_generic_page_record_produces_evidence():
    data, sources, score = IntelligenceService().enrich(
        {
            "records": [{
                "url": "https://docs.python.org/3/tutorial/",
                "title": "Python Tutorial",
                "description": "An informal introduction to Python.",
                "content": "This tutorial introduces the basic concepts and features of Python.",
                "headings": ["Whetting Your Appetite"],
                "external_links": [],
            }]
        },
        "https://docs.python.org/3/tutorial/",
    )
    assert data["evidence"]
    assert sources[0]["title"] == "Python Tutorial"
    assert score == 0.9
