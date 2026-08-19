from backend.app.services.scraper.intelligence_service import IntelligenceService


def test_claims_are_generated_from_evidence_and_verified():
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
            "verification_status": "verified",
        }
    ]
    assert data["claims"][0]["statement"] == data["evidence"][0]["snippet"]


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
