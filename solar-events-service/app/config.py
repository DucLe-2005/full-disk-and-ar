"""Environment-based configuration for the solar-events service."""

import os
from pathlib import Path


class Settings:
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_database = os.getenv("MONGODB_DATABASE", "solar_events")
    lmsal_base_url = "https://www.lmsal.com/solarsoft"
    lmsal_archive_url = "https://www.lmsal.com/solarsoft/latest_events_archive.html"
    noaa_data_directory = Path(os.getenv("NOAA_DATA_DIRECTORY", "noaa_data"))
    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )


settings = Settings()
