from datetime import datetime, timezone
from io import BytesIO
import json
from urllib.parse import parse_qs, urlparse

from PIL import Image

from app.services import solar_event_overlay
from app.services.solar_event_overlay import fetch_actual_flare_regions, render_actual_flare_overlay


def blank_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (512, 512), "black").save(output, format="PNG")
    return output.getvalue()


def test_fetches_m_x_regions_in_centered_two_hour_window(monkeypatch):
    requested_urls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"regions": [{"region_id": "4525"}]}).encode("utf-8")

    def fake_urlopen(url, timeout):
        requested_urls.append((url, timeout))
        return Response()

    monkeypatch.setattr(solar_event_overlay, "urlopen", fake_urlopen)

    regions, status = fetch_actual_flare_regions(
        "http://solar-events-service:8001/",
        datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc),
    )

    query = parse_qs(urlparse(requested_urls[0][0]).query)
    assert query == {
        "prediction_timestamp": ["2026-09-07T11:30:00+00:00"],
        "window_hours": ["2"],
        "goes_classes": ["M,X"],
    }
    assert requested_urls[0][1] == 3.0
    assert regions == [{"region_id": "4525"}]
    assert status == "available"


def test_overlay_uses_stored_pixel_coordinates_not_event_position():
    overlay = render_actual_flare_overlay(
        blank_image(),
        [
            {
                "region_id": "4525",
                "event_position": "not-a-heliographic-position",
                "pix_x": 100.4,
                "pix_y": 120.6,
            }
        ],
    )

    with Image.open(BytesIO(overlay)) as image:
        assert image.getpixel((100, 121)) == (230, 45, 45)


def test_overlay_skips_regions_without_stored_pixel_coordinates():
    overlay = render_actual_flare_overlay(
        blank_image(),
        [{"region_id": "4525", "event_position": "S22E79( 4525 )"}],
    )

    with Image.open(BytesIO(overlay)) as image:
        assert image.getbbox() is None
