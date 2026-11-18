"""Shared loading for the fold-1 full-disk model."""

from pathlib import Path

import torch
from prediction.modeling.device import select_inference_device
from prediction.modeling.full_disk.model import Custom_AlexNet


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FOLD_1_WEIGHT_PATH = (
    REPOSITORY_ROOT / "prediction/modeling/full_disk/trained_models/new-fold1.pth"
)


def load_full_disk_model(
    weight_path: str | Path = FOLD_1_WEIGHT_PATH,
    device: torch.device | str | None = None,
) -> Custom_AlexNet:
    """Load the fold-1 full-disk checkpoint in evaluation mode."""
    path = Path(weight_path)
    if not path.is_file():
        raise FileNotFoundError(f"Full-disk model weights not found: {path}")

    selected_device = torch.device(device) if device is not None else select_inference_device()
    checkpoint_device = "cpu" if selected_device.type == "mps" else selected_device
    checkpoint = torch.load(path, map_location=checkpoint_device)
    model = Custom_AlexNet(pretrained=False, train=False).to(selected_device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model
