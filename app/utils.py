import hashlib
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterable

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_event_fingerprint(parts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.strip().lower().encode("utf-8"))
        digest.update(b"|")
    return digest.hexdigest()


def parse_datetime(value: str) -> datetime:
    from dateutil import parser

    parsed = parser.parse(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def new_correlation_id() -> str:
    return f"cid-{secrets.token_hex(8)}"
