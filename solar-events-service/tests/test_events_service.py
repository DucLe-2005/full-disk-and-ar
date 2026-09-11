from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import events
from app.services.events_service import EventsService


class FakeEventRepository:
    def find_active_window(self, *_args):
        return [
            {
                "event_id": "event-1",
                "event_GOES": "M1.0",
                "event_position": "S22E79( 4525 )",
            },
            {
                "event_id": "event-2",
                "event_GOES": "X1.0",
                "event_position": "S21E78(4525)",
            },
            {
                "event_id": "event-3",
                "event_GOES": "M2.0",
                "event_position": "N10W20( 4526 )",
            },
            {
                "event_id": "event-4",
                "event_GOES": "M3.0",
                "event_position": "N11W21",
            },
        ]


def test_active_regions_group_events_by_noaa_region_number():
    response = EventsService(FakeEventRepository()).get_active_regions(
        datetime(2026, 9, 7, tzinfo=timezone.utc),
        window_hours=24,
        goes_classes="M,X",
    )

    assert [region.region_id for region in response.regions] == ["4525", "4526"]
    assert response.regions[0].event_position == "S22E79( 4525 )"
    assert [event["event_id"] for event in response.regions[0].events] == ["event-1", "event-2"]


def test_list_events_builds_typed_date_and_escaped_class_filters():
    class Repository:
        filters = None

        def find_many(self, filters):
            self.filters = filters
            return [{"_id": "internal", "event_id": "event-1", "event_GOES": "M1.0"}]

    repository = Repository()
    result = EventsService(repository).list_events("2026-09-07", "2026-09-07", "M+")

    assert result == [{"event_id": "event-1", "event_GOES": "M1.0"}]
    assert repository.filters["event_start_at"]["$gte"] == datetime(2026, 9, 7, tzinfo=timezone.utc)
    assert repository.filters["event_start_at"]["$lt"] == datetime(2026, 9, 8, tzinfo=timezone.utc)
    assert repository.filters["event_GOES"]["$regex"] == r"^M\+"


def test_active_regions_rejects_invalid_goes_classes():
    with pytest.raises(Exception) as error:
        EventsService(FakeEventRepository()).get_active_regions(
            datetime(2026, 9, 7, tzinfo=timezone.utc), 24, "M,(.*)"
        )

    assert error.value.status_code == 422


def test_active_regions_endpoint_has_stable_response_types(monkeypatch):
    monkeypatch.setattr(events, "EventsService", lambda: EventsService(FakeEventRepository()))
    api = FastAPI()
    api.include_router(events.router)

    response = TestClient(api).get(
        "/active-regions",
        params={"prediction_timestamp": "2026-09-07T00:00:00Z", "window_hours": 24},
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["prediction_timestamp"], str)
    assert isinstance(body["window_end"], str)
    assert isinstance(body["window_hours"], int)
    assert isinstance(body["goes_classes"], list)
    assert isinstance(body["regions"], list)
    assert isinstance(body["regions"][0]["region_id"], str)
    assert isinstance(body["regions"][0]["events"], list)


def test_event_detail_endpoint_returns_404(monkeypatch):
    monkeypatch.setattr(events, "EventsService", lambda: type("Service", (), {"get_event": lambda self, _id: None})())
    api = FastAPI()
    api.include_router(events.router)

    response = TestClient(api).get("/events/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
