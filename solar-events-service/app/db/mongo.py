"""MongoDB connection and collection initialization."""

from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

from app.config import settings


@lru_cache(maxsize=1)
def get_events_collection() -> Collection:
    """Return the shared MongoDB events collection and ensure its indexes exist.

    The function is cached so one process reuses a single MongoClient and does
    not recreate the collection handle for every API request.
    """
    client = MongoClient(settings.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    collection = client[settings.mongodb_database]["events"]
    collection.create_index([("event_id", ASCENDING)], unique=True, name="event_id_unique")
    collection.create_index([("event_start_at", ASCENDING)], name="event_start_at")
    collection.create_index([("event_peak_at", ASCENDING)], name="event_peak_at")
    collection.create_index([("event_GOES", ASCENDING)], name="event_goes")
    return collection


def ping_database() -> None:
    """Raise a PyMongo error when the configured MongoDB server is unavailable."""
    get_events_collection().database.client.admin.command("ping")
