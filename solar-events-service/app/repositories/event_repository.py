"""MongoDB operations for solar-event documents."""

from datetime import datetime
from typing import Any, Iterable, Optional

from pymongo import UpdateOne
from pymongo.collection import Collection

from app.db.mongo import get_events_collection
from app.models.event import to_event_document


class EventRepository:
    def __init__(self, collection: Optional[Collection] = None) -> None:
        """Use the supplied collection, or connect to the configured events collection."""
        self.collection = collection or get_events_collection()

    def find_many(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Return matching event documents ordered by their normalized start time."""
        return list(self.collection.find(filters).sort("event_start_at", 1))

    def find_one(self, event_id: str) -> Optional[dict[str, Any]]:
        """Return one event by its stable LMSAL event identifier, if it exists."""
        return self.collection.find_one({"event_id": event_id})

    def find_active_window(
        self,
        start: datetime,
        end: datetime,
        goes_pattern: str,
    ) -> list[dict[str, Any]]:
        """Return GOES events whose normalized peak is inside ``[start, end)``."""
        query = {
            "event_peak_at": {"$gte": start, "$lt": end},
            "event_GOES": {"$regex": goes_pattern, "$options": "i"},
        }
        return list(self.collection.find(query).sort("event_peak_at", 1))

    def upsert_many(self, events: Iterable[dict[str, Any]]) -> int:
        """Normalize and upsert events while merging their LMSAL snapshot URLs.

        ``event_id`` is the unique key. Repeated observations update the event
        fields and add new ``seen_in_dates`` values without creating duplicates.
        The returned count is the number of valid upsert operations submitted.
        """
        operations = []
        for event in events:
            document = to_event_document(event)
            event_id = document.get("event_id")
            if not event_id:
                continue
            seen_in_dates = list(dict.fromkeys(document.pop("seen_in_dates", [])))
            update: dict[str, Any] = {"$set": document}
            if seen_in_dates:
                update["$addToSet"] = {"seen_in_dates": {"$each": seen_in_dates}}
            operations.append(UpdateOne({"event_id": event_id}, update, upsert=True))
        if operations:
            self.collection.bulk_write(operations, ordered=False)
        return len(operations)

    def all_start_timestamps(self) -> list[datetime]:
        """Return distinct normalized event start times used to select NOAA reports."""
        return [timestamp for timestamp in self.collection.distinct("event_start_at") if timestamp]

    def list_for_quality_matching(self):
        """Stream only the event fields required for NOAA quality comparison."""
        return self.collection.find({}, {"event_id": 1, "event_start": 1, "event_stop": 1, "event_GOES": 1})

    def list_with_positions(self):
        """Stream event identifiers and positions eligible for pixel enrichment."""
        return self.collection.find({"event_position": {"$exists": True}}, {"event_position": 1})

    def bulk_update(self, operations: list[UpdateOne]) -> None:
        """Apply unordered MongoDB updates, doing nothing when the list is empty."""
        if operations:
            self.collection.bulk_write(operations, ordered=False)
