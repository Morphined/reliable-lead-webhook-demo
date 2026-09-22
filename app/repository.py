from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AlertRecord, LeadEvent, ProcessingAttempt
from .schemas import LeadIn


def get_by_idempotency_key(db: Session, key: str) -> LeadEvent | None:
    return db.scalar(select(LeadEvent).where(LeadEvent.idempotency_key == key))


def get_event(db: Session, event_id: str) -> LeadEvent | None:
    return db.get(LeadEvent, event_id)


def create_event(db: Session, key: str, lead: LeadIn) -> tuple[LeadEvent, bool]:
    existing = get_by_idempotency_key(db, key)
    if existing:
        return existing, False

    event = LeadEvent(
        idempotency_key=key,
        name=lead.name,
        email=str(lead.email),
        company=lead.company,
        source=lead.source,
        status="PENDING",
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
        return event, True
    except IntegrityError:
        db.rollback()
        existing = get_by_idempotency_key(db, key)
        if existing is None:
            raise
        return existing, False


def next_attempt_no(db: Session, event_id: str, stage: str) -> int:
    current = db.scalar(
        select(func.max(ProcessingAttempt.attempt_no)).where(
            ProcessingAttempt.event_id == event_id,
            ProcessingAttempt.stage == stage,
        )
    )
    return int(current or 0) + 1


def record_attempt(
    db: Session,
    *,
    event_id: str,
    stage: str,
    attempt_no: int,
    outcome: str,
    http_status: int | None = None,
    error: str | None = None,
) -> None:
    db.add(
        ProcessingAttempt(
            event_id=event_id,
            stage=stage,
            attempt_no=attempt_no,
            outcome=outcome,
            http_status=http_status,
            error=error,
        )
    )
    db.commit()


def record_alert(db: Session, event_id: str, message: str) -> None:
    db.add(AlertRecord(event_id=event_id, channel="demo-log", message=message))
    db.commit()
