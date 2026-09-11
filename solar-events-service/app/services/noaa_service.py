"""NOAA report download and LMSAL quality matching."""

import ftplib
from pathlib import Path
from typing import Optional

from pymongo import UpdateOne

from app.config import settings
from app.repositories.event_repository import EventRepository


class NoaaService:
    def __init__(self, repository: Optional[EventRepository] = None) -> None:
        """Use an injected event repository or the configured MongoDB repository."""
        self.repository = repository or EventRepository()

    def download_reports(self) -> None:
        """Download missing NOAA daily reports for dates represented in MongoDB.

        Reports are retained as local source files in ``noaa_data``. A NOAA 550
        response is treated as a missing report and its empty destination is removed.
        """
        output_directory = settings.noaa_data_directory
        output_directory.mkdir(exist_ok=True)
        dates = {timestamp.strftime("%Y%m%d") for timestamp in self.repository.all_start_timestamps()}
        with ftplib.FTP("ftp.swpc.noaa.gov") as ftp:
            ftp.login()
            ftp.cwd("pub/indices/events")
            for date in sorted(dates):
                destination = output_directory / f"{date}events.txt"
                if destination.exists():
                    continue
                try:
                    with destination.open("wb") as output_file:
                        ftp.retrbinary(f"RETR {destination.name}", output_file.write)
                except ftplib.error_perm:
                    destination.unlink(missing_ok=True)

    def match_quality(self) -> None:
        """Compare stored LMSAL events with NOAA XRA rows and set quality flags.

        An event is ``HIGH`` quality when its date, exact GOES class, start time,
        and stop time match a NOAA row within the configured ten-minute tolerance;
        otherwise it is marked ``LOW``.
        """
        noaa_events = [
            event
            for report in settings.noaa_data_directory.glob("*events.txt")
            for event in self._parse_report(report)
        ]
        operations = []
        for event in self.repository.list_for_quality_matching():
            event_start = event.get("event_start")
            event_stop = event.get("event_stop")
            if not event_start or not event_stop:
                continue
            date, start_time = event_start.split(" ", 1)
            start = self._time_to_number(start_time)
            stop = self._time_to_number(event_stop)
            quality = "HIGH" if any(
                self._is_match(event, date, start, stop, candidate) for candidate in noaa_events
            ) else "LOW"
            operations.append(UpdateOne({"_id": event["_id"]}, {"$set": {"quality_flag": quality}}))
        self.repository.bulk_update(operations)

    @staticmethod
    def _parse_report(filename: Path) -> list[dict]:
        """Extract comparable XRA entries from one NOAA daily text report."""
        events = []
        with filename.open() as report:
            for line in report:
                fields = line.split()
                if line.startswith("#") or "XRA" not in fields:
                    continue
                index = fields.index("XRA")
                if index < 5 or len(fields) <= index + 2:
                    continue
                events.append(
                    {
                        "date": filename.name[:8],
                        "begin": fields[index - 5] if fields[index - 5] != "////" else None,
                        "end": fields[index - 3] if fields[index - 3] != "////" else None,
                        "goes_class": fields[index + 2] if fields[index + 2] != "////" else None,
                    }
                )
        return events

    @classmethod
    def _is_match(cls, event: dict, date: str, start: int, stop: int, candidate: dict) -> bool:
        """Return whether a NOAA candidate corroborates an LMSAL flare event."""
        if candidate["date"] != date.replace("/", "") or candidate["goes_class"] != event.get("event_GOES"):
            return False
        if not candidate["begin"] or not candidate["end"]:
            return False
        return (
            abs(cls._time_to_number(candidate["begin"]) - start) <= 10
            and abs(cls._time_to_number(candidate["end"]) - stop) <= 10
        )

    @staticmethod
    def _time_to_number(value: str) -> int:
        """Normalize a NOAA or LMSAL clock value to its first four HHMM digits."""
        return int("".join(filter(str.isdigit, value))[:4])
