from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite:///./reliable_leads.db"
    )
    upstream_base_url: str = os.getenv("UPSTREAM_BASE_URL", "http://localhost:8090")
    max_attempts: int = int(os.getenv("MAX_ATTEMPTS", "3"))
    backoff_seconds: float = float(os.getenv("BACKOFF_SECONDS", "0.25"))
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "3"))
