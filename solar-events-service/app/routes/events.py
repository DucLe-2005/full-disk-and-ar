"""Solar-event REST endpoints."""

from datetime import datetime
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import Response

from app.dto.events import ActiveRegionsResponseDto, ScrapeStartedDto
from app.services.events_service import EventsService
from app.services.scraper_service import LmsalScraperService


router = APIRouter(tags=["events"])


@router.get("/events")
def list_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    goes_class: Optional[str] = None,
) -> list[dict]:
    """List MongoDB events filtered by optional start dates and GOES class."""
    return EventsService().list_events(start_date, end_date, goes_class)


@router.get("/events/download/")
def download_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    goes_class: Optional[str] = None,
) -> Response:
    """Download the filtered event list as a JSON attachment."""
    events = EventsService().list_events(start_date, end_date, goes_class)
    return Response(
        content=json.dumps(events, default=str),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=events.json"},
    )


@router.get("/active-regions", response_model=ActiveRegionsResponseDto)
def get_active_regions(
    prediction_timestamp: datetime,
    window_hours: int = Query(24, ge=1, le=168),
    goes_classes: str = "M,X",
) -> ActiveRegionsResponseDto:
    """Return unique NOAA active regions that flare in a prediction window."""
    return EventsService().get_active_regions(prediction_timestamp, window_hours, goes_classes)


@router.get("/scrape", response_model=ScrapeStartedDto)
def scrape_events(background_tasks: BackgroundTasks) -> ScrapeStartedDto:
    """Queue a background scrape for the current and previous UTC dates."""
    background_tasks.add_task(LmsalScraperService().scrape_recent)
    return ScrapeStartedDto()


@router.post("/scrape/window", response_model=ScrapeStartedDto)
def scrape_event_window(
    prediction_timestamp: datetime,
    background_tasks: BackgroundTasks,
    window_hours: int = Query(24, ge=1, le=168),
) -> ScrapeStartedDto:
    """Queue a bounded scrape for one prediction window; intended for development."""
    background_tasks.add_task(
        LmsalScraperService().scrape_event_window,
        prediction_timestamp,
        window_hours,
    )
    return ScrapeStartedDto(message="window scraper running in background")


@router.get("/events/{event_id}")
def get_event(event_id: str) -> dict:
    """Return one LMSAL event or respond with HTTP 404 when it does not exist."""
    event = EventsService().get_event(event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    return event
