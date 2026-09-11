from pydantic import BaseModel, Field
from typing import Any, List, Optional


class ActiveRegionResponse(BaseModel):
    rank: int
    probability: float
    heatmap_score: Optional[float] = None
    image_path: Optional[str] = None
    bbox_original: Optional[list[int]] = None
    bbox_resized: Optional[list[int]] = None
    center_original: Optional[list[int]] = None
    center_resized: Optional[list[int]] = None
    polygon_original: List[list[int]] = Field(default_factory=list)
    polygon_resized: List[list[int]] = Field(default_factory=list)
    crop_box_original: Optional[list[int]] = None
    crop_box_clipped_original: Optional[list[int]] = None
    crop_padding_ltrb: Optional[list[int]] = None
    proposal_score: Optional[float] = None
    consensus_score: Optional[float] = None
    area_weighted_score: Optional[float] = None
    area_resized: Optional[float] = None


class HeatmapResponse(BaseModel):
    method_name: str
    image_path: str


class PredictionResponse(BaseModel):
    prediction_id: str
    requested_at: str
    timestamp: str
    global_flare_probability: float
    localized_probabilities: List[float] = Field(default_factory=list)
    predicted_class: str
    jp2_image_url: Optional[str] = None
    full_disk_image_url: Optional[str] = None
    heatmap_url: Optional[str] = None
    guided_gradcam_url: Optional[str] = None
    integrated_gradients_url: Optional[str] = None
    deepshap_url: Optional[str] = None
    consensus_url: Optional[str] = None
    final_hulls_url: Optional[str] = None
    actual_flare_regions: List[dict[str, Any]] = Field(default_factory=list)
    actual_events_status: Optional[str] = None
    actual_flare_overlay_url: Optional[str] = None
    active_regions: List[ActiveRegionResponse] = Field(default_factory=list)
    heatmaps: List[HeatmapResponse] = Field(default_factory=list)
    raw_active_regions: List[dict[str, Any]] = Field(default_factory=list)


class PredictionHistoryPage(BaseModel):
    items: List[PredictionResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
