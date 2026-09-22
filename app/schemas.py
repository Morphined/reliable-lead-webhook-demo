from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    company: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=100)


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    attempt_no: int
    outcome: str
    http_status: int | None
    error: str | None
    created_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel: str
    message: str
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idempotency_key: str
    name: str
    email: str
    company: str | None
    source: str | None
    status: str
    enriched_company: str | None
    crm_record_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    attempts: list[AttemptOut] = []
    alerts: list[AlertOut] = []


class IngestResponse(BaseModel):
    duplicate: bool
    event: EventOut
