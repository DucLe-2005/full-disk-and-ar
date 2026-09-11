from io import BytesIO

from PIL import Image

from app.services.solar_event_overlay import render_actual_flare_overlay


def blank_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (512, 512), "black").save(output, format="PNG")
    return output.getvalue()


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

