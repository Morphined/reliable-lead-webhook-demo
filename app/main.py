from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .db import Base, build_engine, build_session_factory
from .models import LeadEvent
from .processor import process_event
from .repository import create_event, get_event
from .schemas import EventOut, IngestResponse, LeadIn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    transport=None,
    sleep=None,
) -> FastAPI:
    settings = settings or Settings()
    engine = engine or build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    Base.metadata.create_all(engine)

    app = FastAPI(
        title="Reliable Lead Webhook Demo",
        version="1.0.0",
        description=(
            "Portfolio demo showing idempotency, validation, deterministic retries, "
            "persistent attempt history, selective retry and failure alerting."
        ),
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.transport = transport
    app.state.sleep = sleep

    def get_db() -> Session:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/leads", response_model=IngestResponse)
    def ingest_lead(
        lead: LeadIn,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=6, max_length=128),
        db: Session = Depends(get_db),
    ):
        event, created = create_event(db, idempotency_key, lead)
        if not created:
            db.refresh(event)
            return IngestResponse(duplicate=True, event=EventOut.model_validate(event))

        processed = process_event(
            db,
            event,
            settings,
            transport=app.state.transport,
            sleep=app.state.sleep or (lambda seconds: __import__("time").sleep(seconds)),
        )
        payload = IngestResponse(duplicate=False, event=EventOut.model_validate(processed))
        if processed.status == "FAILED":
            return JSONResponse(status_code=502, content=payload.model_dump(mode="json"))
        return JSONResponse(status_code=201, content=payload.model_dump(mode="json"))

    @app.post("/events/{event_id}/retry", response_model=EventOut)
    def retry_event(event_id: str, db: Session = Depends(get_db)):
        event = get_event(db, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        if event.status == "SUCCESS":
            raise HTTPException(status_code=409, detail="Successful events are not reprocessed")

        processed = process_event(
            db,
            event,
            settings,
            transport=app.state.transport,
            sleep=app.state.sleep or (lambda seconds: __import__("time").sleep(seconds)),
        )
        if processed.status == "FAILED":
            return JSONResponse(status_code=502, content=EventOut.model_validate(processed).model_dump(mode="json"))
        return processed

    @app.get("/events", response_model=list[EventOut])
    def list_events(db: Session = Depends(get_db)):
        return list(db.scalars(select(LeadEvent).order_by(LeadEvent.created_at.desc())).all())

    @app.get("/events/{event_id}", response_model=EventOut)
    def read_event(event_id: str, db: Session = Depends(get_db)):
        event = get_event(db, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    return app


app = create_app()
