from __future__ import annotations

from datetime import UTC, datetime


def current_utc_datetime() -> datetime:
    return datetime.now(UTC)


def current_utc_iso() -> str:
    return current_utc_datetime().isoformat()
