from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from prediction.pipeline.stages.crop_regions import crop_proposed_active_regions_from_image
from prediction.pipeline.stages.download import download_forecast_magnetogram, jp2_to_jpg_conversion
from prediction.pipeline.stages.ar_predict import predict_ar_models_for_regions
from prediction.pipeline.stages.region_proposal import PROPOSAL_IMAGE_SIZE, propose_active_regions
from prediction.pipeline.stages.full_disk_predict import predict_full_disk

logger = logging.getLogger(__name__)

DATA_ROOT = Path("data")
PREDICTION_THRESHOLD = 0.5
AR_MODEL_NAMES = ["mobilenet"]
AR_THRESHOLD = 0.5


def run_pipeline(
    date: str,
    *,
    stage: Callable[[str], AbstractContextManager] = lambda _name: nullcontext(),
    data_root: Path = DATA_ROOT,
) -> dict:
    logger.info("Starting solar flare pipeline for %s", date)
    if not date:
        raise ValueError("date is required")

    dt = datetime.datetime.strptime(
        date.strip().replace("T", " ").replace("Z", ""),
        "%Y-%m-%d %H:%M:%S",
    )
    artifact_base_dir = data_root / f"{dt.year}" / f"{dt.month:02d}" / f"{dt.day:02d}"
    jp2_dir = artifact_base_dir / "jp2"
    full_disk_dir = artifact_base_dir / "full_disk"
    heatmap_dir = artifact_base_dir / "heat_maps"
    active_regions_dir = artifact_base_dir / "active_regions"
    for artifact_dir in (jp2_dir, full_disk_dir, active_regions_dir):
        artifact_dir.mkdir(parents=True, exist_ok=True)

    with stage("magnetogram"):
        jp2_path, observed_at = download_forecast_magnetogram(dt, jp2_dir)
        jpg_path = jp2_to_jpg_conversion(
            jp2_path=jp2_path,
            destination=full_disk_dir,
            resize=False,
        )

    with stage("full_disk"):
        prediction_result = predict_full_disk(
            image_path=str(jpg_path),
            threshold=PREDICTION_THRESHOLD,
        )

    with stage("attribution"):
        region_result = propose_active_regions(
            image_path=str(jpg_path),
            heatmap_output_dir=heatmap_dir,
        )

    with stage("regions"):
        crop_results = crop_proposed_active_regions_from_image(
            image_path=jp2_path,
            regions=region_result["regions"],
            output_dir=active_regions_dir,
            resize_to=PROPOSAL_IMAGE_SIZE,
        )
        ar_region_results = predict_ar_models_for_regions(
            crop_results=crop_results,
            model_names=AR_MODEL_NAMES,
            threshold=AR_THRESHOLD,
        )
    logger.info(
        "Pipeline completed: class=%s flare_probability=%.4f proposed_regions=%d",
        prediction_result["pred_class"],
        prediction_result["p_flare"],
        len(region_result["regions"]),
    )

    artifact_dirs = {
        "jp2": str(jp2_dir),
        "full_disk": str(full_disk_dir),
        "heat_maps": str(heatmap_dir),
        "active_regions": str(active_regions_dir),
    }

    return {
        "jpg_path": str(jpg_path),
        "image_path": str(jp2_path),
        "prediction_datetime": dt.isoformat(),
        "observed_at": observed_at.isoformat(),
        "artifact_base_dir": str(artifact_base_dir),
        "artifact_dirs": artifact_dirs,
        "prediction": prediction_result,
        "active_regions": region_result,
        "ar_region_crops": ar_region_results,
    }
