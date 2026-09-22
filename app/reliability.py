from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .repository import next_attempt_no, record_attempt


class UpstreamFailure(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def post_json_with_retry(
    *,
    db: Session,
    event_id: str,
    stage: str,
    client: httpx.Client,
    url: str,
    payload: dict[str, Any],
    max_attempts: int,
    backoff_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    last_error = "unknown upstream error"

    for local_index in range(max_attempts):
        attempt_no = next_attempt_no(db, event_id, stage)
        try:
            response = client.post(url, json=payload)
            if 200 <= response.status_code < 300:
                record_attempt(
                    db,
                    event_id=event_id,
                    stage=stage,
                    attempt_no=attempt_no,
                    outcome="SUCCESS",
                    http_status=response.status_code,
                )
                return response.json()

            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            record_attempt(
                db,
                event_id=event_id,
                stage=stage,
                attempt_no=attempt_no,
                outcome="FAILED",
                http_status=response.status_code,
                error=last_error,
            )
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            record_attempt(
                db,
                event_id=event_id,
                stage=stage,
                attempt_no=attempt_no,
                outcome="FAILED",
                error=last_error,
            )

        if local_index < max_attempts - 1:
            sleep(backoff_seconds * (2**local_index))

    raise UpstreamFailure(stage, last_error)
