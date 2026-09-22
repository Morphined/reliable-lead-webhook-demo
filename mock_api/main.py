from __future__ import annotations

from collections import defaultdict
import hashlib

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

app = FastAPI(title="Mock CRM and Enrichment APIs", version="1.0.0")
_calls: dict[tuple[str, str], int] = defaultdict(int)


class EnrichmentIn(BaseModel):
    email: EmailStr
    company: str | None = None


class CRMIn(BaseModel):
    name: str
    email: EmailStr
    company: str | None = None
    source: str | None = None
    external_event_id: str


def _bump(stage: str, email: str) -> int:
    key = (stage, email.lower())
    _calls[key] += 1
    return _calls[key]


@app.post("/enrichment")
def enrichment(payload: EnrichmentIn):
    n = _bump("enrichment", str(payload.email))
    email = str(payload.email).lower()
    if "retry" in email and n <= 2:
        raise HTTPException(status_code=503, detail=f"deterministic transient failure #{n}")
    normalized = payload.company.strip().title() if payload.company else email.split("@")[1].split(".")[0].title()
    return {"normalized_company": normalized, "attempt_seen_by_mock": n}


@app.post("/crm/leads")
def create_crm_lead(payload: CRMIn):
    n = _bump("crm", str(payload.email))
    email = str(payload.email).lower()
    if "hardfail" in email:
        raise HTTPException(status_code=503, detail="deterministic terminal CRM outage for demo")
    digest = hashlib.sha256(payload.external_event_id.encode()).hexdigest()[:10]
    return {"crm_record_id": f"crm_{digest}", "attempt_seen_by_mock": n}


@app.post("/admin/reset")
def reset():
    _calls.clear()
    return {"status": "reset"}
