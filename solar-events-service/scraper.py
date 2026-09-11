"""CLI entry point for the full LMSAL historical scrape."""

from app.services.scraper_service import LmsalScraperService


def main() -> None:
    """Run the full historical LMSAL scrape and print the submitted upsert count."""
    print(f"Upserted {LmsalScraperService().scrape_historical()} scraped events into MongoDB.")


if __name__ == "__main__":
    main()
