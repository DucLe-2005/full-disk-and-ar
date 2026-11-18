from __future__ import annotations

import datetime
import logging
from pathlib import Path
import re

import cv2
import requests

from prediction.pipeline import MagnetogramNotFoundError

logger = logging.getLogger(__name__)
JP2_URL = "https://api.helioviewer.org/v2/getJP2Image/"
MAX_IMAGE_AGE = datetime.timedelta(minutes=12)
JPIP_TIMESTAMP = re.compile(r"^(\d{4}_\d{2}_\d{2}__\d{2}_\d{2}_\d{2})(?:_(\d+))?__")


def _closest_observation(target: datetime.datetime, source_id: int) -> datetime.datetime:
    response = requests.get(
        JP2_URL,
        params={"date": f"{target.isoformat()}Z", "sourceId": source_id, "jpip": "true"},
        timeout=60,
    )
    response.raise_for_status()
    match = JPIP_TIMESTAMP.match(response.content.decode().strip().rsplit("/", 1)[-1])
    if match is None:
        raise RuntimeError(f"Invalid Helioviewer JPIP response for {target.isoformat()}Z")
    timestamp, fraction = match.groups()
    observed_at = datetime.datetime.strptime(timestamp, "%Y_%m_%d__%H_%M_%S")
    return observed_at.replace(microsecond=int((fraction or "").ljust(6, "0")[:6]))


def _download_image(observed_at: datetime.datetime, source_id: int, file_path: Path) -> None:
    response = requests.get(
        JP2_URL,
        params={"date": f"{observed_at.isoformat()}Z", "sourceId": source_id},
        timeout=120,
    )
    response.raise_for_status()
    file_path.write_bytes(response.content)


def download_forecast_magnetogram(
    slot: datetime.datetime, destination: Path, source_id: int = 19
) -> tuple[Path, datetime.datetime]:
    """Download an HMI observation at or within 12 minutes before the UTC slot."""
    observed_at = _closest_observation(slot, source_id)
    if observed_at > slot:
        # At the midpoint of the allowed window, any eligible observation
        # is at least as close as an observation outside that window.
        observed_at = _closest_observation(slot - MAX_IMAGE_AGE / 2, source_id)
    if not slot - MAX_IMAGE_AGE <= observed_at <= slot:
        raise MagnetogramNotFoundError(
            f"No magnetogram in the 12 minutes through {slot.isoformat()}Z"
        )
    file_path = destination / f"HMI.m{slot:%Y.%m.%d_%H.%M.%S}.jp2"
    _download_image(observed_at, source_id, file_path)
    return file_path, observed_at


def _prediction_exists_for_requested_at(requested_at: datetime.datetime) -> bool:
    from app.core.database import SessionLocal
    from app.api.repositories.prediction_repository import PredictionRepository

    db = SessionLocal()
    try:
        repo = PredictionRepository(db)
        return repo.exists_for_requested_at(requested_at)
    finally:
        db.close()


def download_from_helioviewer(
    date: str | datetime.datetime,
    basedir: str | Path = "data/",
    include_time_components: bool = False,
    check_existing_prediction: bool = True,
    source_id: int = 19,
) -> Path:
    """
    Download a single 4k magnetogram JP2 from Helioviewer for the specified date.

    Files are saved as:
    basedir/year/month/day/jp2/HMI.mYYYY.MM.DD_HH.MM.SS.jp2

    If include_time_components=True, files are saved as:
    basedir/year/month/day/hour/minute/second/jp2/HMI.mYYYY.MM.DD_HH.MM.SS.jp2
    """

    if isinstance(date, datetime.datetime):
        dt = date
    else:
        normalized_date = str(date).strip().replace("T", " ").replace("Z", "")
        dt = datetime.datetime.strptime(normalized_date, "%Y-%m-%d %H:%M:%S")

    if check_existing_prediction and _prediction_exists_for_requested_at(dt):
        requested_at = dt.replace(microsecond=0)
        raise FileExistsError(
            f"A prediction already exists for requested_at "
            f"{requested_at.strftime('%Y-%m-%dT%H:%M:%S')}."
        )

    basedir = Path(basedir)
    date_dir = basedir / f"{dt.year}" / f"{dt.month:02d}" / f"{dt.day:02d}"
    if include_time_components:
        date_dir = date_dir / f"{dt.hour:02d}" / f"{dt.minute:02d}" / f"{dt.second:02d}"
    target_dir = date_dir / "jp2"
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f"HMI.m{dt.year}.{dt.month:02d}.{dt.day:02d}_"
        f"{dt.hour:02d}.{dt.minute:02d}.{dt.second:02d}.jp2"
    )
    file_path = target_dir / filename
    final_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    request_string = (
        "https://api.helioviewer.org/v2/getJP2Image/"
        f"?date={final_date}&sourceId={source_id}&jpip=true"
    )
    response = requests.get(request_string, timeout=60)
    response.raise_for_status()

    returned_url = response.content.decode("utf-8").strip()
    if not returned_url:
        raise RuntimeError(f"Helioviewer returned an empty JPIP response for {final_date}")

    url_temp = returned_url.rsplit("/", 1)[-1]
    date_received = url_temp.rsplit("__", 1)[0][:-4]
    received = datetime.datetime.strptime(date_received, "%Y_%m_%d__%H_%M_%S")

    if abs(received - dt) > datetime.timedelta(minutes=12):
        raise MagnetogramNotFoundError(
            f"No magnetogram found within 12 minutes of {final_date}. "
            f"Closest available image is {received.strftime('%Y-%m-%dT%H:%M:%SZ')}."
        )

    if file_path.exists():
        logger.info("Using existing Helioviewer JP2: %s", file_path)
        return file_path

    request_uri = (
        "https://api.helioviewer.org/v2/getJP2Image/"
        f"?date={final_date}&sourceId={source_id}"
    )
    hmidata = requests.get(request_uri, timeout=120)
    hmidata.raise_for_status()
    file_path.write_bytes(hmidata.content)
    logger.info("Downloaded Helioviewer JP2: %s", file_path)
    return file_path

def jp2_to_jpg_conversion(
    jp2_path: str | Path,
    destination: str | Path = "data/hmi_jpgs/",
    resize: bool = False,
    width: int = 512,
    height: int = 512,
    jpg_dir: str | Path | None = None,
):
    """
    Convert one JP2 to JPG and return the output path.

    If resize=True, the output JPG is resized to the provided width and height.
    If jpg_dir is provided, the JPG is written directly into that directory.
    """
    jp2_path = Path(jp2_path)
    target_dir = Path(jpg_dir) if jpg_dir is not None else Path(destination)
    target_dir.mkdir(parents=True, exist_ok=True)
    jpg_path = target_dir / f"{jp2_path.stem}.jpg"

    image = cv2.imread(str(jp2_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f"Failed to read JP2 image: {jp2_path}")
    if resize:
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(str(jpg_path), image):
        raise RuntimeError(f"Failed to write JPG image: {jpg_path}")
    return jpg_path
