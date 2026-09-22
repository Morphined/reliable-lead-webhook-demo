from __future__ import annotations

import logging
import httpx
from sqlalchemy.orm import Session

from .config import Settings
from .models import LeadEvent
from .reliability import UpstreamFailure, post_json_with_retry
from .repository import record_alert

logger = logging.getLogger("reliable_leads")


def process_event(
    db: Session,
    event: LeadEvent,
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep=lambda seconds: __import__("time").sleep(seconds),
) -> LeadEvent:
    event.status = "PROCESSING"
    event.last_error = None
    db.commit()

    try:
        with httpx.Client(
            timeout=settings.request_timeout_seconds,
            transport=transport,
        ) as client:
            enrichment = post_json_with_retry(
                db=db,
                event_id=event.id,
                stage="enrichment",
                client=client,
                url=f"{settings.upstream_base_url}/enrichment",
                payload={"email": event.email, "company": event.company},
                max_attempts=settings.max_attempts,
                backoff_seconds=settings.backoff_seconds,
                sleep=sleep,
            )
            event.enriched_company = enrichment.get("normalized_company")
            db.commit()

            crm = post_json_with_retry(
                db=db,
                event_id=event.id,
                stage="crm",
                client=client,
                url=f"{settings.upstream_base_url}/crm/leads",
                payload={
                    "name": event.name,
                    "email": event.email,
                    "company": event.enriched_company or event.company,
                    "source": event.source,
                    "external_event_id": event.id,
                },
                max_attempts=settings.max_attempts,
                backoff_seconds=settings.backoff_seconds,
                sleep=sleep,
            )
            event.crm_record_id = crm.get("crm_record_id")
            event.status = "SUCCESS"
            event.last_error = None
            db.commit()
            db.refresh(event)
            return event

    except UpstreamFailure as exc:
        event.status = "FAILED"
        event.last_error = f"{exc.stage}: {exc}"
        db.commit()
        message = f"Lead event {event.id} failed at stage '{exc.stage}' after retries: {exc}"
        record_alert(db, event.id, message)
        logger.error(message)
        db.refresh(event)
        return event
