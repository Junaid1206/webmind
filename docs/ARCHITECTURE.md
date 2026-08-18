# WebMind Architecture

## 1. Mission

WebMind is an intelligent public-web research and data extraction platform.

It combines custom web scraping, structured extraction, evidence tracking,
LLM-assisted analysis, validation, and change detection.

## 2. Core Principle

Scrape → Normalize → Validate → Enrich → Verify → Store → Explain

The system must never treat an LLM-generated claim as verified without
supporting source evidence.

## 3. Hackathon Requirement

WebMind MUST use a custom scraper created and executed through
Bright Data Scraper Studio.

Existing scrapers from the Bright Data Scrapers Library alone are not sufficient.

## 4. Data Scope

Only publicly available web data is allowed.

The system must NOT intentionally collect:

- private data
- login-protected data
- paywalled data
- personal/restricted information

## 5. High-Level Pipeline

User Query
    ↓
Research Planner
    ↓
Target Discovery
    ↓
Bright Data Custom Scraper
    ↓
Raw Web Data
    ↓
Normalizer
    ↓
Schema Validator
    ↓
Evidence Extractor
    ↓
LLM Analysis
    ↓
Verification / Confidence
    ↓
Knowledge Store
    ↓
Research Result

## 6. Main Components

### Frontend
- Research input
- Job status
- Sources
- Extracted entities
- Evidence
- Relationships
- Confidence
- Final research report

### Backend
- API server
- Research orchestration
- Scraper orchestration
- Data normalization
- Validation
- Evidence processing
- LLM analysis
- Job management

### Scraper Layer
- Bright Data Scraper Studio custom scraper
- Scraper execution
- Structured output
- Error handling
- Retry handling

### Intelligence Layer
- Entity extraction
- Relationship extraction
- Classification
- Deduplication
- Confidence scoring
- Contradiction detection
- Change detection

### Storage
- Research jobs
- Sources
- Documents
- Entities
- Relationships
- Claims
- Evidence
- Scrape runs

## 7. Evidence Model

Every important extracted claim should retain:

- source URL
- page title
- extraction timestamp
- supporting text/snippet where available
- scraper run ID
- confidence score

## 8. Verification

LLM output is considered an interpretation, not ground truth.

Verification should compare generated claims against extracted source data.

## 9. MVP

The first working version should support:

1. User enters a research query.
2. System determines the target web pages.
3. Bright Data custom scraper collects public data.
4. Data is normalized into a fixed schema.
5. Entities and relationships are extracted.
6. Evidence is attached to claims.
7. Results are shown in a research dashboard.

## 10. Hackathon Priority

Reliability > complexity.

We will avoid unnecessary microservices, distributed infrastructure,
and complicated ML systems unless they directly improve the judging criteria.

## 11. Five-Day Build Strategy

### Day 1
Architecture + repository + scraper design.

### Day 2
Backend skeleton + scraper integration.

### Day 3
Intelligence pipeline + evidence/verification.

### Day 4
Frontend + complete end-to-end flow.

### Day 5
Testing + debugging + UX + demo + submission preparation.