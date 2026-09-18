import cv2 as cv
import numpy as np
import pytest

from prediction.pipeline.stages.region_fusion import fuse_overlapping_regions


def rectangle(x1, y1, x2, y2):
    return np.array(
        [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        dtype=np.int32,
    )


def bounded_map(shape, polygons, value):
    mask = np.zeros(shape, dtype=np.uint8)
    cv.fillPoly(mask, polygons, 1)
    return mask.astype(np.float32) * value


def test_fusion_discards_overlap_when_only_two_methods_agree():
    shape = (40, 40)
    method_a = [rectangle(2, 2, 10, 10), rectangle(27, 2, 34, 9)]
    method_b = [rectangle(8, 5, 16, 13)]
    method_c = [rectangle(27, 25, 34, 32)]

    fused_map, merged_polygons = fuse_overlapping_regions(
        bounded_maps={
            "a": bounded_map(shape, method_a, 0.2),
            "b": bounded_map(shape, method_b, 0.6),
            "c": bounded_map(shape, method_c, 0.9),
        },
        polygons_by_method={"a": method_a, "b": method_b, "c": method_c},
    )

    assert merged_polygons == []
    assert not np.any(fused_map)


def test_fusion_merges_transitive_overlap_across_three_methods():
    shape = (40, 40)
    method_a = [rectangle(2, 10, 10, 18)]
    method_b = [rectangle(8, 10, 16, 18)]
    method_c = [rectangle(14, 10, 22, 18)]

    fused_map, merged_polygons = fuse_overlapping_regions(
        bounded_maps={
            "a": bounded_map(shape, method_a, 0.3),
            "b": bounded_map(shape, method_b, 0.6),
            "c": bounded_map(shape, method_c, 0.9),
        },
        polygons_by_method={"a": method_a, "b": method_b, "c": method_c},
    )

    assert len(merged_polygons) == 1
    assert fused_map[14, 3] == pytest.approx(0.3)
    assert fused_map[14, 11] == pytest.approx(0.6)
    assert fused_map[14, 21] == pytest.approx(0.9)


def test_fusion_merges_direct_overlap_from_all_three_methods():
    shape = (30, 30)
    method_a = [rectangle(2, 2, 12, 12)]
    method_b = [rectangle(7, 5, 17, 15)]
    method_c = [rectangle(9, 8, 20, 18)]

    fused_map, merged_polygons = fuse_overlapping_regions(
        bounded_maps={
            "a": bounded_map(shape, method_a, 0.3),
            "b": bounded_map(shape, method_b, 0.6),
            "c": bounded_map(shape, method_c, 0.9),
        },
        polygons_by_method={"a": method_a, "b": method_b, "c": method_c},
    )

    assert len(merged_polygons) == 1
    assert fused_map[10, 10] == pytest.approx(0.6)


def test_fusion_returns_empty_output_when_no_methods_overlap():
    shape = (20, 20)
    method_a = [rectangle(1, 1, 4, 4)]
    method_b = [rectangle(10, 10, 14, 14)]

    fused_map, merged_polygons = fuse_overlapping_regions(
        bounded_maps={
            "a": bounded_map(shape, method_a, 0.3),
            "b": bounded_map(shape, method_b, 0.7),
        },
        polygons_by_method={"a": method_a, "b": method_b},
    )

    assert merged_polygons == []
    assert not np.any(fused_map)
