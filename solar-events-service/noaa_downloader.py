"""CLI entry point for downloading NOAA reports."""

from app.services.noaa_service import NoaaService


if __name__ == "__main__":
    NoaaService().download_reports()
