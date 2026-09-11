"""CLI entry point for a targeted LMSAL event-window scrape."""

import argparse
from datetime import datetime, timezone

from app.services.scraper_service import LmsalScraperService


def parse_timestamp(value: str) -> datetime:
    """Parse a CLI ISO-8601 timestamp, treating a naive value as UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use an ISO-8601 timestamp, for example 2026-03-27T00:00:00Z.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> None:
    """Parse CLI options and synchronously scrape one requested event window."""
    parser = argparse.ArgumentParser(description="Scrape LMSAL flare events for one time window.")
    parser.add_argument("--timestamp", required=True, type=parse_timestamp, help="UTC window start time")
    parser.add_argument("--window-hours", type=int, default=24, choices=range(1, 169))
    arguments = parser.parse_args()
    count = LmsalScraperService().scrape_event_window(arguments.timestamp, arguments.window_hours)
    print(f"Upserted {count} events for the requested window.")


if __name__ == "__main__":
    main()
