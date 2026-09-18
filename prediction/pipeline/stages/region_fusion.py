from __future__ import annotations

import cv2 as cv
import numpy as np


MIN_OVERLAPPING_METHODS = 2


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
    """Fuse cross-method polygon unions and discard single-method regions.

    Polygons are connected only when their filled areas overlap and they come
    from different attribution methods. A connected group is retained when it
    contains regions from at least ``min_methods`` methods. The score within
    the retained union is the mean of the bounded attribution maps that cover
    each pixel; no pixel-wise consensus is required for retaining a region.
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

    nodes = []
    method_masks = {}
    for method_name in bounded_maps:
        method_mask = np.zeros(image_shape, dtype=np.uint8)
        for polygon in polygons_by_method.get(method_name, []):
            mask = _polygon_mask(polygon, image_shape)
            if not np.any(mask):
                continue
            method_mask = np.maximum(method_mask, mask)
            nodes.append({
                "method": method_name,
                "mask": mask,
            })
        method_masks[method_name] = method_mask

    if not nodes:
        return np.zeros(image_shape, dtype=np.float32), []

    parents = list(range(len(nodes)))

    def find(node_index: int) -> int:
        while parents[node_index] != node_index:
            parents[node_index] = parents[parents[node_index]]
            node_index = parents[node_index]
        return node_index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root != right_root:
            parents[right_root] = left_root

    for left_index, left in enumerate(nodes):
        for right_index in range(left_index + 1, len(nodes)):
            right = nodes[right_index]
            if left["method"] == right["method"]:
                continue
            if np.any(left["mask"] & right["mask"]): 
                # union if 2 masks overlap, the bitwise AND check for that
                union(left_index, right_index)

    groups = {}
    for node_index in range(len(nodes)):
        groups.setdefault(find(node_index), []).append(node_index)

    fused_mask = np.zeros(image_shape, dtype=np.uint8)
    merged_polygons = []
    for node_indices in groups.values():
        methods = {nodes[node_index]["method"] for node_index in node_indices}
        if len(methods) < min_methods:
            continue

        group_mask = np.zeros(image_shape, dtype=np.uint8)
        for node_index in node_indices:
            group_mask = np.maximum(group_mask, nodes[node_index]["mask"])
        fused_mask = np.maximum(fused_mask, group_mask)

        contours, _ = cv.findContours(
            group_mask,
            cv.RETR_EXTERNAL,
            cv.CHAIN_APPROX_SIMPLE,
        )
        merged_polygons.extend(
            contour.reshape(-1, 2)
            for contour in contours
            if len(contour) >= 3
        )

    score_sum = np.zeros(image_shape, dtype=np.float32)
    coverage_count = np.zeros(image_shape, dtype=np.float32)
    for method_name, bounded_map in bounded_maps.items():
        method_mask = method_masks[method_name].astype(np.float32)
        score_sum += np.asarray(bounded_map, dtype=np.float32) * method_mask
        coverage_count += method_mask

    fused_map = np.divide(
        score_sum,
        coverage_count,
        out=np.zeros_like(score_sum),
        where=coverage_count > 0,
    )
    fused_map *= fused_mask.astype(np.float32)
    return fused_map, merged_polygons


__all__ = ["MIN_OVERLAPPING_METHODS", "fuse_overlapping_regions"]
