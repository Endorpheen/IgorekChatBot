"""Реестр поддерживаемых провайдеров изображений."""
from __future__ import annotations

from typing import Dict, Iterable

from .base import ProviderRegistryEntry
from .replicate import ReplicateAdapter
from .stability import StabilityAdapter
from .together import TogetherAdapter

PROVIDER_REGISTRY: Dict[str, ProviderRegistryEntry] = {
    "together": {
        "id": "together",
        "label": "Together AI",
        "enabled": True,
        "description": "FLUX, SDXL и другие модели через Together AI.",
        "recommended_models": {
            "black-forest-labs/FLUX.1-schnell-Free",
            "black-forest-labs/FLUX.1-dev",
        },
    },
    "replicate": {
        "id": "replicate",
        "label": "Replicate",
        "enabled": True,
        "description": "Коллекция моделей сообщества Replicate для генерации изображений.",
        "recommended_models": {
            "stability-ai/sdxl",
            "black-forest-labs/flux-1.1-pro",
        },
    },
    "stability": {
        "id": "stability",
        "label": "Stability AI",
        "enabled": True,
        "description": "Stable Diffusion через официальное API Stability.",
        "recommended_models": {
            "stable-diffusion-xl-v1",
            "stable-diffusion-v1-6",
        },
    },
}


def get_registry() -> Dict[str, ProviderRegistryEntry]:
    return PROVIDER_REGISTRY


def build_adapter(provider_id: str):
    provider_id = provider_id.lower()
    if provider_id == "together":
        return TogetherAdapter()
    if provider_id == "replicate":
        return ReplicateAdapter()
    if provider_id == "stability":
        return StabilityAdapter()
    raise KeyError(f"Неизвестный провайдер: {provider_id}")


__all__ = ["PROVIDER_REGISTRY", "get_registry", "build_adapter"]
