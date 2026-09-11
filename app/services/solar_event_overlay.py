"""Fetch and render actual flare locations for one prediction window."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
import logging
import math
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont


logger = logging.getLogger(__name__)

IMAGE_SIZE = 512
CDELT = 0.600000023842
HPCCENTER = 4096.0 / 2.0
DOWNSAMPLE_FACTOR = 8.0
RSUN_METERS = 696000000.0
DSUN_METERS = 149597870691.0
POSITION_PATTERN = re.compile(r"^\s*([NS])(\d{1,2})([EW])(\d{1,2})")
LABEL_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def hgs_to_pixel(longitude_deg: float, latitude_deg: float) -> tuple[int, int]:
    """Convert HGS coordinates to the 512px HMI coordinate system.

    This is the supplied HGS -> HCC -> HPC converter logic, kept here so the
    API image overlay does not depend on the offline evaluation package.
    """
    longitude = math.radians(longitude_deg)
    latitude = math.radians(latitude_deg)
    hcc_x = RSUN_METERS * math.cos(latitude) * math.sin(longitude)
    hcc_y = RSUN_METERS * math.sin(latitude)
    z_squared = RSUN_METERS**2 - hcc_x**2 - hcc_y**2
    z = math.sqrt(z_squared) if z_squared >= 0 else 0.0
    zeta = DSUN_METERS - z
    distance = math.sqrt(hcc_x**2 + hcc_y**2 + zeta**2)
    hpc_x = math.degrees(math.atan2(hcc_x, zeta)) * 3600
    hpc_y = math.degrees(math.asin(hcc_y / distance)) * 3600
    return (
        int((HPCCENTER + hpc_x / CDELT) / DOWNSAMPLE_FACTOR),
        int((HPCCENTER - hpc_y / CDELT) / DOWNSAMPLE_FACTOR),
    )


def position_to_pixel(position: str) -> tuple[int, int] | None:
    """Parse LMSAL locations such as S22E79 or S22E79( 4405 )."""
    match = POSITION_PATTERN.match(position or "")
    if match is None:
        return None
    latitude = float(match.group(2)) * (-1 if match.group(1) == "S" else 1)
    longitude = float(match.group(4)) * (-1 if match.group(3) == "E" else 1)
    return hgs_to_pixel(longitude, latitude)


def fetch_actual_flare_regions(
    service_url: str,
    prediction_timestamp: datetime,
    timeout_seconds: float = 3.0,
) -> tuple[list[dict[str, Any]], str]:
    """Retrieve M/X flare regions without failing the prediction detail view."""
    timestamp = prediction_timestamp.isoformat()
    query = urlencode({"prediction_timestamp": timestamp, "window_hours": 24, "goes_classes": "M,X"})
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
    scale_x = image.width / IMAGE_SIZE
    scale_y = image.height / IMAGE_SIZE
    scale = min(scale_x, scale_y)
    font_size = max(12, round(14 * scale))
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
        point = position_to_pixel(str(region.get("event_position", "")))
        if point is None:
            continue
        rendered_region_ids.add(region_id)
        x, y = round(point[0] * scale_x), round(point[1] * scale_y)
        if not (0 <= x < image.width and 0 <= y < image.height):
            continue
        radius = max(6, round(7 * scale))
        outline_width = max(1, round(2 * scale))
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
