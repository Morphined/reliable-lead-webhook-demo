from __future__ import annotations

from collections import defaultdict

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.main import create_app


def build_client():
    calls = defaultdict(int)

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content.decode())
        email = body["email"].lower()
        stage = "enrichment" if request.url.path == "/enrichment" else "crm"
        calls[(stage, email)] += 1
        n = calls[(stage, email)]

        if stage == "enrichment":
            if "retry" in email and n <= 2:
                return httpx.Response(503, json={"detail": "transient"})
            company = body.get("company") or email.split("@")[1].split(".")[0]
            return httpx.Response(200, json={"normalized_company": company.title()})

        if "hardfail" in email:
            return httpx.Response(503, json={"detail": "terminal"})
        return httpx.Response(201, json={"crm_record_id": "crm_test_123"})

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        upstream_base_url="http://mock",
        max_attempts=3,
        backoff_seconds=0,
        request_timeout_seconds=1,
    )
    app = create_app(
        settings,
        engine=engine,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )
    return TestClient(app), calls


def payload(email="buyer@example.com"):
    return {
        "name": "Ada Buyer",
        "email": email,
        "company": "example labs",
        "source": "portfolio-demo",
    }


def test_success_persists_lineage():
    client, _ = build_client()
    response = client.post(
        "/webhooks/leads",
        headers={"Idempotency-Key": "lead-001"},
        json=payload(),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["duplicate"] is False
    assert data["event"]["status"] == "SUCCESS"
    assert data["event"]["crm_record_id"] == "crm_test_123"
    assert [(a["stage"], a["outcome"]) for a in data["event"]["attempts"]] == [
        ("enrichment", "SUCCESS"),
        ("crm", "SUCCESS"),
    ]


def test_duplicate_is_not_reprocessed():
    client, calls = build_client()
    headers = {"Idempotency-Key": "lead-dup-001"}
    first = client.post("/webhooks/leads", headers=headers, json=payload())
    second = client.post("/webhooks/leads", headers=headers, json=payload())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert calls[("enrichment", "buyer@example.com")] == 1
    assert calls[("crm", "buyer@example.com")] == 1


def test_transient_failure_retries_then_succeeds():
    client, calls = build_client()
    email = "retry@example.com"
    response = client.post(
        "/webhooks/leads",
        headers={"Idempotency-Key": "lead-retry-001"},
        json=payload(email),
    )
    assert response.status_code == 201
    data = response.json()["event"]
    enrichment_attempts = [a for a in data["attempts"] if a["stage"] == "enrichment"]
    assert [a["outcome"] for a in enrichment_attempts] == ["FAILED", "FAILED", "SUCCESS"]
    assert calls[("enrichment", email)] == 3
    assert data["status"] == "SUCCESS"


def test_terminal_failure_records_alert_and_does_not_call_crm_twice_outside_retry_loop():
    client, calls = build_client()
    email = "hardfail@example.com"
    response = client.post(
        "/webhooks/leads",
        headers={"Idempotency-Key": "lead-fail-001"},
        json=payload(email),
    )
    assert response.status_code == 502
    event = response.json()["event"]
    assert event["status"] == "FAILED"
    assert len(event["alerts"]) == 1
    assert calls[("enrichment", email)] == 1
    assert calls[("crm", email)] == 3


def test_failed_duplicate_is_not_implicitly_reprocessed():
    client, calls = build_client()
    email = "hardfail@example.com"
    headers = {"Idempotency-Key": "lead-fail-dup-001"}
    first = client.post("/webhooks/leads", headers=headers, json=payload(email))
    second = client.post("/webhooks/leads", headers=headers, json=payload(email))

    assert first.status_code == 502
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert calls[("crm", email)] == 3


def test_explicit_retry_targets_only_failed_event():
    client, calls = build_client()
    email = "hardfail@example.com"
    first = client.post(
        "/webhooks/leads",
        headers={"Idempotency-Key": "lead-explicit-retry-001"},
        json=payload(email),
    )
    event_id = first.json()["event"]["id"]
    second = client.post(f"/events/{event_id}/retry")

    assert first.status_code == 502
    assert second.status_code == 502
    assert calls[("enrichment", email)] == 2
    assert calls[("crm", email)] == 6
    assert len(second.json()["alerts"]) == 2


def test_validation_rejects_bad_email_before_processing():
    client, calls = build_client()
    response = client.post(
        "/webhooks/leads",
        headers={"Idempotency-Key": "lead-invalid-001"},
        json=payload("not-an-email"),
    )
    assert response.status_code == 422
    assert not calls
