from __future__ import annotations

import cv2 as cv
import numpy as np


MIN_OVERLAPPING_METHODS = 3


def _polygon_mask(
    polygon: np.ndarray,
    image_shape: tuple[int, int],
) -> np.ndarray:
    mask = np.zeros(image_shape, dtype=np.uint8)
    polygon = np.asarray(polygon, dtype=np.int32).reshape(-1, 2)
    if len(polygon) >= 3:
        cv.fillPoly(mask, [polygon], 1)
    return mask


def fuse_overlapping_regions(
    bounded_maps: dict[str, np.ndarray],
    polygons_by_method: dict[str, list[np.ndarray]],
    min_methods: int = MIN_OVERLAPPING_METHODS,
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Keep only pixels covered by bounding regions from all required maps.

    Each method's polygons are first combined into one binary mask. The fused
    mask is their spatial intersection: a pixel survives only when it is
    covered by at least ``min_methods`` method masks. Returned polygons trace
    the connected components of that shared area, rather than the union of the
    original bounding regions.
    """
    if min_methods < 2:
        raise ValueError("min_methods must be at least 2")
    if not bounded_maps:
        raise ValueError("bounded_maps must not be empty")

    map_shapes = {np.asarray(score_map).shape for score_map in bounded_maps.values()}
    if len(map_shapes) != 1:
        raise ValueError("All bounded maps must have the same shape")
    image_shape = map_shapes.pop()
    if len(image_shape) != 2:
        raise ValueError(f"Expected 2D bounded maps, got shape {image_shape}")

    method_masks = {}
    for method_name in bounded_maps:
        method_mask = np.zeros(image_shape, dtype=np.uint8)
        for polygon in polygons_by_method.get(method_name, []):
            mask = _polygon_mask(polygon, image_shape)
            method_mask = np.maximum(method_mask, mask)
        method_masks[method_name] = method_mask

    score_sum = np.zeros(image_shape, dtype=np.float32)
    coverage_count = np.zeros(image_shape, dtype=np.float32)
    for method_name, bounded_map in bounded_maps.items():
        method_mask = method_masks[method_name].astype(np.float32)
        score_sum += np.asarray(bounded_map, dtype=np.float32)
        coverage_count += method_mask

    fused_mask = (coverage_count >= min_methods).astype(np.uint8)
    fused_map = np.divide(
        score_sum,
        coverage_count,
        out=np.zeros_like(score_sum),
        where=fused_mask > 0,
    )
    fused_map *= fused_mask.astype(np.float32)

    contours, _ = cv.findContours(
        fused_mask,
        cv.RETR_EXTERNAL,
        cv.CHAIN_APPROX_SIMPLE,
    )
    intersection_polygons = [
        contour.reshape(-1, 2)
        for contour in contours
        if len(contour) >= 3
    ]
    return fused_map, intersection_polygons


__all__ = ["MIN_OVERLAPPING_METHODS", "fuse_overlapping_regions"]
