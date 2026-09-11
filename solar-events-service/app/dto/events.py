"""Pydantic DTOs for the public events API."""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ActualRegionDto(BaseModel):
    region_id: str
    event_position: str
    pix_x: Optional[float] = None
    pix_y: Optional[float] = None
    events: List[dict[str, Any]] = Field(default_factory=list)


class ActiveRegionsResponseDto(BaseModel):
    prediction_timestamp: datetime
    window_end: datetime
    window_hours: int
    goes_classes: List[str]
    regions: List[ActualRegionDto] = Field(default_factory=list)


class ScrapeStartedDto(BaseModel):
    status: str = "started"
    message: str = "scraper running in background"
