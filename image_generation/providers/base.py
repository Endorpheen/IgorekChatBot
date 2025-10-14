"""Базовые компоненты провайдеров генерации изображений."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Protocol, TypedDict


class ProviderErrorCode(str, Enum):
    """Унифицированные коды ошибок адаптеров провайдеров."""

    UNAUTHORIZED = "UNAUTHORIZED"
    RATE_LIMIT = "RATE_LIMIT"
    BAD_REQUEST = "BAD_REQUEST"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"


class ProviderError(Exception):
    """Исключение, нормализующее ошибку провайдера."""

    def __init__(self, code: ProviderErrorCode, message: str, *, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ModeOption(TypedDict, total=False):
    id: str
    label: str
    description: str


class ProviderModelCapabilities(TypedDict, total=False):
    supports_steps: bool
    supports_cfg: bool
    supports_seed: bool
    supports_mode: bool
    modes: List[ModeOption]


class ProviderModelLimits(TypedDict, total=False):
    min_steps: int
    max_steps: int
    min_cfg: float
    max_cfg: float
    min_width: int
    max_width: int
    min_height: int
    max_height: int
    width_values: List[int]
    height_values: List[int]
    presets: List[List[int]]


class ProviderModelDefaults(TypedDict, total=False):
    width: int
    height: int
    steps: int
    cfg: float
    seed: int
    mode: str


class ProviderModelSpec(TypedDict, total=False):
    id: str
    display_name: str
    recommended: bool
    capabilities: ProviderModelCapabilities
    limits: ProviderModelLimits
    defaults: ProviderModelDefaults
    metadata: Dict[str, Any]


class ProviderRegistryEntry(TypedDict, total=False):
    id: str
    label: str
    enabled: bool
    description: str
    recommended_models: Iterable[str]


@dataclass(slots=True)
class GenerateResult:
    image_bytes: Optional[bytes] = None
    image_url: Optional[str] = None
    mime_type: str = "image/webp"


class ImageProviderAdapter(Protocol):
    """Интерфейс адаптера провайдера изображений."""

    provider_id: str

    def list_models(self, key: str, *, force: bool = False) -> List[ProviderModelSpec]:
        """Возвращает список моделей провайдера."""

    def validate_params(
        self,
        model_id: str,
        params: Dict[str, Any],
        *,
        model_spec: Optional[ProviderModelSpec] = None,
    ) -> Dict[str, Any]:
        """Проверяет и нормализует параметры генерации."""

    async def generate(self, prompt: str, params: Dict[str, Any], key: str) -> GenerateResult:
        """Запускает генерацию изображения."""


# Значения по умолчанию согласно политике.
DEFAULT_SIZE_PRESETS: List[tuple[int, int]] = [
    (1024, 1024),
    (1280, 720),
    (720, 1280),
    (832, 1216),
    (1216, 832),
]
DEFAULT_STEPS = 28
DEFAULT_STEPS_RANGE = (1, 50)
DEFAULT_CFG = 4.5
DEFAULT_CFG_RANGE = (0.0, 20.0)
DEFAULT_SEED_RANGE = (0, 2_147_483_647)


def apply_limit_defaults(spec: ProviderModelSpec) -> ProviderModelSpec:
    """Гарантирует присутствие дефолтных лимитов и параметров в спецификации модели."""

    limits = spec.setdefault("limits", ProviderModelLimits())  # type: ignore[arg-type]
    defaults = spec.setdefault("defaults", ProviderModelDefaults())  # type: ignore[arg-type]
    capabilities = spec.setdefault("capabilities", ProviderModelCapabilities())  # type: ignore[arg-type]

    # Размеры
    width_values = limits.setdefault("width_values", [])
    height_values = limits.setdefault("height_values", [])
    if not width_values or not height_values:
        limits["width_values"] = sorted({w for w, _ in DEFAULT_SIZE_PRESETS})
        limits["height_values"] = sorted({h for _, h in DEFAULT_SIZE_PRESETS})
    if not limits.get("presets"):
        limits["presets"] = [[w, h] for w, h in DEFAULT_SIZE_PRESETS]
    limits.setdefault("min_width", min(w for w, _ in DEFAULT_SIZE_PRESETS))
    limits.setdefault("max_width", max(w for w, _ in DEFAULT_SIZE_PRESETS))
    limits.setdefault("min_height", min(h for _, h in DEFAULT_SIZE_PRESETS))
    limits.setdefault("max_height", max(h for _, h in DEFAULT_SIZE_PRESETS))

    # Steps
    limits.setdefault("min_steps", DEFAULT_STEPS_RANGE[0])
    limits.setdefault("max_steps", DEFAULT_STEPS_RANGE[1])

    # CFG
    limits.setdefault("min_cfg", DEFAULT_CFG_RANGE[0])
    limits.setdefault("max_cfg", DEFAULT_CFG_RANGE[1])

    defaults.setdefault("width", DEFAULT_SIZE_PRESETS[0][0])
    defaults.setdefault("height", DEFAULT_SIZE_PRESETS[0][1])
    defaults.setdefault("steps", DEFAULT_STEPS)
    defaults.setdefault("cfg", DEFAULT_CFG)

    capabilities.setdefault("supports_steps", True)
    capabilities.setdefault("supports_cfg", True)
    capabilities.setdefault("supports_seed", True)
    capabilities.setdefault("supports_mode", False)
    if capabilities.get("supports_mode") and "modes" not in capabilities:
        capabilities["modes"] = []

    return spec


__all__ = [
    "ProviderErrorCode",
    "ProviderError",
    "ProviderModelCapabilities",
    "ProviderModelLimits",
    "ProviderModelDefaults",
    "ProviderModelSpec",
    "ProviderRegistryEntry",
    "GenerateResult",
    "ImageProviderAdapter",
    "apply_limit_defaults",
    "DEFAULT_SIZE_PRESETS",
    "DEFAULT_STEPS",
    "DEFAULT_STEPS_RANGE",
    "DEFAULT_CFG",
    "DEFAULT_CFG_RANGE",
    "DEFAULT_SEED_RANGE",
]
