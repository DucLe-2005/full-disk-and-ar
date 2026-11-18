from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, call, patch

import torch
from PIL import Image

from prediction.pipeline.stages import ar_predict


class ArPredictTests(TestCase):
    def setUp(self):
        ar_predict._get_ar_model.cache_clear()
        self.addCleanup(ar_predict._get_ar_model.cache_clear)
        self.enterContext(patch.object(
            ar_predict, "select_inference_device", return_value=torch.device("cpu")
        ))
        self.image = Image.new("L", (32, 32))
        self.addCleanup(self.image.close)
        self.crops = [{"id": 1, "image": self.image}, {"id": 2, "image": self.image}]
        self.device = torch.device("cpu")
        self.model = Mock(return_value=torch.zeros((1, 2)))
        self.checkpoint = Path("mobilenet.pth")
        self.loader = self.enterContext(
            patch.object(ar_predict, "load_ar_model", return_value=(self.model, self.checkpoint))
        )

    def test_reuses_model_for_later_jobs_and_all_crops(self):
        first = ar_predict.predict_ar_models_for_regions(self.crops)
        second = ar_predict.predict_ar_models_for_regions(self.crops, threshold=0.6)

        self.loader.assert_called_once_with("mobilenet", device=self.device)
        self.assertEqual(self.model.call_count, 4)
        for index, crop in enumerate(self.crops):
            prediction = {"checkpoint_path": str(self.checkpoint), "ar_prob": 0.5}
            self.assertEqual(first[index], {
                "id": crop["id"],
                "ar_predictions": {"mobilenet": {**prediction, "pred_class": 1}},
            })
            self.assertEqual(second[index], {
                "id": crop["id"],
                "ar_predictions": {"mobilenet": {**prediction, "pred_class": 0}},
            })

    def test_separates_models_by_device(self):
        for device in (self.device, torch.device("cuda:0")):
            self.assertIs(ar_predict._get_ar_model("mobilenet", device)[0], self.model)
            self.assertIs(ar_predict._get_ar_model("mobilenet", device)[0], self.model)

        self.assertEqual(self.loader.call_args_list, [
            call("mobilenet", device=self.device),
            call("mobilenet", device=torch.device("cuda:0")),
        ])

    def test_skips_model_loading_without_crops(self):
        self.assertEqual(ar_predict.predict_ar_models_for_regions([]), [])
        self.loader.assert_not_called()

    def test_retries_only_the_model_that_failed_to_load(self):
        resnet = Mock(return_value=torch.zeros((1, 2)))
        self.loader.side_effect = [
            (self.model, self.checkpoint),
            FileNotFoundError("checkpoint missing"),
            (resnet, Path("resnet.pth")),
        ]

        first = ar_predict.predict_ar_models_for_regions(self.crops, ["mobilenet", "resnet"])
        second = ar_predict.predict_ar_models_for_regions(self.crops, ["mobilenet", "resnet"])

        self.assertEqual(self.loader.call_args_list, [
            call("mobilenet", device=self.device),
            call("resnet", device=self.device),
            call("resnet", device=self.device),
        ])
        self.assertEqual(self.model.call_count, 4)
        self.assertEqual(resnet.call_count, 2)
        for before, after in zip(first, second):
            self.assertEqual(
                before["ar_predictions"]["mobilenet"], after["ar_predictions"]["mobilenet"]
            )
            self.assertEqual(before["ar_predictions"]["resnet"], {
                "error": "FileNotFoundError: checkpoint missing",
            })
            self.assertEqual(after["ar_predictions"]["resnet"], {
                "checkpoint_path": "resnet.pth", "ar_prob": 0.5, "pred_class": 1,
            })
