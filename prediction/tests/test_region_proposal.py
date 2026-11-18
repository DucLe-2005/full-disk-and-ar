from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import cv2 as cv
import numpy as np
from PIL import Image

from prediction.pipeline.stages import region_proposal
from prediction.pipeline.stages.crop_regions import crop_proposed_active_regions_from_image


class FusedHeatmapTests(TestCase):
    def test_saved_candidate_images_match_the_extracted_crop_footprints(self):
        polygon = np.array([[4, 4], [24, 4], [4, 24]], dtype=np.int32)
        edge_polygon = np.array([[27, 27], [31, 27], [31, 31]], dtype=np.int32)
        polygons = [polygon, edge_polygon]
        mask = np.zeros((32, 32), dtype=np.uint8)
        cv.fillPoly(mask, polygons, 1)
        fused_map = mask.astype(np.float32)
        attribution = {
            "maps": dict.fromkeys(region_proposal.ATTRIBUTION_METHODS, fused_map),
            "map_paths": {},
            "original_size_wh": (64, 64),
        }

        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "disk.png"
            Image.new("L", (64, 64), 128).save(image_path)
            with (
                patch.object(region_proposal, "PROPOSAL_IMAGE_SIZE", (32, 32)),
                patch.object(region_proposal, "CROP_SIZE_ORIGINAL", 16),
                patch.object(region_proposal, "generate_attribution_maps", return_value=attribution),
                patch.object(region_proposal, "bound_heatmap_regions", return_value=(fused_map, polygons)),
            ):
                result = region_proposal.propose_active_regions(image_path, directory)

            crops = crop_proposed_active_regions_from_image(
                image_path, result["regions"], output_dir=None, resize_to=(16, 16)
            )
            self.assertEqual(crops[0]["crop_box_clipped_original_xyxy"], (20, 20, 36, 36))
            self.assertEqual(crops[1]["crop_box_clipped_original_xyxy"], (50, 50, 64, 64))
            self.assertEqual(crops[1]["crop_padding_ltrb"], (0, 0, 2, 2))
            self.assertEqual(crops[0]["crop_box_resized_xyxy"], (10, 10, 17, 17))
            self.assertEqual(crops[1]["crop_box_resized_xyxy"], (25, 25, 31, 31))

            path = Path(result["debug"]["heatmap_path"])
            self.assertEqual(path.name, "disk_heatmap.png")
            self.assertEqual(str(path), result["debug"]["attribution_map_paths"]["consensus"])
            with Image.open(path) as image:
                self.assertEqual(image.getpixel((17, 13)), (0, 255, 255))  # Last pixel in the crop
                self.assertEqual(image.getpixel((18, 13)), (0, 0, 0))  # Immediately past the crop
                self.assertEqual(image.getpixel((14, 14)), (255, 255, 255))  # Unoutlined polygon edge
                self.assertEqual(image.getpixel((31, 28)), (0, 255, 255))  # Crop meets image edge
                fused_boxes = np.all(np.asarray(image) == (0, 255, 255), axis=2)

            for key in ("final_hulls_path", "proposal_overlay_path"):
                with self.subTest(artifact=key), Image.open(result["debug"][key]) as image:
                    boxes = np.all(np.asarray(image) == (0, 255, 255), axis=2)
                    np.testing.assert_array_equal(boxes, fused_boxes)
