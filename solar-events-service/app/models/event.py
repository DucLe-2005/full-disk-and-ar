"""Solar-event document model and timestamp normalization."""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


INTERNAL_EVENT_FIELDS = {"_id", "event_start_at", "event_peak_at", "event_stop_at"}


class SolarEvent(BaseModel):
    """Canonical MongoDB event document, retaining enrichment fields as extras."""

    model_config = ConfigDict(extra="allow")

    event_id: Optional[str] = None
    event_start: Optional[str] = None
    event_stop: Optional[str] = None
    event_peak: Optional[str] = None
    event_GOES: Optional[str] = None
    event_position: Optional[str] = None
    seen_in_dates: List[str] = Field(default_factory=list)
    quality_flag: Optional[str] = None
    pix_x: Optional[float] = None
    pix_y: Optional[float] = None
    event_start_at: Optional[datetime] = None
    event_peak_at: Optional[datetime] = None
    event_stop_at: Optional[datetime] = None


def parse_event_datetime(value: Optional[str], date: Optional[str] = None) -> Optional[datetime]:
    """Parse LMSAL timestamps as UTC, including time-only peak/stop fields."""
    if not value:
        return None
    normalized = value.strip()
    if date and " " not in normalized:
        normalized = f"{date} {normalized}"
    for format_string in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(normalized, format_string).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def to_event_document(event: dict[str, Any]) -> dict[str, Any]:
    """Return a MongoDB-ready event document with indexed timestamp fields."""
    document = SolarEvent.model_validate({key: value for key, value in event.items() if key != "_id"}).model_dump(
        mode="python",
        exclude_none=True,
    )
    event_start = document.get("event_start")
    date = event_start.split(" ", 1)[0] if isinstance(event_start, str) else None
    event_start_at = parse_event_datetime(event_start)
    event_peak_at = parse_event_datetime(document.get("event_peak"), date)
    event_stop_at = parse_event_datetime(document.get("event_stop"), date)
    if event_start_at is not None:
        if event_peak_at is not None and event_peak_at < event_start_at:
            event_peak_at += timedelta(days=1)
        if event_stop_at is not None and event_stop_at < event_start_at:
            event_stop_at += timedelta(days=1)
    document["event_start_at"] = event_start_at
    document["event_peak_at"] = event_peak_at
    document["event_stop_at"] = event_stop_at
    return document


def to_event_response(document: dict[str, Any]) -> dict[str, Any]:
    """Hide MongoDB identifiers and internal indexed timestamp fields."""
    return {key: value for key, value in document.items() if key not in INTERNAL_EVENT_FIELDS}
