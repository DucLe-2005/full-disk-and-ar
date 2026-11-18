from unittest import TestCase
from unittest.mock import patch

import torch

from prediction.modeling.device import select_inference_device


class InferenceDeviceTests(TestCase):
    def test_device_priority(self):
        for cuda, mps, expected in (
            (True, True, "cuda:0"),
            (True, False, "cuda:0"),
            (False, True, "mps"),
            (False, False, "cpu"),
        ):
            with (
                self.subTest(cuda=cuda, mps=mps),
                patch.object(torch.cuda, "is_available", return_value=cuda),
                patch.object(torch.backends.mps, "is_available", return_value=mps),
            ):
                self.assertEqual(select_inference_device(), torch.device(expected))
