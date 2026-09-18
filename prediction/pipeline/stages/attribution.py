from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

import torch
from captum.attr import DeepLiftShap, GuidedGradCam, IntegratedGradients
from torchvision.transforms import Compose, Resize, ToTensor
import torch.nn as nn

MODEL_PATH = Path("prediction/modeling/full_disk/trained_models/new-fold1.pth")
_ATTRIBUTION_MODEL: "AlexNet | None" = None
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class AlexNet(nn.Module):
    def __init__(self, num_classes: int = 2, dropout: float = 0.5) -> None:
        super().__init__()
        
        self.first_conv_layer = nn.Sequential(
            nn.Conv2d(1, 3, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, bias=True),
            nn.ReLU()
            )

        self.features = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=3, stride=2),
            nn.Conv2d(64, 192, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=3, stride=2),
            nn.Conv2d(192, 384, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(384, 256, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(256, 256, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=3, stride=2),
        )
        self.avgpool = nn.AdaptiveAvgPool2d((6, 6))
        self.classifier = nn.Sequential(
            nn.Dropout(p=dropout),
            nn.Linear(256 * 6 * 6, 4096),
            nn.ReLU(),
            nn.Dropout(p=dropout),
            nn.Linear(4096, 4096),
            nn.ReLU(),
            nn.Linear(4096, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.first_conv_layer(x)
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        return x


def _get_attribution_model() -> AlexNet:
    """Return the process-wide AlexNet used for all attribution calls."""
    global _ATTRIBUTION_MODEL
    if _ATTRIBUTION_MODEL is None:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(MODEL_PATH, map_location=device)
        _ATTRIBUTION_MODEL = AlexNet().to(device)
        _ATTRIBUTION_MODEL.load_state_dict(checkpoint["model_state_dict"])
        _ATTRIBUTION_MODEL.eval()
    return _ATTRIBUTION_MODEL


def normalize_map(arr):
    arr = np.asarray(arr, dtype=np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    arr = np.abs(arr)
    arr = arr - arr.min()
    maxv = arr.max()
    if maxv > 0:
        arr = arr / maxv
    return arr


def to_uint8_grayscale(arr: np.ndarray) -> np.ndarray:
    return (normalize_map(arr) * 255).clip(0, 255).astype(np.uint8)


def save_binary_raw_map(
    attr_map: np.ndarray,
    image_path,
    output_dir="data/raw_maps",
    name="guided_gradcam",
    threshold=30,
):
    image_stem = Path(image_path).stem or "unknown_image"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_uint8 = to_uint8_grayscale(attr_map)
    binary_map = np.zeros_like(raw_uint8, dtype=np.uint8)
    binary_map[raw_uint8 >= threshold] = 255

    npy_path = output_dir / f"{image_stem}_{name}_binary.npy"
    np.save(npy_path, binary_map)
    Image.fromarray(binary_map).save(output_dir / f"{image_stem}_{name}_binary.png")
    return npy_path


def save_raw_map_image(
    attr_map: np.ndarray,
    image_path,
    output_dir="data/raw_maps",
    name="heatmap",
):
    image_stem = Path(image_path).stem or "unknown_image"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_uint8 = to_uint8_grayscale(attr_map)
    png_path = output_dir / f"{image_stem}_{name}.png"
    Image.fromarray(raw_uint8).save(png_path)

    return png_path


def generate_attribution_maps(
    image_path,
    resize_to=(512, 512),
    heatmap_output_dir: str | Path = "data/heat_maps",
    save_heatmaps: bool = True,
    deepshap_baseline_tensors: torch.Tensor | None = None,
) -> dict:
    model = _get_attribution_model()
    device = next(model.parameters()).device
    transform = Compose([
        Resize(resize_to),
        ToTensor(),
    ])

    with Image.open(image_path) as image:
        pil_img = image.convert("L")
        original_size = pil_img.size
        img_tensor = transform(pil_img)

    input_tensor = img_tensor.unsqueeze(0).to(device)
    # Calculate gradients during backpropagation.
    input_tensor.requires_grad_(True)

    # GGCAM
    model.zero_grad()
    guided_gc = GuidedGradCam(model, model.features[10])
    gradcam_attr = guided_gc.attribute(input_tensor, target=1)
    gradcam_map = gradcam_attr.squeeze(0).detach().cpu().numpy().mean(axis=0)
    
    # Integrated gradients
    model.zero_grad()
    ig = IntegratedGradients(model)
    intgrad_attr, delta = ig.attribute(
        input_tensor,
        baselines=input_tensor * 0, 
        target=1,
        return_convergence_delta=True,
    )
    intgrad_map = intgrad_attr.squeeze(0).detach().cpu().numpy().mean(axis=0)
    
    # DeepLiftshap
    model.zero_grad()
    dls = DeepLiftShap(model)
    if deepshap_baseline_tensors is None:
        deepshap_baseline_tensors = torch.cat(
            [
                torch.zeros_like(input_tensor),
                torch.ones_like(input_tensor),
            ],
            dim=0,
        )

    deepshap_baseline_tensors = deepshap_baseline_tensors.to(device)
    deepshap_attr = dls.attribute(
        input_tensor,
        baselines=deepshap_baseline_tensors,
        target=1,
    )
    deepshap_map = deepshap_attr.squeeze(0).detach().cpu().numpy().mean(axis=0)

    maps = {
        "guided_gradcam": gradcam_map,
        "integrated_gradients": intgrad_map,
        "deepshap": deepshap_map,
    }
    
    map_paths = {}
    if save_heatmaps:
        map_paths = {
            method_name: str(
                save_raw_map_image(
                    attr_map=attr_map,
                    image_path=image_path,
                    output_dir=heatmap_output_dir,
                    name=method_name,
                )
            )
            for method_name, attr_map in maps.items()
        }

    return {
        "image_path": image_path,
        "input_tensor": input_tensor,
        "original_size_wh": original_size,
        "integrated_gradients_delta": (
            delta.detach().cpu().numpy() if torch.is_tensor(delta) else delta
        ),
        "maps": maps,
        "map_paths": map_paths,
        "attrs": {
            "guided_gradcam": gradcam_attr,
            "integrated_gradients": intgrad_attr,
            "deepshap": deepshap_attr,
        },
    }


__all__ = [
    "generate_attribution_maps",
    "MODEL_PATH",
    "normalize_map",
    "save_binary_raw_map",
    "save_raw_map_image",
    "to_uint8_grayscale",
]
