"""CLI entry point for a targeted LMSAL event-window scrape."""

import argparse
from datetime import date, datetime, timedelta, timezone

from app.services.scraper_service import LmsalScraperService


def parse_timestamp(value: str) -> datetime:
    """Parse a CLI ISO-8601 timestamp, treating a naive value as UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use an ISO-8601 timestamp, for example 2026-03-27T00:00:00Z.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_hour(value: str, *, end_of_day: bool = False) -> datetime:
    """Normalize an inclusive forecast range endpoint to a UTC hour."""
    try:
        day = date.fromisoformat(value)
    except ValueError:
        slot = parse_timestamp(value).astimezone(timezone.utc)
    else:
        slot = datetime(day.year, day.month, day.day, 23 if end_of_day else 0, tzinfo=timezone.utc)
    if slot.minute or slot.second or slot.microsecond:
        raise argparse.ArgumentTypeError("Forecast slots must fall on a whole UTC hour.")
    return slot


def main() -> None:
    """Parse CLI options and synchronously scrape one requested event window."""
    parser = argparse.ArgumentParser(description="Scrape LMSAL flare events for one time window.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--timestamp", type=parse_timestamp, help="UTC window start time")
    mode.add_argument("--start-time", type=parse_hour, help="First UTC slot in an inclusive forecast range")
    parser.add_argument("--end-time", help="Last UTC slot. A date includes its final hour")
    parser.add_argument("--window-hours", type=int, default=24, choices=range(1, 169))
    arguments = parser.parse_args()
    start = arguments.timestamp
    window_hours = arguments.window_hours
    if arguments.start_time is not None:
        if arguments.end_time is None:
            parser.error("--start-time requires --end-time")
        try:
            last = parse_hour(arguments.end_time, end_of_day=True)
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = arguments.start_time
        if start > last or last > now:
            parser.error("Choose an ordered range that ends at or before the current UTC hour")
        # Include the entire last forecast hour in the half-open event window.
        window_hours = (last - start) // timedelta(hours=1) + 1
    elif arguments.end_time is not None:
        parser.error("--end-time requires --start-time")

    count = LmsalScraperService().scrape_event_window(start, window_hours)
    print(f"Upserted {count} events for the requested window.")


if __name__ == "__main__":
    main()
