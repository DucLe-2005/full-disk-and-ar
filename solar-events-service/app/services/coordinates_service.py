"""Map heliographic flare positions onto the 512px HMI image plane."""

import math
import re
from typing import Optional

from pymongo import UpdateOne

from app.repositories.event_repository import EventRepository


CDELT = 0.600000023842
HPCCENTER = 4096.0 / 2.0
RSUN_METERS = 696000000.0
DSUN_METERS = 149597870691.0
POSITION_PATTERN = re.compile(r"^\s*([NS])(\d{1,2})([EW])(\d{1,2})")


class CoordinatesService:
    def __init__(self, repository: Optional[EventRepository] = None) -> None:
        """Use an injected event repository or the configured MongoDB repository."""
        self.repository = repository or EventRepository()

    def add_pixel_coordinates(self) -> None:
        """Calculate and persist 512px pixel coordinates for positioned events."""
        operations = []
        for event in self.repository.list_with_positions():
            point = self.position_to_pixel(event.get("event_position", ""))
            if point is None:
                continue
            operations.append(
                UpdateOne(
                    {"_id": event["_id"]},
                    {"$set": {"pix_x": point[0], "pix_y": point[1]}},
                )
            )
        self.repository.bulk_update(operations)

    @staticmethod
    def position_to_pixel(position: str) -> Optional[tuple[float, float]]:
        """Parse an LMSAL HGS position and project it onto the 512px image plane.

        East and south coordinates are converted to negative longitude and
        latitude respectively. Any parenthesized NOAA number is ignored.
        """
        match = POSITION_PATTERN.match(position)
        if match is None:
            return None
        latitude = float(match.group(2)) * (-1 if match.group(1) == "S" else 1)
        longitude = float(match.group(4)) * (-1 if match.group(3) == "E" else 1)
        return CoordinatesService.hgs_to_pixel(longitude, latitude)

    @staticmethod
    def hgs_to_pixel(longitude_deg: float, latitude_deg: float) -> tuple[float, float]:
        """Convert HGS degrees to pixels using the fixed B0=0, L0=0 projection."""
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
        return (HPCCENTER + hpc_x / CDELT) / 8.0, (HPCCENTER - hpc_y / CDELT) / 8.0
