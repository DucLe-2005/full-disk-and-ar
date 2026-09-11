"""Event query and response shaping rules."""

from datetime import datetime, timedelta, timezone
import re
from typing import Optional

from fastapi import HTTPException

from app.dto.events import ActiveRegionsResponseDto, ActualRegionDto
from app.models.event import to_event_response
from app.repositories.event_repository import EventRepository
from app.services.coordinates_service import CoordinatesService


NOAA_ACTIVE_REGION_PATTERN = re.compile(r"\(\s*(\d+)\s*\)")


class EventsService:
    def __init__(self, repository: Optional[EventRepository] = None) -> None:
        """Use an injected event repository or the configured MongoDB repository."""
        self.repository = repository or EventRepository()

    @staticmethod
    def _parse_iso_date(value: str, end_of_day: bool = False) -> datetime:
        """Parse an ISO-8601 value as UTC and expand date-only upper bounds.

        When ``end_of_day`` is true, a value such as ``2026-03-27`` becomes
        midnight at the beginning of the next day for an exclusive query bound.
        """
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise HTTPException(422, "Dates must use ISO-8601 format.") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if len(value) == 10 and end_of_day:
            parsed += timedelta(days=1)
        return parsed.astimezone(timezone.utc)

    def list_events(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        goes_class: Optional[str] = None,
    ) -> list[dict]:
        """Return public event records filtered by start time and GOES prefix."""
        filters: dict = {}
        if start_date or end_date:
            date_filter: dict = {}
            if start_date:
                date_filter["$gte"] = self._parse_iso_date(start_date)
            if end_date:
                date_filter["$lt"] = self._parse_iso_date(end_date, end_of_day=True)
            filters["event_start_at"] = date_filter
        if goes_class:
            filters["event_GOES"] = {"$regex": f"^{re.escape(goes_class)}", "$options": "i"}
        return [to_event_response(event) for event in self.repository.find_many(filters)]

    def get_event(self, event_id: str) -> Optional[dict]:
        """Return one public event record, excluding MongoDB-only internal fields."""
        event = self.repository.find_one(event_id)
        return to_event_response(event) if event else None

    @staticmethod
    def _active_region_id(position: str) -> str | None:
        """Return the NOAA active-region number embedded in an LMSAL position."""
        match = NOAA_ACTIVE_REGION_PATTERN.search(position)
        return match.group(1) if match else None

    def get_active_regions(
        self,
        prediction_timestamp: datetime,
        window_hours: int,
        goes_classes: str,
    ) -> ActiveRegionsResponseDto:
        """Group M/X events fully contained in a prediction window by region.

        Both the event start and stop must fall within the next ``window_hours``.
        The parenthesized number in ``event_position`` is the grouping key;
        events without that number cannot be reliably deduplicated and are
        omitted from this response.
        """
        if prediction_timestamp.tzinfo is None:
            prediction_timestamp = prediction_timestamp.replace(tzinfo=timezone.utc)
        start = prediction_timestamp.astimezone(timezone.utc)
        end = start + timedelta(hours=window_hours)
        classes = [item.strip().upper() for item in goes_classes.split(",") if item.strip()]
        if not classes or any(not re.fullmatch(r"[A-Z]", item) for item in classes):
            raise HTTPException(422, "goes_classes must be a comma-separated list such as M,X.")

        events = self.repository.find_active_window(
            start,
            end,
            f"^({'|'.join(map(re.escape, classes))})",
        )
        grouped_regions: dict[str, ActualRegionDto] = {}
        for event in events:
            position = event.get("event_position")
            if not position:
                continue

            # Using the parenthesized number in the position string as the NOAA active-region ID
            region_id = self._active_region_id(position)
            if region_id is None:
                continue

            pix_x = event.get("pix_x")
            pix_y = event.get("pix_y")
            if pix_x is None or pix_y is None:
                point = CoordinatesService.position_to_pixel(position)
                if point is not None:
                    pix_x, pix_y = point

            region = grouped_regions.setdefault(
                region_id,
                ActualRegionDto(
                    region_id=region_id,
                    event_position=position,
                    pix_x=pix_x,
                    pix_y=pix_y,
                ),
            )
            region.events.append(to_event_response(event))

        return ActiveRegionsResponseDto(
            prediction_timestamp=start,
            window_end=end,
            window_hours=window_hours,
            goes_classes=classes,
            regions=list(grouped_regions.values()),
        )
