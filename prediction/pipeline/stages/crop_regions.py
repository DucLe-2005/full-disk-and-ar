from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def load_full_disk_grayscale_from_image(image_path: str | Path) -> np.ndarray:
    image_path = Path(image_path)
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is not None:
        return image.astype(np.uint8)

    pil_image = Image.open(image_path).convert("L")
    return np.array(pil_image, dtype=np.uint8)


def clip_crop_box_xyxy(
    box: tuple[int, int, int, int], image_size: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Clip half-open crop coordinates to the source image."""
    width, height = image_size
    x1, y1, x2, y2 = box
    return (
        max(0, min(width, int(x1))),
        max(0, min(height, int(y1))),
        max(0, min(width, int(x2))),
        max(0, min(height, int(y2))),
    )


def crop_and_resize_active_region(
    full_disk_grayscale: np.ndarray,
    bbox_original_xyxy: tuple[int, int, int, int],
    output_path: str | Path | None = None,
    resize_to: tuple[int, int] = (512, 512),
) -> dict:
    height, width = full_disk_grayscale.shape
    x1, y1, x2, y2 = clip_crop_box_xyxy(bbox_original_xyxy, (width, height))

    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid bounding box after clipping: {(x1, y1, x2, y2)}")

    crop_array = full_disk_grayscale[y1:y2, x1:x2]
    crop_image = Image.fromarray(crop_array, mode="L")
    resized_image = crop_image.resize(resize_to, Image.Resampling.BILINEAR)

    saved_path = None
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        resized_image.save(output_path, quality=95)
        saved_path = str(output_path)

    return {
        "bbox_original_xyxy": (x1, y1, x2, y2),
        "crop_size_wh": crop_image.size,
        "resized_size_wh": resized_image.size,
        "image": resized_image,
        "saved_path": saved_path,
    }


def crop_square_active_region_with_padding(
    full_disk_grayscale: np.ndarray,
    crop_box_original_xyxy: tuple[int, int, int, int],
    output_path: str | Path | None = None,
    resize_to: tuple[int, int] = (512, 512),
) -> dict:
    height, width = full_disk_grayscale.shape
    x1, y1, x2, y2 = [int(v) for v in crop_box_original_xyxy]

    pad_left = max(0, -x1)
    pad_top = max(0, -y1)
    pad_right = max(0, x2 - width)
    pad_bottom = max(0, y2 - height)

    x1_clamped, y1_clamped, x2_clamped, y2_clamped = clip_crop_box_xyxy(
        (x1, y1, x2, y2), (width, height)
    )

    if x2_clamped <= x1_clamped or y2_clamped <= y1_clamped:
        raise ValueError(f"Invalid square crop after clipping: {(x1, y1, x2, y2)}")

    crop_array = full_disk_grayscale[y1_clamped:y2_clamped, x1_clamped:x2_clamped]
    if any(v > 0 for v in (pad_left, pad_top, pad_right, pad_bottom)):
        crop_array = cv2.copyMakeBorder(
            crop_array,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            borderType=cv2.BORDER_CONSTANT,
            value=0,
        )

    crop_image = Image.fromarray(crop_array, mode="L")
    resized_image = crop_image.resize(resize_to, Image.Resampling.BILINEAR)

    saved_path = None
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        resized_image.save(output_path, quality=95)
        saved_path = str(output_path)

    return {
        "crop_box_original_xyxy": (x1, y1, x2, y2),
        "crop_box_clipped_original_xyxy": (x1_clamped, y1_clamped, x2_clamped, y2_clamped),
        "crop_padding_ltrb": (pad_left, pad_top, pad_right, pad_bottom),
        "crop_size_wh": crop_image.size,
        "resized_size_wh": resized_image.size,
        "image": resized_image,
        "saved_path": saved_path,
    }


def crop_proposed_active_regions_from_image(
    image_path: str | Path,
    regions: list[dict],
    output_dir: str | Path | None,
    resize_to: tuple[int, int] = (512, 512),
) -> list[dict]:
    image_path = Path(image_path)
    output_dir = Path(output_dir) if output_dir is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    full_disk_grayscale = load_full_disk_grayscale_from_image(image_path)

    crop_results = []
    for index, region in enumerate(regions, start=1):
        output_path = (
            output_dir / f"{image_path.stem}.region_{index:02d}.jpg"
            if output_dir is not None
            else None
        )
        if "crop_box_original_xyxy" in region:
            crop_result = crop_square_active_region_with_padding(
                full_disk_grayscale=full_disk_grayscale,
                crop_box_original_xyxy=region["crop_box_original_xyxy"],
                output_path=output_path,
                resize_to=resize_to,
            )
        else:
            crop_result = crop_and_resize_active_region(
                full_disk_grayscale=full_disk_grayscale,
                bbox_original_xyxy=region["bbox_original_xyxy"],
                output_path=output_path,
                resize_to=resize_to,
            )
        crop_results.append({
            "region_index": index,
            **region,
            **crop_result,
        })

    return crop_results
