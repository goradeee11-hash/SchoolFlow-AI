"""Timezone helpers for UTC storage, comparisons, and Riyadh display."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_RIYADH_ZONE = "Asia/Riyadh"


def timestamp_to_utc(value: object) -> datetime:
    """Parse an ISO timestamp; interpret legacy naive values as host-local time."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO 8601 string.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be a valid ISO 8601 value.") from exc
    if parsed.utcoffset() is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc)


def timestamp_sort_key(value: object) -> datetime:
    """Return a UTC sort key; invalid or missing timestamps sort before valid ones."""
    try:
        return timestamp_to_utc(value)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def format_timestamp_riyadh(value: object, *, include_date: bool = True) -> str:
    """Format an ISO timestamp in Asia/Riyadh without mutating its source value."""
    if value is None or value == "":
        return "—"
    utc_value = timestamp_to_utc(value)
    try:
        riyadh = ZoneInfo(_RIYADH_ZONE)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            "IANA timezone data for Asia/Riyadh is unavailable; install the "
            "tzdata package or configure the system timezone database."
        ) from exc

    local_value = utc_value.astimezone(riyadh)
    pattern = "%Y-%m-%d %H:%M:%S %z" if include_date else "%H:%M %z"
    return f"{local_value.strftime(pattern)} ({_RIYADH_ZONE})"
