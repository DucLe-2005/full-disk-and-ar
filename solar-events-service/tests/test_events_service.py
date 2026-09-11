from datetime import datetime, timezone

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
