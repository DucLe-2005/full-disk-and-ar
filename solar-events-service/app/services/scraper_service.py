"""LMSAL archive scraping and event upsert orchestration."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Callable, Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.models.event import parse_event_datetime
from app.repositories.event_repository import EventRepository


logger = logging.getLogger(__name__)


class LmsalScraperService:
    def __init__(self, repository: Optional[EventRepository] = None) -> None:
        """Use an injected event repository or the configured MongoDB repository."""
        self.repository = repository or EventRepository()

    def scrape_historical(self) -> int:
        """Scrape and upsert every LMSAL snapshot dated on or after 2015-07-01."""
        return self._scrape(lambda snapshot_date: snapshot_date >= "20150701")

    def scrape_recent(self, now: Optional[datetime] = None) -> int:
        """Scrape and upsert snapshots for the current and previous UTC dates."""
        current_time = now or datetime.now(timezone.utc)
        allowed_dates = {
            current_time.strftime("%Y%m%d"),
            (current_time - timedelta(days=1)).strftime("%Y%m%d"),
        }
        return self._scrape(lambda snapshot_date: snapshot_date in allowed_dates)

    def scrape_event_window(
        self,
        start: datetime,
        window_hours: int = 24,
        publication_lookahead_days: int = 2,
    ) -> int:
        """Scrape a bounded event window for development or targeted backfills.

        LMSAL snapshots are publication-time pages, not event-time pages. We
        inspect snapshots through two days after the requested window so late
        reports are still eligible, then only upsert events that started in
        ``[start, start + window_hours)``.
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        start = start.astimezone(timezone.utc)
        end = start + timedelta(hours=window_hours)
        first_snapshot_date = start.strftime("%Y%m%d")
        last_snapshot_date = (end + timedelta(days=publication_lookahead_days)).strftime("%Y%m%d")

        def is_in_requested_window(event: dict) -> bool:
            """Return whether an event starts inside the requested half-open window."""
            event_time = parse_event_datetime(event.get("event_start"))
            return event_time is not None and start <= event_time < end

        return self._scrape(
            lambda snapshot_date: first_snapshot_date <= snapshot_date <= last_snapshot_date,
            is_in_requested_window,
        )

    def _scrape(
        self,
        include_snapshot: Callable[[str], bool],
        include_event: Optional[Callable[[dict], bool]] = None,
    ) -> int:
        """Scrape selected snapshots, optionally filter events, and upsert them.

        Failure to download one snapshot is logged and skipped so the remaining
        archive pages can still be processed.
        """
        response = httpx.get(settings.lmsal_archive_url, timeout=20)
        response.raise_for_status()
        archive = BeautifulSoup(response.text, "html.parser")
        events = []
        for snapshot_url in self._snapshot_urls(archive, include_snapshot):
            try:
                snapshot_events = self._events_from_snapshot(snapshot_url)
                events.extend(event for event in snapshot_events if include_event is None or include_event(event))
            except httpx.HTTPError as error:
                logger.warning("Skipping LMSAL snapshot %s: %s", snapshot_url, error)
        return self.repository.upsert_many(events)


    @staticmethod
    def _snapshot_urls(archive: BeautifulSoup, include_snapshot: Callable[[str], bool]) -> list[str]:
        """Return absolute LMSAL snapshot URLs accepted by the date predicate."""
        urls = []
        for link in archive.find_all("a"):
            href = link.get("href")
            if not href or "last_events_" not in href:
                continue
            snapshot_date = href.split("last_events_", 1)[1][:8]
            if include_snapshot(snapshot_date):
                urls.append(f"{settings.lmsal_base_url}/{href}")
        return urls

    @staticmethod
    def _events_from_snapshot(snapshot_url: str) -> list[dict]:
        """Parse one LMSAL snapshot table into raw solar-event dictionaries."""
        response = httpx.get(snapshot_url, timeout=20)
        response.raise_for_status()
        snapshot = BeautifulSoup(response.text, "html.parser")
        table = next((table for table in snapshot.find_all("table") if "gev_" in table.get_text()), None)
        if table is None:
            return []
        values = [cell.get_text(strip=True) for cell in table.find_all("td")]
        events = []
        for index, event_id in enumerate(values):
            if not event_id.startswith("gev_") or index + 5 >= len(values):
                continue
            events.append(
                {
                    "event_id": event_id,
                    "event_start": values[index + 1],
                    "event_stop": values[index + 2],
                    "event_peak": values[index + 3],
                    "event_GOES": values[index + 4],
                    "event_position": values[index + 5],
                    "seen_in_dates": [snapshot_url],
                }
            )
        return events
