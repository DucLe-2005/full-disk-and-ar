"""Import the bundled solar-event catalog into MongoDB once."""

import json
import logging
from pathlib import Path

from app.db.mongo import get_events_collection
from app.repositories.event_repository import EventRepository


logger = logging.getLogger(__name__)
SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "events.json"
SNAPSHOT_ID = "bundled-solar-events-v1"


def seed_event_catalog() -> None:
    collection = get_events_collection()
    imports = collection.database["catalog_imports"]
    if imports.find_one({"_id": SNAPSHOT_ID}) is not None:
        return

    with SNAPSHOT_PATH.open(encoding="utf-8") as snapshot:
        events = json.load(snapshot)
    if not events:
        raise ValueError(f"Empty solar-event catalog at {SNAPSHOT_PATH}")

    repository = EventRepository(collection)
    count = repository.upsert_many(events, insert_only=True)
    imports.update_one({"_id": SNAPSHOT_ID}, {"$set": {"event_count": count}}, upsert=True)
    logger.info("Processed %d records from the bundled solar-event catalog", count)
