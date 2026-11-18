from __future__ import annotations

from functools import cache
from pathlib import Path

import torch
from PIL import Image
from torch.nn.functional import softmax
from torchvision.transforms import Compose, ToTensor

from prediction.modeling.device import select_inference_device

AR_IMAGE_TRANSFORM = Compose([ToTensor()])

DEFAULT_AR_MODELS = {
    "resnet": "prediction/modeling/active_region/trained_models/resnet/best_loss_ce.pth",
    "mobilenet": "prediction/modeling/active_region/trained_models/mobilenet/best_loss_ce.pth",
    "mobilevit": "prediction/modeling/active_region/trained_models/mobilevit/best_loss_ce.pth",
}


def build_ar_model(model_name: str) -> torch.nn.Module:
    if model_name == "resnet":
        from prediction.modeling.active_region.models.cnns import Custom_ResNet34
        return Custom_ResNet34(train=False)
    if model_name == "mobilenet":
        from prediction.modeling.active_region.models.mobilenet import MobileNet
        return MobileNet(pretrained=False)
    if model_name == "mobilevit":
        from prediction.modeling.active_region.models.mobilevit import MobileViT
        return MobileViT(
            image_size=(512, 512),
            dims=[144, 192, 240],
            channels=[16, 32, 64, 64, 96, 96, 128, 128, 160, 160, 640],
            num_classes=2,
        )

    raise ValueError(f"Unsupported AR model: {model_name}")


def load_ar_model(
    model_name: str,
    checkpoint_path: str | Path | None = None,
    device: torch.device | str = "cpu",
) -> tuple[torch.nn.Module, Path]:
    checkpoint_path = Path(checkpoint_path or DEFAULT_AR_MODELS[model_name])
    device = torch.device(device)
    checkpoint_device = "cpu" if device.type == "mps" else device
    checkpoint = torch.load(checkpoint_path, map_location=checkpoint_device)

    model = build_ar_model(model_name).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    return model, checkpoint_path


@cache
def _get_ar_model(
    model_name: str,
    device: torch.device,
) -> tuple[torch.nn.Module, Path]:
    """Reuse the default checkpoint model for this worker process."""
    return load_ar_model(model_name, device=device)


def predict_one_ar_image(
    image: str | Path | Image.Image,
    model: torch.nn.Module,
    device: torch.device | str = "cpu",
    threshold: float = 0.5,
) -> dict:
    if isinstance(image, (str, Path)):
        pil_image = Image.open(image).convert("L")
        image_path = str(image)
    else:
        pil_image = image.convert("L")
        image_path = None

    image_tensor = AR_IMAGE_TRANSFORM(pil_image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(image_tensor)
        probs = softmax(logits, dim=1)
        ar_prob = float(probs[0, 1].item())

    return {
        "image_path": image_path,
        "ar_prob": ar_prob,
        "pred_class": int(ar_prob >= threshold),
    }


def predict_ar_models_for_regions(
    crop_results: list[dict],
    model_names: list[str] | None = None,
    threshold: float = 0.5,
) -> list[dict]:
    if not crop_results:
        return []

    model_names = model_names or ["mobilenet"]
    device = select_inference_device()

    loaded_models: dict[str, tuple[torch.nn.Module, Path]] = {}
    load_errors: dict[str, str] = {}
    for model_name in model_names:
        try:
            loaded_models[model_name] = _get_ar_model(model_name, device)
        except Exception as exc:
            load_errors[model_name] = f"{type(exc).__name__}: {exc}"

    enriched_regions = []
    for crop_result in crop_results:
        ar_predictions = {}
        for model_name, (model, checkpoint_path) in loaded_models.items():
            prediction = predict_one_ar_image(
                image=crop_result["image"],
                model=model,
                device=device,
                threshold=threshold,
            )
            ar_predictions[model_name] = {
                "checkpoint_path": str(checkpoint_path),
                "ar_prob": prediction["ar_prob"],
                "pred_class": prediction["pred_class"],
            }
        for model_name, error_message in load_errors.items():
            ar_predictions[model_name] = {
                "error": error_message,
            }

        enriched_region = dict(crop_result)
        enriched_region.pop("image", None)
        enriched_region["ar_predictions"] = ar_predictions
        enriched_regions.append(enriched_region)

    return enriched_regions
