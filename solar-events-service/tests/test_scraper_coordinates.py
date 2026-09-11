from app.services.coordinates_service import CoordinatesService
from app.services.scraper_service import LmsalScraperService
from app.models.event import to_event_document


class FakeResponse:
    text = """
        <html><body><table><tr>
          <td>gev_20260910_1200</td>
          <td>2026/09/10 12:00:00</td>
          <td>12:20:00</td>
          <td>12:10:00</td>
          <td>M1.2</td>
          <td>S22E79( 4525 )</td>
        </tr></table></body></html>
    """

    def raise_for_status(self):
        return None


def test_scraped_events_include_deterministic_pixel_coordinates(monkeypatch):
    monkeypatch.setattr(
        "app.services.scraper_service.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    first = LmsalScraperService._events_from_snapshot("snapshot-url")[0]
    second = LmsalScraperService._events_from_snapshot("snapshot-url")[0]
    expected = CoordinatesService.position_to_pixel("S22E79( 4525 )")

    assert expected is not None
    assert (first["pix_x"], first["pix_y"]) == expected
    assert (second["pix_x"], second["pix_y"]) == expected


def test_event_stop_after_midnight_is_normalized_to_the_next_day():
    document = to_event_document(
        {
            "event_id": "gev_20260201_2344",
            "event_start": "2026/02/01 23:44:00",
            "event_peak": "23:57:00",
            "event_stop": "00:04:00",
            "event_GOES": "X8.1",
        }
    )

    assert document["event_stop_at"].isoformat() == "2026-02-02T00:04:00+00:00"
