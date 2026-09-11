"""CLI entry point for adding NOAA quality flags."""

from app.services.noaa_service import NoaaService


if __name__ == "__main__":
    NoaaService().match_quality()
