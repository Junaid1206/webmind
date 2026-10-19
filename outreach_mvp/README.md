# Cold Outreach Agent MVP

A lightweight FastAPI + SQLite lead CRM and personalized outreach drafting API, isolated inside WebMind so the existing app is not disrupted.

## MVP scope

- Add and list marketing-agency and startup leads
- Store public source URL and contact-basis notes
- Generate channel-specific drafts for email, X and Instagram
- Require explicit user approval before queueing a draft
- Maintain an opt-out/suppression list
- Record draft and queue events
- Keep live sending disabled by default

**This MVP does not send email or social DMs.** The dispatch endpoint fails closed until an official, authorized and policy-compliant channel adapter is implemented and tested. An environment flag alone cannot enable sending.

## Windows setup

From the WebMind repository root, run:

    py -m venv .venv-outreach
    .\\.venv-outreach\\Scripts\\Activate.ps1
    python -m pip install -r outreach_mvp\\requirements.txt
    Copy-Item outreach_mvp\\.env.example outreach_mvp\\.env
    $env:DATABASE_PATH = ".\\outreach_mvp\\outreach.db"
    uvicorn app:app --app-dir outreach_mvp --reload

Open http://127.0.0.1:8000/docs to use the API interactively. SQLite is created on first run.

## Quick test

Create a lead using POST /leads:

    {
      "name": "Alex",
      "company": "Example Agency",
      "role": "Founder",
      "website": "https://example.com",
      "email": "alex@example.com",
      "segment": "agency",
      "notes": "Public website says they serve local businesses",
      "source_url": "https://example.com",
      "contact_basis": "Public business contact; verify applicable rules before outreach"
    }

Create a draft using POST /leads/{lead_id}/drafts:

    {
      "channel": "email",
      "service": "AI review-response and lead research automation",
      "specific_observation": "I noticed your agency works with local service businesses"
    }

Use the actual lead ID returned by the API. Review the generated draft before approving it with POST /drafts/{draft_id}/queue and body {"approved_by_user": true}.

Add an opt-out using POST /suppression with body {"destination": "alex@example.com", "reason": "opt_out"}.

## Before any live channel integration

1. Confirm current platform API eligibility and rules for the exact use case.
2. Use OAuth and least-privilege scopes; never collect passwords or session cookies.
3. Add idempotency, rate limits, delivery logs and safe retry behavior.
4. Check suppression and recipient eligibility immediately before sending.
5. Stop follow-ups on replies, opt-outs, bounces or complaints.
6. Do not scrape login-only/restricted pages or bypass platform limits.
7. Follow applicable privacy, email and direct-marketing requirements for the recipient's jurisdiction.

## Current limitations

- Lead discovery is manual/API-input based; no scraper is included.
- Drafts use deterministic templates; no LLM key is required.
- Reply sync, scheduler, Gmail OAuth sender, X/Instagram adapters and UI are future milestones.
- Do not use real personal contact data in test runs.
