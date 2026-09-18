"""Fetch and render actual flare locations for one prediction window."""

from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
import json
import logging
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont


logger = logging.getLogger(__name__)

LABEL_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def fetch_actual_flare_regions(
    service_url: str,
    prediction_timestamp: datetime,
    timeout_seconds: float = 3.0,
) -> tuple[list[dict[str, Any]], str]:
    """Retrieve M/X flare regions within one hour of the prediction timestamp."""
    window_start = prediction_timestamp - timedelta(hours=1)
    query = urlencode(
        {
            "prediction_timestamp": window_start.isoformat(),
            "window_hours": 2,
            "goes_classes": "M,X",
        }
    )
    url = f"{service_url.rstrip('/')}/active-regions?{query}"
    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310: configured service URL
            payload = json.loads(response.read().decode("utf-8"))
        regions = payload.get("regions", [])
        if not isinstance(regions, list):
            raise ValueError("Solar-events response has an invalid regions field")
        return regions, "available" if regions else "no_events"
    except Exception as error:  # The event catalog is supplemental to predictions.
        logger.warning("Could not fetch actual flare regions from %s: %s", service_url, error)
        return [], "unavailable"


def render_actual_flare_overlay(final_hulls_image: bytes, regions: list[dict[str, Any]]) -> bytes:
    """Draw actual flare locations in red over a final-candidate-regions image."""
    with Image.open(BytesIO(final_hulls_image)) as source:
        image = source.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_size = 14
    try:
        label_font = ImageFont.truetype(LABEL_FONT_PATH, font_size)
    except OSError:
        # Keep rendering usable for local test environments; the API image
        # installs DejaVu so production annotations remain anti-aliased.
        label_font = ImageFont.load_default(size=font_size)
    rendered_region_ids: set[str] = set()
    for region in regions:
        region_id = str(region.get("region_id", "")).strip()
        if region_id in rendered_region_ids:
            continue
        try:
            x = round(float(region["pix_x"]))
            y = round(float(region["pix_y"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not (0 <= x < image.width and 0 <= y < image.height):
            continue
        rendered_region_ids.add(region_id)
        radius = 7
        outline_width = 2
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(230, 45, 45),
            outline=(255, 255, 255),
            width=outline_width,
        )

        label = region_id or "actual"
        text_bounds = draw.textbbox((0, 0), label, font=label_font, stroke_width=1)
        text_width = text_bounds[2] - text_bounds[0]
        text_height = text_bounds[3] - text_bounds[1]
        label_x = min(max(2, x + radius + 3), image.width - text_width - 2)
        label_y = max(2, min(y - text_height // 2, image.height - text_height - 2))
        draw.text(
            (label_x, label_y - text_bounds[1]),
            label,
            font=label_font,
            fill=(255, 96, 96),
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
