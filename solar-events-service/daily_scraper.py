"""CLI entry point for the daily LMSAL update scrape."""

from app.services.scraper_service import LmsalScraperService


def main() -> None:
    """Run the recent LMSAL scrape and print the submitted upsert count."""
    print(f"Upserted {LmsalScraperService().scrape_recent()} scraped events into MongoDB.")


if __name__ == "__main__":
    main()
