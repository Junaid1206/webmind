from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()
DB_PATH = os.getenv("DATABASE_PATH", "./outreach.db")
AUTO_SEND_ENABLED = os.getenv("AUTO_SEND_ENABLED", "false").lower() == "true"
DAILY_SEND_LIMIT = max(1, int(os.getenv("DAILY_SEND_LIMIT", "10")))
SENDER_NAME = os.getenv("SENDER_NAME", "Your Name")
SENDER_SERVICE = os.getenv("SENDER_SERVICE", "AI automation and custom software")
SENDER_WEBSITE = os.getenv("SENDER_WEBSITE", "")

app = FastAPI(title="Cold Outreach Agent — MVP", version="0.1.0",
    description="Lightweight lead CRM and outreach drafting API. Live sending is disabled until an authorized, policy-compliant channel adapter is implemented.")

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, company TEXT NOT NULL,
          role TEXT DEFAULT '', website TEXT DEFAULT '', email TEXT DEFAULT '', x_handle TEXT DEFAULT '',
          instagram_handle TEXT DEFAULT '', segment TEXT NOT NULL DEFAULT 'agency', notes TEXT DEFAULT '',
          source_url TEXT DEFAULT '', contact_basis TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'new',
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
          channel TEXT NOT NULL, subject TEXT DEFAULT '', body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS suppression (
          id INTEGER PRIMARY KEY AUTOINCREMENT, destination TEXT NOT NULL UNIQUE,
          reason TEXT NOT NULL DEFAULT 'opt_out', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outreach_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
          draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL, channel TEXT NOT NULL,
          event TEXT NOT NULL, detail TEXT DEFAULT '', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_drafts_lead ON drafts(lead_id);
        """)
        conn.commit()

@app.on_event("startup")
def startup():
    init_db()

class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=180)
    role: str = Field(default="", max_length=120)
    website: str = Field(default="", max_length=500)
    email: str = Field(default="", max_length=254)
    x_handle: str = Field(default="", max_length=100)
    instagram_handle: str = Field(default="", max_length=100)
    segment: Literal["agency", "startup", "other"] = "agency"
    notes: str = Field(default="", max_length=2000)
    source_url: str = Field(default="", max_length=1000)
    contact_basis: str = Field(default="", max_length=500)

class DraftIn(BaseModel):
    channel: Literal["email", "x", "instagram"]
    service: str = Field(default=SENDER_SERVICE, min_length=2, max_length=300)
    sender_name: str = Field(default=SENDER_NAME, min_length=1, max_length=120)
    sender_website: str = Field(default=SENDER_WEBSITE, max_length=500)
    specific_observation: str = Field(default="", max_length=500)

class SuppressIn(BaseModel):
    destination: str = Field(min_length=3, max_length=300)
    reason: str = Field(default="opt_out", max_length=120)

class QueueIn(BaseModel):
    draft_id: int
    approved_by_user: bool = False

def row_dict(row):
    return dict(row) if row else None

def destination_for(row, channel: str) -> str:
    field = {"email": "email", "x": "x_handle", "instagram": "instagram_handle"}[channel]
    return (row[field] or "").strip().lower()

def is_suppressed(conn, destination: str) -> bool:
    if not destination:
        return False
    return conn.execute("SELECT 1 FROM suppression WHERE lower(destination)=lower(?) LIMIT 1", (destination,)).fetchone() is not None

def build_draft(lead, req: DraftIn):
    first_name = lead["name"].strip().split()[0]
    company = lead["company"].strip()
    observation = req.specific_observation.strip() or f"I came across {company} and wanted to learn how your team handles repetitive research and operational workflows"
    if req.channel == "email":
        subject = f"Idea for {company}'s workflow"
        body = (f"Hi {first_name},\n\n{observation.rstrip('.')}."
                f"\n\nI build {req.service}. If improving that workflow is a priority, "
                "I can share a small, relevant example and learn whether it would be useful for your team."
                f"\n\nWould a short conversation be relevant?\n\nBest,\n{req.sender_name}")
        if req.sender_website:
            body += f"\n{req.sender_website}"
        body += "\n\nIf this isn't relevant, reply 'no thanks' and I won't follow up."
        return subject, body
    if req.channel == "x":
        body = (f"Hi {first_name} — I came across {company}. I build {req.service} and am curious "
                "how your team handles repetitive workflows. Happy to share a relevant example if useful.")
    else:
        body = (f"Hi {first_name} — I came across {company} and was curious how your team handles "
                f"repetitive workflows. I build {req.service}. If useful, I can share a small example "
                "tailored to your work. Interested?")
    return "", body

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0", "live_sending_enabled": AUTO_SEND_ENABLED,
            "daily_send_limit": DAILY_SEND_LIMIT}

@app.post("/leads", status_code=201)
def create_lead(payload: LeadIn):
    with db() as conn:
        if payload.email and conn.execute("SELECT id FROM leads WHERE lower(email)=lower(?)", (payload.email.strip(),)).fetchone():
            raise HTTPException(409, "A lead with this email already exists.")
        cur = conn.execute("""INSERT INTO leads
          (name, company, role, website, email, x_handle, instagram_handle, segment, notes, source_url, contact_basis, created_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
          (payload.name.strip(), payload.company.strip(), payload.role.strip(), payload.website.strip(),
           payload.email.strip(), payload.x_handle.strip(), payload.instagram_handle.strip(), payload.segment,
           payload.notes.strip(), payload.source_url.strip(), payload.contact_basis.strip(), utc_now()))
        return row_dict(conn.execute("SELECT * FROM leads WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/leads")
def list_leads(status: Optional[str] = None, limit: int = 100):
    limit = min(max(limit, 1), 500)
    with db() as conn:
        rows = conn.execute("SELECT * FROM leads" + (" WHERE status=?" if status else "") +
            " ORDER BY id DESC LIMIT ?", ((status, limit) if status else (limit,))).fetchall()
        return [row_dict(r) for r in rows]

@app.get("/leads/{lead_id}")
def get_lead(lead_id: int):
    with db() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lead:
            raise HTTPException(404, "Lead not found.")
        return row_dict(lead)

@app.post("/leads/{lead_id}/drafts", status_code=201)
def create_draft(lead_id: int, payload: DraftIn):
    with db() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lead:
            raise HTTPException(404, "Lead not found.")
        destination = destination_for(lead, payload.channel)
        if not destination:
            raise HTTPException(422, f"No {payload.channel} destination saved for this lead.")
        if is_suppressed(conn, destination):
            raise HTTPException(409, "This destination is on the suppression list.")
        subject, body = build_draft(lead, payload)
        cur = conn.execute("INSERT INTO drafts (lead_id, channel, subject, body, created_at) VALUES (?, ?, ?, ?, ?)",
                           (lead_id, payload.channel, subject, body, utc_now()))
        conn.execute("INSERT INTO outreach_events (lead_id, draft_id, channel, event, detail, created_at) VALUES (?, ?, ?, 'draft_created', 'Draft created', ?)",
                     (lead_id, cur.lastrowid, payload.channel, utc_now()))
        return row_dict(conn.execute("SELECT * FROM drafts WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/drafts")
def list_drafts(status: Optional[str] = None, limit: int = 100):
    limit = min(max(limit, 1), 500)
    with db() as conn:
        rows = conn.execute("SELECT * FROM drafts" + (" WHERE status=?" if status else "") +
            " ORDER BY id DESC LIMIT ?", ((status, limit) if status else (limit,))).fetchall()
        return [row_dict(r) for r in rows]

@app.post("/drafts/{draft_id}/queue")
def queue_draft(draft_id: int, payload: QueueIn):
    if not payload.approved_by_user:
        raise HTTPException(400, "Explicit user approval is required before queueing.")
    with db() as conn:
        draft = conn.execute("""SELECT drafts.*, leads.email, leads.x_handle, leads.instagram_handle
            FROM drafts JOIN leads ON leads.id=drafts.lead_id WHERE drafts.id=?""", (draft_id,)).fetchone()
        if not draft:
            raise HTTPException(404, "Draft not found.")
        if draft["status"] in ("queued", "sent", "suppressed"):
            raise HTTPException(409, f"Draft is already {draft['status']}.")
        destination = destination_for(draft, draft["channel"])
        if not destination or is_suppressed(conn, destination):
            conn.execute("UPDATE drafts SET status='suppressed' WHERE id=?", (draft_id,))
            raise HTTPException(409, "Missing destination or destination is suppressed.")
        conn.execute("UPDATE drafts SET status='queued' WHERE id=?", (draft_id,))
        conn.execute("INSERT INTO outreach_events (lead_id, draft_id, channel, event, detail, created_at) VALUES (?, ?, ?, 'queued', 'Approved; waiting for channel adapter', ?)",
                     (draft["lead_id"], draft_id, draft["channel"], utc_now()))
        return {"draft_id": draft_id, "status": "queued", "sent": False,
                "message": "Queued only. No message was sent; channel adapter is not enabled."}

@app.post("/suppression", status_code=201)
def add_suppression(payload: SuppressIn):
    destination = payload.destination.strip()
    with db() as conn:
        conn.execute("INSERT INTO suppression (destination, reason, created_at) VALUES (?, ?, ?) ON CONFLICT(destination) DO UPDATE SET reason=excluded.reason",
                     (destination, payload.reason.strip(), utc_now()))
        conn.execute("""UPDATE drafts SET status='suppressed' WHERE status IN ('draft','queued') AND lead_id IN
            (SELECT id FROM leads WHERE lower(email)=lower(?) OR lower(x_handle)=lower(?) OR lower(instagram_handle)=lower(?))""",
                     (destination, destination, destination))
        return {"destination": destination, "suppressed": True}

@app.get("/suppression")
def list_suppression():
    with db() as conn:
        return [row_dict(r) for r in conn.execute("SELECT * FROM suppression ORDER BY id DESC").fetchall()]

@app.get("/events")
def list_events(limit: int = 100):
    limit = min(max(limit, 1), 500)
    with db() as conn:
        return [row_dict(r) for r in conn.execute("SELECT * FROM outreach_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

@app.post("/dispatch/run")
def run_dispatch():
    if not AUTO_SEND_ENABLED:
        return {"status": "dry_run", "sent": 0, "message": "Live sending is disabled. Configure and test an official channel adapter first."}
    raise HTTPException(501, "A channel adapter and authorization checks must be implemented before live sending can be enabled.")
