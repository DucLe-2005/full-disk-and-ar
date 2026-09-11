from app.services.coordinates_service import CoordinatesService
from app.services.scraper_service import LmsalScraperService


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

