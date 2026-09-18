from __future__ import annotations

from pathlib import Path

import cv2 as cv
import numpy as np
from PIL import Image
from sklearn.cluster import DBSCAN
from scipy.spatial import distance


from prediction.pipeline.stages.attribution import (
    generate_attribution_maps,
    normalize_map,
    save_binary_raw_map,
    save_raw_map_image,
    to_uint8_grayscale,
)
from prediction.pipeline.stages.region_fusion import (
    MIN_OVERLAPPING_METHODS,
    fuse_overlapping_regions,
)

PROPOSAL_IMAGE_SIZE = (512, 512)
CROP_SIZE_ORIGINAL = 512
CANNY_LOWER_THRESHOLD = 30
CANNY_UPPER_THRESHOLD = 50
DBSCAN_MIN_SAMPLES = 2
DBSCAN_EPS = 10.0
EAST_BUFFER = 10
WEST_BUFFER = 60
BINARY_THRESHOLD = 30
PROPOSAL_HEATMAP_METHOD = "consensus"
ATTRIBUTION_METHODS = (
    "guided_gradcam",
    "integrated_gradients",
    "deepshap",
)


def polygon_to_bbox_xyxy(poly: np.ndarray) -> tuple[int, int, int, int]:
    x_min = int(np.min(poly[:, 0]))
    x_max = int(np.max(poly[:, 0]))
    y_min = int(np.min(poly[:, 1]))
    y_max = int(np.max(poly[:, 1]))
    return x_min, y_min, x_max, y_max


def clip_box_xyxy(box, image_w, image_h):
    x1, y1, x2, y2 = box
    x1 = max(0, min(int(x1), image_w - 1))
    y1 = max(0, min(int(y1), image_h - 1))
    x2 = max(0, min(int(x2), image_w - 1))
    y2 = max(0, min(int(y2), image_h - 1))
    if x2 <= x1:
        x2 = min(image_w - 1, x1 + 1)
    if y2 <= y1:
        y2 = min(image_h - 1, y1 + 1)
    return x1, y1, x2, y2


def bbox_center_xy(bbox):
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return (cx, cy)


def crop_box_around_center_xyxy(
    center_xy: tuple[int, int],
    crop_size: int,
) -> tuple[int, int, int, int]:
    cx, cy = center_xy
    half = crop_size // 2
    x1 = cx - half
    y1 = cy - half
    return x1, y1, x1 + crop_size, y1 + crop_size


def resize_box_to_original(bbox_resized, resized_size, original_size):
    resized_w, resized_h = resized_size
    original_w, original_h = original_size

    x1, y1, x2, y2 = bbox_resized
    scale_x = original_w / resized_w
    scale_y = original_h / resized_h

    return clip_box_xyxy(
        (
            int(round(x1 * scale_x)),
            int(round(y1 * scale_y)),
            int(round(x2 * scale_x)),
            int(round(y2 * scale_y)),
        ),
        original_w,
        original_h,
    )


def score_polygon_from_map(score_map: np.ndarray, polygon: np.ndarray) -> float:
    h, w = score_map.shape
    mask = np.zeros((h, w), dtype=np.uint8)
    cv.fillPoly(mask, [polygon.astype(np.int32)], 1)
    vals = score_map[mask == 1]
    if len(vals) == 0:
        return 0.0
    return float(np.mean(vals))


def get_hulls(
    heatmap_u8: np.ndarray,
    lower_threshold: int = 30,
    upper_threshold: int = 50,
    min_samples: int = 2,
    eps: float = 10.0,
):
    edges = cv.Canny(heatmap_u8, lower_threshold, upper_threshold)
    points = np.argwhere(edges == 255)
    if len(points) == 0:
        return edges, []

    points = points[:, ::-1]
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(points)

    hulls = []
    for label in np.unique(labels):
        if label == -1:
            continue

        cluster_points = points[labels == label]
        if len(cluster_points) < 3:
            continue

        hull = cv.convexHull(cluster_points.astype(np.int32)).reshape(-1, 2)
        hulls.append(hull)

    return edges, hulls

def longest_radius_from_center(hull: np.ndarray) -> int:
    """
    Find the longest radius from the center of the hull
    :param hull: The hull to find the longest radius from the center
    :return: The longest radius
    """
    center = np.mean(hull, axis=0)
    max_dist = 0

    for p in hull:
        dist = distance.euclidean(p, center)
        max_dist = max(max_dist, dist)

    return int(max_dist)


def triangle_points(center, nw_angle, sw_angle, length):
    center = np.array(center)

    nw_angle_rad = -np.deg2rad(nw_angle)
    nw_point_side_1 = np.array([
        center[0] + length * np.cos(nw_angle_rad),
        center[1] - length * np.sin(nw_angle_rad),
    ]).astype(int)

    nw_point_side_2 = np.array([
        center[0] + length * np.cos(nw_angle_rad),
        center[1],
    ]).astype(int)

    sw_angle_rad = -np.deg2rad(sw_angle)
    sw_point_side_1 = np.array([
        center[0] + length * np.cos(sw_angle_rad),
        center[1] - length * np.sin(sw_angle_rad),
    ]).astype(int)

    sw_point_side_2 = np.array([
        center[0] + length * np.cos(sw_angle_rad),
        center[1],
    ]).astype(int)

    ellipse_rad = int(distance.euclidean(sw_point_side_1, sw_point_side_2))

    return (
        nw_point_side_1,
        nw_point_side_2,
        sw_point_side_1,
        sw_point_side_2,
        ellipse_rad,
    )


def tangent_line(center, point_side_1, radius, nw=True):
    center = np.array(center)
    point_side_1 = np.array(point_side_1)

    hypotenuse_length = np.linalg.norm(point_side_1 - center)

    if hypotenuse_length == 0:
        return tuple(center.astype(int))

    # Avoid invalid arcsin input
    ratio = min(radius / hypotenuse_length, 1.0)
    angle = np.arcsin(ratio)

    unit_vector = (point_side_1 - center) / hypotenuse_length

    if nw:
        rotation_matrix = np.array([
            [np.cos(3 * np.pi / 2 + angle), -np.sin(3 * np.pi / 2 + angle)],
            [np.sin(3 * np.pi / 2 + angle),  np.cos(3 * np.pi / 2 + angle)],
        ])
    else:
        rotation_matrix = np.array([
            [np.cos(np.pi / 2 - angle), -np.sin(np.pi / 2 - angle)],
            [np.sin(np.pi / 2 - angle),  np.cos(np.pi / 2 - angle)],
        ])

    rotated_vector = np.dot(rotation_matrix, unit_vector)
    point_C = center + rotated_vector * radius

    return tuple(point_C.astype(int))


def draw_bounding_region(
    polygons: list[np.ndarray],
    image_shape: tuple[int, int],
    nw_angle: float = -20,
    sw_angle: float = 20,
    east_buffer: int = 10,
    west_buffer: int = 60,
) -> np.ndarray:
    """
    Draw the bounding region of the activation points
    :param hulls: The hulls of the activation points
    :param nw_angle: The angle of the north-west side
    :param sw_angle: The angle of the south-west side
    :param east_buffer: The buffer of the east side
    :param west_buffer: The buffer of the west side
    :return: The image of the bounding region
    """
    h, w = image_shape
    img = np.zeros((h, w), dtype=np.uint8)

    # Draw convex hulls
    for hull in polygons:
        hull = np.asarray(hull, dtype=np.int32).reshape(-1, 2)

        if len(hull) < 3:
            continue

        # Find the center of the hull
        center = tuple(np.mean(hull, axis=0).astype(int))

        radius = longest_radius_from_center(hull) + east_buffer
        length = radius - east_buffer + west_buffer

        # Calculate the end point of the line
        (
            nw_point_side_1,
            nw_point_side_2,
            sw_point_side_1,
            sw_point_side_2,
            ellipse_rad,
        ) = triangle_points(center, nw_angle, sw_angle, length)

        nw_point_C = tangent_line(center, nw_point_side_1, radius, nw=True)
        sw_point_C = tangent_line(center, sw_point_side_1, radius, nw=False)

        # Draw the bounding polygon
        cv.circle(img, center, radius, 255, 1)
        
        # Draw the line from the center of the hull
        cv.ellipse(
            img,
            tuple(sw_point_side_2),
            (ellipse_rad, ellipse_rad),
            0,
            270,
            450,
            255,
            1,
        )
        
        # Draw the tangent line NW
        cv.line(img, nw_point_C, tuple(nw_point_side_1), 255, 1)
        
        # Draw the tangent line SW
        cv.line(img, sw_point_C, tuple(sw_point_side_1), 255, 1)

    return img


def bounding_hulls(
    img: np.ndarray,
    min_samples: int = 2,
    eps: float = 2,
):
    """
    Draw the bounding polygons around the activation points
    :param img: The image of the activation points
    :return: The hulls of the activation points
    """
    points = np.argwhere(img == 255)
    if len(points) == 0:
        return []

    points = points[:, ::-1] 
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(points)


    final_hulls = []
    for label in np.unique(labels):
        if label == -1:
            continue

        cluster_points = points[labels == label]
        if len(cluster_points) < 3:
            continue
        hull = cv.convexHull(cluster_points.astype(np.int32)).reshape(-1, 2)
        final_hulls.append(hull)

    return final_hulls


def bound_heatmap_regions(score_map: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """Mask a normalized heatmap to the bounding regions found on that map."""
    normalized_map = normalize_map(score_map)
    heatmap_u8 = to_uint8_grayscale(normalized_map)
    _, initial_hulls = get_hulls(
        heatmap_u8=heatmap_u8,
        lower_threshold=CANNY_LOWER_THRESHOLD,
        upper_threshold=CANNY_UPPER_THRESHOLD,
        min_samples=DBSCAN_MIN_SAMPLES,
        eps=DBSCAN_EPS,
    )
    bounding_mask = draw_bounding_region(
        polygons=initial_hulls,
        image_shape=heatmap_u8.shape,
        nw_angle=-20,
        sw_angle=20,
        east_buffer=EAST_BUFFER,
        west_buffer=WEST_BUFFER,
    )
    polygons = bounding_hulls(img=bounding_mask, min_samples=2, eps=2)

    filled_mask = np.zeros(heatmap_u8.shape, dtype=np.uint8)
    if polygons:
        cv.fillPoly(filled_mask, [poly.astype(np.int32) for poly in polygons], 1)
    return normalized_map * filled_mask.astype(np.float32), polygons


def save_bounded_heatmap_overlay(
    bounded_map: np.ndarray,
    polygons: list[np.ndarray],
    image_path: str | Path,
    output_dir: str | Path,
    method_name: str,
) -> Path:
    """Save one pre-fusion heatmap with its bounding regions drawn on top."""
    overlay = cv.applyColorMap(to_uint8_grayscale(bounded_map), cv.COLORMAP_INFERNO)
    for polygon in polygons:
        cv.polylines(
            overlay,
            [polygon.astype(np.int32)],
            isClosed=True,
            color=(0, 255, 255),
            thickness=2,
        )

    image_stem = Path(image_path).stem or "unknown_image"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    save_path = output_path / f"{image_stem}_{method_name}_bounded.png"
    Image.fromarray(cv.cvtColor(overlay, cv.COLOR_BGR2RGB)).save(save_path)
    return save_path


def draw_hulls(
    hulls,
    image_shape=(512, 512),
    draw_ids=True,
):
    """
    Draw final hull polygons.
    Works with hulls shaped like: [polygon1, polygon2, ...]
    """
    h, w = image_shape
    img = np.zeros((h, w), dtype=np.uint8)

    for hull_id, hull_points in enumerate(hulls, start=1):
        hull_points = np.asarray(hull_points, dtype=np.int32).reshape(-1, 2)

        if len(hull_points) < 3:
            continue

        cv.polylines(img, [hull_points], True, 255, 1)

        if draw_ids:
            center = tuple(np.mean(hull_points, axis=0).astype(int))
            cv.putText(
                img,
                str(hull_id),
                center,
                cv.FONT_HERSHEY_SIMPLEX,
                0.5,
                255,
                1,
                cv.LINE_AA,
            )

    return img


def build_polygon_regions(
    polygons: list[np.ndarray],
    score_map: np.ndarray,
) -> list[dict]:
    regions = []
    for poly in polygons:
        bbox = polygon_to_bbox_xyxy(poly)
        x1, y1, x2, y2 = bbox
        area = max(1, (x2 - x1) * (y2 - y1))
        mean_score = score_polygon_from_map(score_map, poly)
        regions.append({
            "polygon": poly,
            "score": mean_score,
            "mean_score": mean_score,
            "bbox_resized_xyxy": bbox,
            "area": area,
        })

    if not regions:
        return regions

    max_area = max(region["area"] for region in regions)
    max_area_log = np.log1p(max_area)
    for region in regions:
        area_factor = np.log1p(region["area"]) / max_area_log if max_area_log > 0 else 1.0
        ranking_score = region["mean_score"] * area_factor
        region["area_factor"] = float(area_factor)
        region["ranking_score"] = float(ranking_score)
        region["score"] = float(ranking_score)

    regions.sort(key=lambda region: region["ranking_score"], reverse=True)
    return regions


def save_region_proposal_overlay(
    heatmap_u8: np.ndarray,
    regions: list[dict],
    image_path,
    output_dir: str | Path = "data/heat_maps",
) -> Path:
    overlay = cv.cvtColor(heatmap_u8, cv.COLOR_GRAY2BGR)

    for region in regions:
        poly = np.array(region["polygon_resized_xy"], dtype=np.int32)
        bbox = tuple(region["bbox_resized_xyxy"])
        cv.polylines(overlay, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
        cv.rectangle(
            overlay,
            (bbox[0], bbox[1]),
            (bbox[2], bbox[3]),
            color=(255, 255, 255),
            thickness=1,
        )

    image_stem = Path(image_path).stem or "unknown_image"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    save_path = output_path / f"{image_stem}_final_region_proposal.png"
    Image.fromarray(cv.cvtColor(overlay, cv.COLOR_BGR2RGB)).save(save_path)
    return save_path


def save_heatmap_image(
    attr_map: np.ndarray,
    image_path: str | Path,
    output_dir: str | Path,
) -> Path:
    source_path = save_raw_map_image(
        attr_map=attr_map,
        image_path=image_path,
        output_dir=output_dir,
        name="heatmap",
    )
    image_stem = Path(image_path).stem or "unknown_image"
    target_path = Path(output_dir) / f"{image_stem}_heatmap.png"
    if Path(source_path) != target_path:
        Path(source_path).replace(target_path)
    return target_path


def save_final_hulls_image(
    final_hulls_image: np.ndarray,
    image_path: str | Path,
    output_dir: str | Path,
) -> Path:
    image_stem = Path(image_path).stem or "unknown_image"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    save_path = output_path / f"{image_stem}_final_hulls.png"
    if final_hulls_image.ndim == 2:
        Image.fromarray(final_hulls_image.astype(np.uint8), mode="L").save(save_path)
    else:
        Image.fromarray(cv.cvtColor(final_hulls_image.astype(np.uint8), cv.COLOR_BGR2RGB)).save(save_path)
    return save_path


def _build_region_outputs(
    polygon_regions: list[dict],
    original_size: tuple[int, int],
    resized_size_wh: tuple[int, int],
    crop_size_original: int,
) -> list[dict]:
    
    """
    polygon (512x512) -> bbox (512x512) -> scale -> polygon(4kx4k) -> bbox(4kx4k) -> center -> crop 512x512 around center
    """
    resized_w, resized_h = resized_size_wh
    original_w, original_h = original_size
    sx = original_w / resized_w
    sy = original_h / resized_h

    final_regions = []
    for idx, region in enumerate(polygon_regions, start=1):
        polygon_resized = region["polygon"]
        bbox_resized = clip_box_xyxy(
            region["bbox_resized_xyxy"],
            image_w=resized_w,
            image_h=resized_h,
        )
        bbox_original = resize_box_to_original(
            bbox_resized=bbox_resized,
            resized_size=resized_size_wh,
            original_size=original_size,
        )
        center_original = bbox_center_xy(bbox_original)
        polygon_original = np.stack([
            np.round(polygon_resized[:, 0] * sx).astype(int),
            np.round(polygon_resized[:, 1] * sy).astype(int),
        ], axis=1)

        final_regions.append({
            "region_rank": idx,
            "polygon_resized_xy": polygon_resized.tolist(),
            "bbox_resized_xyxy": bbox_resized,
            "center_resized_xy": bbox_center_xy(bbox_resized),
            "polygon_original_xy": polygon_original.tolist(),
            "bbox_original_xyxy": bbox_original,
            "center_original_xy": center_original,
            "crop_box_original_xyxy": crop_box_around_center_xyxy(
                center_original,
                crop_size=crop_size_original,
            ),
            "crop_size": crop_size_original,
            "proposal_score": region["ranking_score"],
            "ranking_score": region["ranking_score"],
            "consensus_score": region["mean_score"],
            "area_factor": region["area_factor"],
            "area_weighted_score": region["ranking_score"],
            "area": region["area"],
            "area_resized": region["area"],
        })

    return final_regions

def apply_full_disk_contour(
    original_hmi: np.ndarray,
    region_image: np.ndarray,
    threshold: int = 1,
    outline_thickness: int = 1,
) -> np.ndarray:
    """
    Apply the solar-disk mask detected from the original HMI image
    and draw its outline on the region-proposal image.
    """
    original = np.asarray(original_hmi).squeeze()
    regions = np.asarray(region_image).copy()

    if original.ndim != 2:
        raise ValueError(
            f"Expected a 2D original HMI image, got {original.shape}."
        )

    if original.dtype != np.uint8:
        original = original.astype(np.float32)
        original = np.nan_to_num(original)

        min_value = original.min()
        max_value = original.max()

        if max_value <= min_value:
            raise ValueError("Original HMI image has no intensity range.")

        original = (
            (original - min_value)
            / (max_value - min_value)
            * 255
        ).astype(np.uint8)

    if regions.shape[:2] != original.shape[:2]:
        regions = cv.resize(
            regions,
            (original.shape[1], original.shape[0]),
            interpolation=cv.INTER_NEAREST,
        )

    _, binary = cv.threshold(
        original,
        threshold,
        255,
        cv.THRESH_BINARY,
    )

    contours, _ = cv.findContours(
        binary,
        cv.RETR_EXTERNAL,
        cv.CHAIN_APPROX_SIMPLE,
    )

    if not contours:
        raise ValueError("No solar-disk contour was detected.")

    largest_contour = max(contours, key=cv.contourArea)

    mask = np.zeros(original.shape, dtype=np.uint8)
    cv.drawContours(
        mask,
        [largest_contour],
        contourIdx=-1,
        color=255,
        thickness=cv.FILLED,
    )

    masked_regions = cv.bitwise_and(
        regions,
        regions,
        mask=mask,
    )

    outline_color = (
        255 if masked_regions.ndim == 2 else (255, 255, 255)
    )

    cv.drawContours(
        masked_regions,
        [largest_contour],
        contourIdx=-1,
        color=outline_color,
        thickness=outline_thickness,
    )

    return masked_regions


def propose_active_regions(
    image_path,
    heatmap_output_dir: str | Path = "data/heat_maps",
    save_artifacts: bool = True,
):
    attribution_result = generate_attribution_maps(
        image_path=image_path,
        resize_to=PROPOSAL_IMAGE_SIZE,
        heatmap_output_dir=heatmap_output_dir,
        save_heatmaps=save_artifacts,
    )
    bounded_maps = {}
    bounded_polygons_by_method = {}
    bounded_map_paths = {}
    bounded_region_counts = {}
    for method_name in ATTRIBUTION_METHODS:
        bounded_map, bounded_polygons = bound_heatmap_regions(
            attribution_result["maps"][method_name]
        )
        bounded_maps[method_name] = bounded_map
        bounded_polygons_by_method[method_name] = bounded_polygons
        bounded_region_counts[method_name] = len(bounded_polygons)
        if save_artifacts:
            bounded_map_paths[method_name] = str(
                save_bounded_heatmap_overlay(
                    bounded_map=bounded_map,
                    polygons=bounded_polygons,
                    image_path=image_path,
                    output_dir=heatmap_output_dir,
                    method_name=method_name,
                )
            )

    proposal_score_map, final_polygons = fuse_overlapping_regions(
        bounded_maps=bounded_maps,
        polygons_by_method=bounded_polygons_by_method,
        min_methods=MIN_OVERLAPPING_METHODS,
    )
    attribution_result["maps"][PROPOSAL_HEATMAP_METHOD] = proposal_score_map
    heatmap_path = None
    if save_artifacts:
        heatmap_path = save_heatmap_image(
            attr_map=proposal_score_map,
            image_path=image_path,
            output_dir=heatmap_output_dir,
        )
        attribution_result["map_paths"][PROPOSAL_HEATMAP_METHOD] = str(heatmap_path)
        save_binary_raw_map(
            attr_map=proposal_score_map,
            image_path=image_path,
            output_dir=heatmap_output_dir,
            name="heatmap",
            threshold=BINARY_THRESHOLD,
        )
    proposal_heatmap_u8 = to_uint8_grayscale(proposal_score_map)

    resized_h, resized_w = PROPOSAL_IMAGE_SIZE
    resized_size_wh = (resized_w, resized_h)

    polygon_regions = build_polygon_regions(
        polygons=final_polygons,
        score_map=proposal_score_map,
    )
    final_regions = _build_region_outputs(
        polygon_regions=polygon_regions,
        original_size=attribution_result["original_size_wh"],
        resized_size_wh=resized_size_wh,
        crop_size_original=CROP_SIZE_ORIGINAL,
    )
    final_hulls_path = None
    proposal_overlay_path = None
    if save_artifacts:
        final_hulls_image = draw_hulls(
            hulls=final_polygons,
            image_shape=proposal_heatmap_u8.shape,
            draw_ids=True,
        )
        with Image.open(image_path) as source_image:
            original_hmi = np.asarray(source_image.convert("L"))
        original_resized = cv.resize(
            original_hmi,
            (resized_w, resized_h),
            interpolation=cv.INTER_AREA,
        )
        final_hulls_image = apply_full_disk_contour(
            original_hmi=original_resized,
            region_image=final_hulls_image,
        )
        final_hulls_path = save_final_hulls_image(
            final_hulls_image=final_hulls_image,
            image_path=image_path,
            output_dir=heatmap_output_dir,
        )
        proposal_overlay_path = save_region_proposal_overlay(
            heatmap_u8=proposal_heatmap_u8,
            regions=final_regions,
            image_path=image_path,
            output_dir=heatmap_output_dir,
        )

    return {
        "regions": final_regions,
        "debug": {
            "proposal_heatmap_method": PROPOSAL_HEATMAP_METHOD,
            "fusion_method": "union_of_cross_method_overlapping_regions",
            "minimum_overlapping_methods": MIN_OVERLAPPING_METHODS,
            "attribution_map_paths": attribution_result["map_paths"],
            "bounded_attribution_map_paths": bounded_map_paths,
            "bounded_region_counts": bounded_region_counts,
            "heatmap_path": str(heatmap_path) if heatmap_path else None,
            "final_hulls_path": str(final_hulls_path) if final_hulls_path else None,
            "proposal_overlay_path": str(proposal_overlay_path) if proposal_overlay_path else None,
        },
    }


__all__ = [
    "bbox_center_xy",
    "bounding_hulls",
    "bound_heatmap_regions",
    "build_polygon_regions",
    "clip_box_xyxy",
    "crop_box_around_center_xyxy",
    "draw_bounding_region",
    "draw_hulls",
    "fuse_overlapping_regions",
    "get_hulls",
    "polygon_to_bbox_xyxy",
    "propose_active_regions",
    "resize_box_to_original",
    "save_final_hulls_image",
    "save_bounded_heatmap_overlay",
    "save_heatmap_image",
    "save_region_proposal_overlay",
    "score_polygon_from_map",
]
