from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import torch
from PIL import Image

from prediction.pipeline.stages import full_disk_predict


class FullDiskPredictTests(TestCase):
    def setUp(self):
        get_model = full_disk_predict._get_full_disk_model
        get_model.cache_clear()
        self.addCleanup(get_model.cache_clear)
        image_dir = self.enterContext(TemporaryDirectory())
        self.image_path = str(Path(image_dir) / "full_disk.jpg")
        Image.new("L", (32, 32)).save(self.image_path)

    def test_reuses_model_across_predictions(self):
        model = Mock(return_value=torch.tensor([[0.0, 1.0]]))
        with patch.object(full_disk_predict, "load_full_disk_model", return_value=model) as loader:
            first = full_disk_predict.predict_full_disk(self.image_path)
            second = full_disk_predict.predict_full_disk(self.image_path, threshold=0.8)

        loader.assert_called_once_with(device=full_disk_predict.device)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(first["image_path"], self.image_path)
        self.assertAlmostEqual(first["p_non_flare"], 0.2689414)
        self.assertAlmostEqual(first["p_flare"], 0.7310586)
        self.assertEqual(first["pred_class"], 1)
        self.assertEqual(second, {**first, "pred_class": 0})

    def test_retries_after_model_load_failure(self):
        model = Mock(return_value=torch.zeros((1, 2)))
        with patch.object(
            full_disk_predict,
            "load_full_disk_model",
            side_effect=[FileNotFoundError("checkpoint missing"), model],
        ) as loader:
            with self.assertRaisesRegex(FileNotFoundError, "checkpoint missing"):
                full_disk_predict.predict_full_disk(self.image_path)

            result = full_disk_predict.predict_full_disk(self.image_path)

        self.assertEqual(loader.call_count, 2)
        model.assert_called_once()
        self.assertEqual(result["p_flare"], 0.5)
        self.assertEqual(result["pred_class"], 1)
